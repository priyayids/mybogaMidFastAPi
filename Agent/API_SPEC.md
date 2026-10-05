# Middle Service API Specification

Base URL (local): `http://localhost:8000/api/v1`
Base URL (deployed): `https://dev.app-cube.tech/api/v1`

Interactive docs: `/docs` (Swagger UI) and `/redoc`.
To call protected endpoints from Swagger UI, use **Authorize** and supply the
client API key, then "Try it out" → Execute. Closing the dialog without
pressing Authorize discards the key and requests will return 401.

## 1. Authentication

Client endpoints expect:
```http
X-Client-API-Key: <CLIENT_API_KEY>
```
The key is matched by exact string comparison (`app/core/security.py`). There
is no hashing, trimming, or case folding, and `CLIENT_API_KEYS` accepts a
comma-separated list. Missing or unknown keys return `401`.

Nuveq webhooks authenticate using the path token:
```http
POST /api/v1/webhooks/nuveq/{webhook_secret_token}
```

> The secret is a **URL path segment**. It must not contain `/`, and must be
> URL-safe. Nuveq sends no HMAC signature, so this path token plus an optional
> Nuveq egress IP allowlist is the entire trust boundary for inbound events.

---

## 2. Room Management Endpoints

### 2.1 List Rooms & Current Status
- **GET** `/rooms`
- **Response:**
```json
[
  {
    "id": "rm_c7f4d607e522",
    "name": "Ruang Meeting 1 Gedung A",
    "site_id": 167,
    "controller_id": 2228,
    "door_number": 1,
    "door_id": 3523,
    "lift_group_id": 630,
    "grace_minutes": 15,
    "is_active": true,
    "current_status": "AVAILABLE",
    "active_booking_id": null
  }
]
```

### 2.2 Get Single Room
- **GET** `/rooms/{id}`

### 2.3 Create Room (Map to Nuveq Door)
- **POST** `/rooms`
- **Request Body:**
```json
{
  "name": "Ruang Meeting 1 Gedung A",
  "site_id": 167,
  "controller_id": 2228,
  "door_number": 1,
  "door_id": 3523,
  "lift_group_id": 630,
  "grace_minutes": 15
}
```

### 2.4 Update Room
- **PATCH** `/rooms/{id}`

### 2.5 Delete Room
- **DELETE** `/rooms/{id}`

---

## 3. Booking Endpoints

### 3.1 Create Booking
- **POST** `/bookings`
- **Request Body:**
```json
{
  "room_id": "rm_c7f4d607e522",
  "booker_name": "Budi Santoso",
  "booker_email": "budi@example.com",
  "booker_phone": "+6281234567890",
  "visit_start": "2026-10-05T10:00:00+07:00",
  "visit_end": "2026-10-05T12:00:00+07:00",
  "notes": "Board meeting"
}
```
- **Response (HTTP 201):**
```json
{
  "id": "bk_98fbc923a12",
  "room_id": "rm_c7f4d607e522",
  "credential_number": 88123456,
  "status": "BOOKED",
  "booker_name": "Budi Santoso",
  "booker_email": "budi@example.com",
  "visit_start": "2026-10-05T10:00:00+07:00",
  "visit_end": "2026-10-05T12:00:00+07:00",
  "expires_at": "2026-10-05T10:15:00+07:00",
  "qr_data_uri": "data:image/png;base64,iVBORw0KGgo...",
  "qr_download_url": "/api/v1/bookings/bk_98fbc923a12/qr"
}
```

### 3.2 Get Booking Detail
- **GET** `/bookings/{id}`

### 3.3 Cancel Booking (Revokes Access)
- **DELETE** `/bookings/{id}`
- Revokes reader access immediately via Nuveq `DELETE /api/visitors/registrations/{visitor_registration_id}`.

### 3.4 Get Booking QR Image
- **GET** `/bookings/{id}/qr`
- Returns direct `image/png` response.

---

## 4. Webhook Ingestion & Dispatch

### 4.1 Nuveq Inbound Webhook
- **POST** `/webhooks/nuveq/{secret_token}`
- Full path: `https://dev.app-cube.tech/api/v1/webhooks/nuveq/{secret_token}`
  (note the `/api/v1` prefix — omitting it 404s).
- Accepts Nuveq raw tap / status payload. Responds fast with
  `{ "received": true, "uuid": "...", "processed": true }`.
- Deduplicated on the payload `uuid`. A replay returns
  `"Duplicate event ignored"` with `processed: false`.
- Only `name == "Valid visitor"` drives booking state
  (`BOOKED → CHECKED_IN → CHECKED_OUT`). All other event types are still
  persisted and marked processed.

Two rows are written per accepted event:

| Table | Contents |
|---|---|
| `tap_events` | Full event log, including the complete `raw_payload` JSON |
| `idempotency_records` | Dedup key (`key` = event `uuid`) |

`bookings` is updated only for valid-visitor taps. Neither table is exposed
over HTTP — inspect them directly in Postgres.

> There is currently no retention/TTL job, so `tap_events` and
> `idempotency_records` grow without bound and idempotency keys never expire.

### 4.2 Client Webhook Notification Configuration
- **POST** `/webhooks/client-config`
```json
{
  "url": "https://client-booking-site.com/api/room-status-webhook",
  "secret": "whsec_supersecretkey",
  "is_active": true
}
```
- **GET** `/webhooks/client-config` lists registrations.
- No per-ID route exists: every POST adds a row and *all* active rows are
  notified, so entries cannot be updated or deleted via the API.
- Note: **manual booking cancellation dispatches no client webhook**, unlike
  no-show expiry and auto-checkout. Clients must re-fetch room status after a
  `DELETE /bookings/{id}` or their dashboard will show a stale `BOOKED`.

---

## 5. Nuveq Sync / Explorer Proxy (Admin)

Endpoints enabling the client admin to discover available doors, controllers, and sites without needing Nuveq dashboard credentials:
- **GET** `/nuveq/sites`
- **GET** `/nuveq/controllers`
- **GET** `/nuveq/doors`
- **GET** `/nuveq/lift-groups`
- **POST** `/nuveq/setup-webhook` (Configures account-level webhook URL on Nuveq Cloud)

```json
{
  "webhook_url": "https://dev.app-cube.tech/api/v1/webhooks/nuveq/<secret>",
  "enable": true,
  "backup_webhook_url": null
}
```

> **Registering this overwrites any webhook already configured on the Nuveq
> account, and Nuveq exposes no way to read the current value back**
> (`GET /api/webhooks` returns 404; the OpenAPI spec lists `POST` only).
> One webhook per account is supported, plus one optional `webhookLink2`.
> Check the Nuveq dashboard for an existing webhook before calling this.
