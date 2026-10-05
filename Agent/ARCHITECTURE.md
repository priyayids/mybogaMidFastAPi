# Architecture Blueprint: Nuveq Middle Service

## 1. Overview & Objectives

The Nuveq Middle Service functions as a Backend-For-Frontend (BFF) and integration bridge between a client meeting-room booking website and the Nuveq Cloud Access Control platform.

### Core Objectives:
1. **Security Isolation:** Keep the master Nuveq API key and internal controller/door infrastructure completely hidden from the client website and browser.
2. **Domain Simplification:** Translate low-level Nuveq access control concepts (controllers, door IDs, visitor registrations, card credentials) into simple meeting-room booking concepts (rooms, bookings, QR codes, room status).
3. **Value-Added Automation:**
   - **No-Show Expiry:** Automatically revokes access at the door reader if the booker fails to check in within a configurable grace period after `visit_start`.
   - **Auto-Updating Room Status:** Real-time room status (`AVAILABLE`, `BOOKED`, `IN_USE`, `EXPIRED`, `MAINTENANCE`) calculated dynamically and pushed to client webhooks.
   - **QR Code Issuance:** Directly generates clean QR code images and data URIs encoding the unique numeric credential number.
   - **Event Deduplication & Resilience:** Handles webhook backlog bursts with idempotency guarantees (by `event_uuid`) and provides a reconciliation polling fallback.

---

## 2. System Architecture Diagram

```
 Client Web App (Meeting Room Booking)
        │
        │ REST API (X-Client-API-Key)
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   FASTAPI MIDDLE SERVICE (Port 8000)                   │
│                                                                        │
│  ┌──────────────┐     ┌────────────────┐     ┌──────────────────────┐  │
│  │ API Routers  │────►│ Service Layer  │────►│ Database (SQLAlchemy)│  │
│  │  - Rooms     │     │  - RoomService │     │  - Rooms             │  │
│  │  - Bookings  │     │  - BookingSvc  │     │  - Bookings          │  │
│  │  - Webhooks  │     │  - WebhookSvc  │     │  - Tap Events        │  │
│  │  - QR Codes  │     │  - QR Service  │     │  - Idempotency Keys  │  │
│  └──────────────┘     └───────┬────────┘     │  - Client Webhooks   │  │
│                               │              └──────────────────────┘  │
│                               ▼                                        │
│                     ┌────────────────────┐                             │
│                     │ NuveqApiClient     │                             │
│                     │ (HTTPX Async)      │                             │
│                     └─────────┬──────────┘                             │
│                               │                                        │
│  ┌────────────────────────────┼─────────────────────────────────────┐  │
│  │ APScheduler Background Jobs│                                     │  │
│  │  - No-show auto-revoke     │ (Calls Nuveq Revoke Registration)   │  │
│  │  - Auto check-out buffer   │                                     │  │
│  │  - Periodic reconciliation │ (Polls GET /api/events fallback)    │  │
│  └────────────────────────────┴─────────────────────────────────────┘  │
└───────────────────────────────┬────────────────────────────────────────┘
                                │ X-API-KEY (Internal Only)
                                ▼
                       Nuveq Cloud API (api-v2.nuveq.cloud)
                                │
                                │ Inbound Webhook (Taps, Status)
                                ▼
                 POST /api/v1/webhooks/nuveq/{secret}
```

---

## 3. Booking State Machine

```
              ┌──────────────┐
              │    DRAFT     │
              └──────┬───────┘
                     │ POST /bookings (Creates Nuveq Registration + QR)
                     ▼
              ┌──────────────┐
              │    BOOKED    │
              └──────┬───────┘
                     │
         ┌───────────┼────────────────────────────────────────┐
         │           │                                        │
 (Now > Start + Grace│ (Webhook: Valid visitor, Entry)        │ (DELETE /bookings/{id})
  & No Entry Tap)    │                                        │
         │           ▼                                        ▼
         │    ┌──────────────┐                         ┌──────────────┐
         │    │  CHECKED_IN  │                         │  CANCELLED   │
         │    └──────┬───────┘                         └──────────────┘
         │           │
         │   ┌───────┴────────────────────────┐
         │   │                                │
         │   │ (Webhook: Exit)                │ (Now > End + Buffer)
         │   ▼                                ▼
         │┌──────────────┐            ┌──────────────────┐
         ││ CHECKED_OUT  │            │ AUTO_CHECKED_OUT │
         │└──────────────┘            └──────────────────┘
         │
         ▼
  ┌──────────────┐
  │   EXPIRED    │  (Revokes Nuveq registration at door reader)
  └──────────────┘
```

---

## 4. Room Status Derivation Logic

A room's status (`AVAILABLE`, `BOOKED`, `IN_USE`, `EXPIRED`, `MAINTENANCE`) is computed deterministically:
1. **MAINTENANCE:** If `room.is_active == False`.
2. **IN_USE:** If there is any booking in `CHECKED_IN` state where `now` falls between `visit_start - buffer` and `visit_end + buffer`.
3. **BOOKED:** If there is any active booking in `BOOKED` state where `visit_start <= now <= visit_end`.
4. **AVAILABLE:** All other times.

Any event that alters a booking's status triggers:
1. Recalculation of the room's status.
2. Immediate asynchronous broadcast to the registered client webhook URL.

---

## 5. Security & Isolation Architecture

- **Credential Isolation:** The client never receives or stores Nuveq API keys. Nuveq sees only requests from our middle service IP.
- **Client Authentication:** Middle service endpoints require an `X-Client-API-Key` header matching configured keys.
- **Webhook Protection:** Nuveq webhook payloads are delivered to a unique secret path `POST /api/v1/webhooks/nuveq/{secret_token}`.
- **Idempotency Guarantee:** Incoming events are deduplicated by their unique `uuid` field stored in the `idempotency_records` table, preventing replay anomalies caused by Nuveq reconnect backlog bursts.
