# Nuveq Access Control Middle Service (BFF)

A high-performance, asynchronous Backend-For-Frontend (BFF) and integration middleware connecting meeting-room booking platforms with **Nuveq Cloud Access Control** (`https://api-v2.nuveq.cloud`).

Built with **FastAPI**, **SQLAlchemy 2.0 (Async)**, **APScheduler**, and **Pydantic v2**.

---

## 📁 Repository Structure

```
.
├── Agent/                         # 🧠 Single Central AI Hub: All AI docs, specs, research & briefs
│   ├── README.md                  # Agent directory index
│   ├── nuveq-integration-brief.md # Original comprehensive live-captured research brief
│   ├── ARCHITECTURE.md            # System architecture, state machine & security blueprint
│   ├── API_SPEC.md                # REST & Webhook API specification
│   └── PROGRESS.md                # Implementation progress & test status
├── app/
│   ├── api/                       # API Routes & Dependencies
│   │   ├── deps.py                # Dependency injection (DB, auth, services)
│   │   └── v1/
│   │       ├── bookings.py        # Booking CRUD, QR codes, Nuveq sync
│   │       ├── health.py          # /healthz endpoint
│   │       ├── nuveq.py           # Admin discovery proxy (sites, controllers, doors)
│   │       ├── rooms.py           # Room mapping & real-time status
│   │       ├── router.py          # V1 router aggregation
│   │       └── webhooks.py        # Nuveq webhook receiver & client dispatch
│   ├── core/                      # Application Core
│   │   ├── config.py              # Pydantic BaseSettings (.env management)
│   │   ├── database.py            # Async engine, sessionmaker & Base
│   │   ├── exceptions.py          # Domain-specific exception hierarchy
│   │   ├── logging.py             # Structured logging setup
│   │   └── security.py            # API key & webhook secret verifiers
│   ├── models/                    # SQLAlchemy 2.0 Async Models
│   │   └── __init__.py            # Room, Booking, TapEvent, IdempotencyRecord, ClientWebhookConfig
│   ├── schemas/                   # Pydantic Schemas (DTOs)
│   │   ├── booking.py             # Booking schemas
│   │   ├── common.py              # Standard ApiResponse wrappers
│   │   ├── nuveq.py               # Nuveq proxy schemas
│   │   ├── room.py                # Room schemas
│   │   └── webhook.py             # Nuveq webhook payload & notification schemas
│   ├── services/                  # Business Logic Layer (Clean Code & DRY)
│   │   ├── booking_service.py     # Booking lifecycle & Nuveq credential generation
│   │   ├── nuveq_client.py        # Typed HTTPX client for Nuveq Cloud REST API
│   │   ├── qr_service.py          # QR PNG binary & Data URI generation
│   │   ├── room_service.py        # Room mapping & dynamic status derivation
│   │   ├── scheduler_service.py   # No-show auto-revoke, auto checkout & reconciliation
│   │   └── webhook_service.py     # Event deduplication & state transitions
│   └── main.py                    # FastAPI application initialization & lifespan
├── tests/                         # Comprehensive Async Test Suite
│   ├── conftest.py                # Test fixtures, in-memory SQLite, mock Nuveq client
│   ├── test_bookings.py           # Booking flow, conflict checking & cancellation
│   ├── test_nuveq_endpoints.py    # Nuveq discovery proxy tests
│   ├── test_qr_service.py         # QR code rendering tests
│   ├── test_rooms.py              # Room CRUD, door mapping & status tests
│   ├── test_scheduler.py          # No-show auto-expiry & auto-checkout tests
│   └── test_webhooks.py           # Webhook idempotency, entry/exit state transitions
├── .env.example                   # Environment configuration template
├── pytest.ini                     # Pytest settings
├── requirements.txt               # Production & test dependencies
└── README.md
```

---

## 🚀 Key Features

1. **Security Isolation:**
   - Client website never sees the master Nuveq API key.
   - Client accesses middle service via `X-Client-API-Key`.
   - Nuveq webhook delivered to secret URL path token (`/api/v1/webhooks/nuveq/{secret}`).

2. **No-Show Auto-Revocation (Value-Add):**
   - Background scheduler checks bookings every 60s.
   - If `now > visit_start + grace_minutes` and no `Entry` tap was recorded, the registration is automatically revoked at the reader via `DELETE /api/visitors/registrations/{id}` and marked `EXPIRED`.

3. **Real-Time Room Status Derivation:**
   - Computes status dynamically: `AVAILABLE`, `BOOKED`, `IN_USE`, `EXPIRED`, `MAINTENANCE`.
   - Updates immediately on tap webhooks and broadcasts to client webhooks.

4. **Credential & QR Generation:**
   - Generates unique numeric 8-digit credentials (`credentialNumber`).
   - Automatically renders QR code PNG bytes and base64 Data URIs (`/bookings/{id}/qr`).

5. **Webhook Deduplication & Backpressure:**
   - Deduplicates Nuveq burst deliveries by event `uuid` (idempotency table).
   - Fast HTTP 200 acknowledgment.

---

## 🛠️ Quickstart

### 1. Setup Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Run Tests
```bash
pytest -v
```

### 3. Start Development Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive Swagger API docs available at: `http://localhost:8000/docs`

---

## 📖 Documentation

For deep technical details, state machine diagrams, live webhook capture schemas, and architecture plans, refer to the `/Agent` directory:
- [Agent/README.md](Agent/README.md)
- [Agent/ARCHITECTURE.md](Agent/ARCHITECTURE.md)
- [Agent/API_SPEC.md](Agent/API_SPEC.md)
- [Agent/PROGRESS.md](Agent/PROGRESS.md)
- [Agent/nuveq-integration-brief.md](Agent/nuveq-integration-brief.md)
