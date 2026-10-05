# Schema Reference

> **Legend**
> - **Custom** — invented by this middle service, never sent to / returned by Nuveq as-is
> - **Original** — mirrors a real Nuveq field (camelCase or snake_case as captured)
> - **Derived** — computed from other fields at read time
> - **Format** — accepted / returned shape, constraints, and examples
> - **ID map** — how the value is used across endpoints

---

## 1. Room Schemas

### 1.1 `RoomCreate` (request)

| Field | Type | Origin | Format / Constraints | Used for | ID relationships |
|---|---|---|---|---|---|
| `name` | `str` | Custom field; **prefill source** = Nuveq VisitorDoor `name` (e.g. `"RUANG MEETING 1 GEDUNG A"`). Client-overridable. | DB `VARCHAR(255)`. No Pydantic min/max. | Human label on the docs UI and in webhook notifications. Never sent upstream. | — |
| `site_id` | `int` | Original | `GET /nuveq/sites` → `Site.id` (e.g. `167`). No negative guard. | Forwarded as `CreateVisitorDto.siteId` on every booking. Also used in `GET /nuveq/controllers` and `GET /nuveq/lift-groups` filters. | FK-ish to upstream `Site.id`; stored on `TapEvent.site_id` from webhooks. |
| `controller_id` | `int` | Original | `GET /nuveq/controllers` → `Controller.id` (e.g. `2228`). | Stored for context. **Never used in any Nuveq call today.** | Copy of `NuveqVisitorDoor.controllerId` on the same door. |
| `door_number` | `int` | Original | `NuveqVisitorDoor.doorNumber` (e.g. `1`). | Stored for context. Would pair with `controller_id` for upstream door commands (not implemented). | Composite `(controller_id, door_number)` is the upstream physical-door key. |
| `door_id` | `int` | **Authoritative — Original** | `GET /nuveq/doors` → `VisitorDoor.id` (e.g. `3523`). DB `UNIQUE`, indexed. | Becomes `CreateVisitorDto.allowedDoorIds: [door_id]` — **the only door grant sent to Nuveq**. | `POST /rooms` / `PATCH /rooms` reject duplicates with 409. Conceptually matches webhook `door_id`, but webhook resolution uses `card_no`, not `door_id`. |
| `lift_group_id` | `int` | Original | `GET /nuveq/lift-groups?siteId=` → `id` (e.g. `630` = "Full Access"). Default `630`. | Forwarded as `CreateVisitorDto.liftGroupId` — controls lift/floor access. | Per-room copy of a per-site Nuveq entity. |
| `grace_minutes` | `int` | Custom | Default `15`. DB `Integer`. | `expires_at = visit_start + grace_minutes`. Enforced by the 60 s no-show expiry job. | Per-room, not global. |
| `is_active` | `bool` | Custom | Default `True`. | `False` → `current_status = MAINTENANCE` and `POST /bookings` on that room returns 409. | — |

### 1.2 `RoomUpdate` (request)

All fields `Optional`. Same origin/format rules as `RoomCreate`. `door_id` uniqueness is re-checked only when it is included in the patch.

### 1.3 `RoomResponse`

| Field | Type | Origin | Format / Constraints | Used for | ID relationships |
|---|---|---|---|---|---|
| `id` | `str` | Custom | `generate_uuid("rm_")` → `"rm_" + 12 hex`. DB `VARCHAR(32)` PK. | Path param `/rooms/{room_id}`. **FK target** of `Booking.room_id`. | Parent of `Booking.room_id`; echoed in `ClientWebhookNotification.room_id`. |
| `current_status` | `RoomStatus` enum | **Derived** | `AVAILABLE` / `BOOKED` / `IN_USE` / `EXPIRED` / `MAINTENANCE`. Default `AVAILABLE`. | Computed on every read by `RoomService.derive_room_status`. | Pairs with `active_booking_id`. |
| `active_booking_id` | `Optional[str]` | **Derived** | `Booking.id` (`bk_…`) of the booking driving the status, or `null`. | NOTE: name is misleading — it holds a *booking* id, not a room id. | Points at `Booking.id`. |
| `created_at` / `updated_at` | `datetime` | Custom | tz-aware UTC. `onupdate=utc_now`. | Bookkeeping. | — |

---

## 2. Booking Schemas

### 2.1 `BookingCreate` (request)

| Field | Type | Origin | Format / Constraints | Used for | ID relationships |
|---|---|---|---|---|---|
| `room_id` | `str` | Custom | `rm_…` id from `Room.id`. 404 if not found. | Resolves the target room. | **FK** → `Room.id`. |
| `booker_name` | `str` | Custom field; **original value** sent upstream | `2–255` chars. DB `VARCHAR(255)`. | Sent as `CreateVisitorDto.name` → `Visitor.name` at the reader. Surfaces in webhook `user_name`. | — |
| `booker_email` | `Optional[EmailStr]` | Custom field; **original value** sent upstream | RFC email format. DB `VARCHAR(255)`. | `CreateVisitorDto.email` (optional upstream). Used for QR delivery. | — |
| `booker_phone` | `Optional[str]` | Custom field; **original value** sent upstream | DB `VARCHAR(50)`. No pattern enforced. | `CreateVisitorDto.phone`. | — |
| `visit_start` | `datetime` | Custom field; **original value** sent upstream | ISO-8601 with tz. Naive values coerced to UTC. | Access window at the reader; base for `expires_at`; overlap check input. | — |
| `visit_end` | `datetime` | Custom field; **original value** sent upstream | ISO-8601 with tz. Must be `> visit_start` (409 otherwise). | As above; also the auto-check-out cutoff. | — |
| `notes` | `Optional[str]` | Custom | DB `Text`. | Stored only. **Never sent to Nuveq.** | — |

### 2.2 `BookingResponse`

| Field | Type | Origin | Format / Constraints | Used for | ID relationships |
|---|---|---|---|---|---|
| `id` | `str` | Custom | `generate_uuid("bk_")` → `"bk_" + 12 hex`. DB `VARCHAR(32)` PK. | Path param `/bookings/{booking_id}` and `/bookings/{booking_id}/qr`. **FK target** of `TapEvent.booking_id`. | Child of `Room.id`; parent of `TapEvent.booking_id`. |
| `room_id` | `str` | Custom | `rm_…`. | Which room; matches `GET /bookings?room_id=` filter. | ↔ `Room.id`. |
| `credential_number` | `int` | **Hybrid** — generated here, **is** the upstream `credentialNumber` | `random.randint(10_000_000, 99_999_999)` — 8 digits. DB `INTEGER UNIQUE INDEXED`. Retried ≤20× against `bookings.credential_number`. | QR payload; the credential the reader validates; **the join key from webhook `card_no` to this booking**. | ↔ webhook `card_no`; input to `QrService`; echoed in `ClientWebhookNotification.credential_number`. |
| `visitor_id` | `Optional[int]` | Original | `CreateVisitorResult.visitorId`. Nullable; not indexed. | Stored only. Nuveq has no visitor DELETE, so the record leaks by design. | Upstream `Visitor.id`. |
| `visitor_registration_id` | `Optional[int]` | Original | `CreateVisitorResult.visitorRegistrationId`. Nullable; indexed. | **Revoke handle**: `DELETE /api/visitors/registrations/{id}` on cancel and on no-show expiry. | Upstream `VisitorRegistration.id`. |
| `booker_name` / `booker_email` / `booker_phone` | `str` / `Optional[str]` / `Optional[str]` | Custom fields; original values | DB `VARCHAR(255/255/50)`. | Display. | — |
| `visit_start` / `visit_end` | `datetime` | Custom fields; original values | tz-aware in DB; both indexed. | Access window. | — |
| `expires_at` | `datetime` | **Custom — derived** | `visit_start_utc + timedelta(minutes=room.grace_minutes)`. DB indexed. | Scheduler predicate `expires_at <= now` for `EXPIRED`. | Derived from `visit_start` + `Room.grace_minutes`. |
| `status` | `BookingStatus` enum | Custom | `BOOKED` / `CHECKED_IN` / `CHECKED_OUT` / `AUTO_CHECKED_OUT` / `EXPIRED` / `CANCELLED`. DB enum indexed. | Lifecycle. Drives `Room.current_status`. | — |
| `checked_in_at` | `Optional[datetime]` | **Derived** | Webhook `timestamp` of first `Valid visitor` + `Entry` with matching `card_no`. | First entry timestamp. Set once. | From `TapEvent`. |
| `checked_out_at` | `Optional[datetime]` | **Derived** | Webhook `timestamp` of `Exit` tap **or** `now()` from `check_auto_checkout`. | End of visit. | — |
| `notes` | `Optional[str]` | Custom | DB `Text`. | — | — |
| `qr_data_uri` | `Optional[str]` | Custom | `data:image/png;base64,…`. QR version 1, ERROR_CORRECT_M. | Inline HTML / mobile render. | Derived from `credential_number`. |
| `qr_download_url` | `Optional[str]` | Custom | Relative path `/api/v1/bookings/{booking.id}/qr`. | Direct PNG download. | Embeds `Booking.id`. |
| `created_at` / `updated_at` | `datetime` | Custom | tz-aware UTC. | Bookkeeping. | — |

### 2.3 `BookingQrResponse`

Defined but **never used** by a router. `GET /bookings/{booking_id}/qr` returns raw `image/png`.

| Field | Type | Notes |
|---|---|---|
| `booking_id` | `str` | `Booking.id` (`bk_…`). |
| `credential_number` | `int` | Encoded in the QR image. |
| `qr_data_uri` | `str` | Base64 PNG. |

---

## 3. Webhook Schemas

### 3.1 `NuveqWebhookPayload` — **100% Original (upstream wire format, snake_case)**

Received at `POST /api/v1/webhooks/nuveq/{secret_token}`.

| Field | Type | Upstream source | Format / Constraints | Used for | ID relationships |
|---|---|---|---|---|---|
| `uuid` | `str` | Event UUID (required). | No regex; DB `VARCHAR(64)` unique indexed. | **Idempotency key** → `IdempotencyRecord.key` and `TapEvent.uuid`. | PK of `idempotency_records`; unique key of `tap_events`. |
| `mac` | `Optional[str]` | Controller MAC (`"E03C1CB330945601"`). | DB `VARCHAR(32)`. | Audit only. `TapEvent.mac`. | Identifies controller; **not** linked to `Room.controller_id`. |
| `owner_id` | `Optional[int]` | Nuveq account/tenant (demo `174`). | — | **Not stored.** Would be multi-tenant routing key. | No table link. |
| `owner_name` | `Optional[str]` | Account name. | — | Not stored. | — |
| `site_id` | `Optional[int]` | Site the event occurred at. | — | Stored on `TapEvent.site_id`. **Not used for routing.** | Mirrors `Room.site_id` but no lookup performed. |
| `site_name` | `Optional[str]` | Site display name. | — | Not stored. | — |
| `card_id` | `Optional[int]` | Credential/staff-card id. **Always `0` for visitor events.** | Default `0`. | Not read. Deliberately ignored (visitor namespace). | — |
| `card_no` | `Optional[int]` | **== registration's `credentialNumber`.** | Default `0`; guard requires `> 0`. | **The join key.** `Booking.credential_number == payload.card_no`. | FK-equivalent → `bookings.credential_number` (unique, indexed). |
| `door_id` | `Optional[int]` | Door where tap happened. | Default `0`. | Stored on `TapEvent.door_id` (indexed) for **audit only**. | Mirrors `Room.door_id`; **not used to resolve the room** (resolution is by `card_no`). |
| `name` | `str` | Event name. Required. | Exact literal match. Accepted: `"Valid visitor"`, `"Valid access"`, `"Invalid access"`, `"Manual release"`, `"Door never opened"`, `"Controller online/offline"`. DB `VARCHAR(100)`. | Gate for the state machine. | — |
| `direction` | `Optional[str]` | `"Entry"` / `"Exit"` / `"Status"`. | Free-form; code normalizes to lower before compare. DB `VARCHAR(20)`. | Check-in vs check-out signal. | Stored on `TapEvent.direction`. |
| `timestamp` | `Optional[datetime]` | ISO instant (`"2026-10-04T15:40:00.000Z"`). | Pydantic-parsed; fallback `datetime.now(timezone.utc)`. | Source of `checked_in_at` / `checked_out_at`. | — |
| `timezone` | `Optional[str]` | IANA tz, e.g. `"Asia/Jakarta"`. | — | Not stored. | — |
| `visitor` | `Optional[bool]` | `true` for visitor events. | Nullable (Status events send `null`). | **Not read** — code keys off `name`, not `visitor`. | — |
| `visitcheckin` | `Optional[bool]` | Nuveq's own visit check-in flag. | — | **Not read anywhere.** Declared for future use. | — |
| `user_name` | `Optional[str]` | Person on the credential. | — | Not stored (`booker_name` is authoritative). | — |
| `email` | `Optional[str]` | Visitor email from credential. | — | Not stored. | — |
| `type` | `Optional[str]` | Door/controller display name. | — | Not stored. | — |
| `alarmevent` | `Optional[bool]` | Alarm flag. | — | Not stored. | — |
| `level` | `Optional[int]` | Alarm severity. | — | Not stored. | — |
| *(extra fields)* | `any` | `commShiftId, dept_id, dept, post_id, post, staff_no, date, time, user_id, user_photo, plateId, platePhoto, snapshotKey, snapshotPhoto, created_at, updated_at, muster` | `model_config = {"extra": "allow"}` | Accepted silently; persisted inside `TapEvent.raw_payload` via `payload.model_dump_json()`. | — |

### 3.2 `WebhookAckResponse` — **Custom**

| Field | Type | Constraints | Meaning |
|---|---|---|---|
| `received` | `bool` | default `true` | Always `true` on 200. |
| `uuid` | `str` | required | Echo of `payload.uuid`. |
| `message` | `str` | default `"Event accepted"` | Actual values: `"Duplicate event ignored"` / `"Event processed successfully"`. |
| `processed` | `bool` | default `true` | `false` only for a duplicate `uuid`. |

> **Note:** `API_SPEC.md` §4.1 documents only `{received, uuid}` — `message` and `processed` are undocumented additions.

### 3.3 `ClientWebhookNotification` — **100% Custom (outbound push)**

| Field | Type | Format / Constraints | Used for | ID relationships |
|---|---|---|---|---|
| `event_type` | `str` | Literal `"booking_status_changed"` is the only value **ever emitted**. `"room_status_changed"` is in the description but **never produced**. | Client-side state sync. | — |
| `room_id` | `str` | `rm_…` | Which room. | ↔ `Room.id`. |
| `room_status` | `RoomStatus` enum | `AVAILABLE` / `BOOKED` / `IN_USE` / `MAINTENANCE`. `EXPIRED` is in the enum but **never emitted**. | Client room-state sync. | — |
| `booking_id` | `Optional[str]` | `bk_…` | Booking that changed. | ↔ `Booking.id`. |
| `booking_status` | `Optional[BookingStatus]` | New booking state. | Booking lifecycle sync. | — |
| `credential_number` | `Optional[int]` | 8-digit int. | Join clue for the client to correlate with its own access logs. | ↔ `Booking.credential_number`; ↔ webhook `card_no`. |
| `tap_event_name` | `Optional[str]` | Raw `payload.name` (e.g. `"Valid visitor"`). | Set **only** on webhook-driven transitions, not by the scheduler. | — |
| `tap_direction` | `Optional[str]` | Raw `payload.direction` casing. | Webhook path only. | — |
| `timestamp` | `datetime` | `default_factory=datetime.utcnow` → **naive** UTC (py3.12 deprecated). Scheduler paths override with `datetime.now(timezone.utc)`. | Event time. | — |

> **Security note:** the schema docstring calls `secret` an "HMAC signature" key, but it is sent as a **plaintext header** (`X-Webhook-Secret`), not an HMAC. Broadcast goes to every `is_active == true` config row; failures are logged, never retried.

### 3.4 `ClientWebhookConfigCreate` / `ClientWebhookConfigResponse` — **Custom**

| Field | Type | Format / Constraints | Used for |
|---|---|---|---|
| `url` | `str` | DB `VARCHAR(512)`. **No URL validation** — `file://` and `http://localhost` are accepted. | Outbound target. |
| `secret` | `Optional[str]` | DB `VARCHAR(255)`. | Echoed back in plaintext in the response. Sent as `X-Webhook-Secret` on every push. |
| `is_active` | `bool` | Default `true`. | Only `true` rows receive notifications. |
| `id` | `str` (response only) | `generate_uuid("cwh_")` → `"cwh_" + 12 hex`. | **There is no per-id route.** Only `POST` (create) and `GET` (list) exist. Each create adds a new row; all active rows are notified. |

---

## 4. Nuveq Proxy Schemas (passthrough — **100% Original upstream, camelCase preserved**)

### 4.1 `NuveqSite` ← `GET /api/sites`

| Field | Type | Upstream | Notes |
|---|---|---|---|
| `id` | `int` | `Site.id` (e.g. `167`) | **This is the value clients copy into `Room.site_id`.** |
| `name` | `str` | `Site.name` (upstream includes trailing whitespace, e.g. `"GEDUNG A "`) | Prefill candidate for room naming. |
| `contactName` | `Optional[str]` | Same-named upstream field. | — |
| `contactEmail` | `Optional[str]` | Same-named upstream field. | — |
| `city` | `Optional[str]` | Same-named upstream field. | — |
| `country` | `Optional[str]` | Same-named upstream field. | — |
| *(extras allowed)* | | `contactPhone, address, address2, state, postcode` | Passed through verbatim. |

### 4.2 `NuveqController` ← `GET /api/controllers`

| Field | Type | Upstream | Notes |
|---|---|---|---|
| `id` | `int` | `Controller.id` (e.g. `2228`) | Copy into `Room.controller_id`. |
| `name` | `str` | `Controller.name`. | — |
| `description` | `Optional[str]` | `Controller.description`. | — |
| `mac` | `Optional[str]` | Controller MAC — links to webhook `mac`. | — |
| `mode` | `Optional[str]` | `"SingleDoor"` / `"TwoDoor"` / `"Lift"`. **Not constrained to an enum in code.** | Do not rely on a fixed set of values. |
| `site` | `Optional[dict]` | Nested `{id, name}`. Typed as bare `dict`, not `NuveqSite`. | Client-side filtering for `?site_id=` happens on `c["site"]["id"]`. |

> **Note:** `GET /api/controllers?site_id=` filtering is done in **Python**, not forwarded to upstream.

### 4.3 `NuveqVisitorDoor` ← `GET /api/visitors/doors` — **authoritative room-mapping source**

| Field | Type | Upstream | Notes |
|---|---|---|---|
| `id` | `int` | `VisitorDoor.id` (e.g. `3523`) | Copy into `Room.door_id`. |
| `name` | `str` | `"RUANG MEETING 1 GEDUNG A"` | Prefill for `Room.name`. |
| `description` | `Optional[str]` | — | — |
| `controllerId` | `int` | `2228` | Copy into `Room.controller_id`. |
| `doorNumber` | `int` | `1` | Copy into `Room.door_number`. |
| `siteId` | `int` | `167` | Copy into `Room.site_id`. Cross-check equals `Site.id`. |
| *(extras allowed)* | | `weeklySchedule{number}` | — |

### 4.4 `NuveqLiftGroup` ← `GET /api/visitors/lift-groups?siteId=`

| Field | Type | Upstream | Notes |
|---|---|---|---|
| `id` | `int` | e.g. `630` | Copy into `Room.lift_group_id`. |
| `description` | `str` | e.g. `"Full Access"`. | — |

### 4.5 `NuveqWebhookSetupRequest` / `NuveqWebhookSetupResponse`

| Field | Type | Upstream | Notes |
|---|---|---|---|
| `webhook_url` | `str` | Maps to `webhookLink`. **No URL validation.** Operator must include the secret path segment. | — |
| `enable` | `bool` | `enable`. | — |
| `backup_webhook_url` | `Optional[str]` | `webhookLink2`. Sent only when truthy. | — |
| `owner_id` | `Optional[int]` (response) | `data.ownerId`. Defined in schema but **never returned by the route** (no `response_model`). | — |
| `webhook_link` | `str` (response) | `data.webhookLink`. Same caveat as above. | — |

> **Note:** `POST /nuveq/setup-webhook` has no `response_model` and returns the raw upstream envelope `{"error":0,"message":"Success","data":{…}}`.

---

## 5. Common Envelopes

### 5.1 `ApiResponse[T]` — **defined but never used by any route**

| Field | Type | Notes |
|---|---|---|
| `success` | `bool` | Default `true`. |
| `message` | `str` | Default `"Success"`. |
| `data` | `Optional[T]` | Generic payload. |

### 5.2 Actual error envelope (hand-built in `app/main.py` exception handlers)

```json
{ "success": false, "message": "<str>", "details": "<Any|null>" }
```

- **404** `ResourceNotFoundException`
- **409** `ResourceConflictException`
- **400** `MiddleServiceException`
- **502** `NuveqApiError` — adds `"upstream_status": <int>`
- **401** auth failure — FastAPI default `{"detail": "..."}` (does **not** match the envelope above)
- **422** validation error — FastAPI default (does **not** match the envelope)

---

## 6. Database Models (SQLAlchemy)

| Model | Table | PK | Prefix | Unique / Indexed | Cascade |
|---|---|---|---|---|---|
| `Room` | `rooms` | `id` | `rm_` | `door_id` unique indexed; `site_id`, `controller_id`, `door_id` indexed | — |
| `Booking` | `bookings` | `id` | `bk_` | `credential_number` unique indexed; `room_id`, `visitor_registration_id`, `visit_start`, `visit_end`, `expires_at`, `status` indexed | — |
| `TapEvent` | `tap_events` | `id` | `tap_` | `uuid` unique indexed; `door_id`, `card_no` indexed | `booking_id` FK → `Booking.id` nullable |
| `IdempotencyRecord` | `idempotency_records` | `key` | — | PK is `key` (webhook `uuid`) | — |
| `ClientWebhookConfig` | `client_webhook_configs` | `id` | `cwh_` | — | No FK to `Room` or `Booking` (global fan-out). |

---

## 7. Cross-Endpoint ID Map

```
rm_<uuid12>  Room.id
  ├── POST /bookings          body.room_id
  ├── GET /bookings?room_id=  filter
  ├── DELETE /rooms/{id}      cascades to Bookings (hard delete)
  └── ClientWebhookNotification.room_id

bk_<uuid12>  Booking.id
  ├── GET /bookings/{id}
  ├── DELETE /bookings/{id}
  ├── GET /bookings/{id}/qr   filename = qr-{id}.png
  ├── Room.active_booking_id
  └── TapEvent.booking_id

credential_number  (8-digit int, unique)
  ├── Booking.credential_number
  ├── webhook payload.card_no   (join key at ingestion)
  └── ClientWebhookNotification.credential_number

cwh_<uuid12>  ClientWebhookConfig.id
  └── GET /webhooks/client-config (list only; no per-id route)

tap_<uuid12>  TapEvent.id
  └── FK → Booking.id (nullable)

IdempotencyRecord.key
  └── webhook payload.uuid
```

---

## 8. Quick Reference — What's Custom vs Original by Domain

| Domain | Custom fields / concepts | Original (upstream) fields used as-is |
|---|---|---|
| **Rooms** | `id` (`rm_…`), `current_status`, `active_booking_id`, `grace_minutes`, `is_active`, `name` (overridable label) | `site_id`, `controller_id`, `door_number`, `door_id`, `lift_group_id` |
| **Bookings** | `id` (`bk_…`), `credential_number` (generated), `expires_at`, `status`, `checked_in_at`, `checked_out_at`, `qr_data_uri`, `qr_download_url`, `notes`, `booker_*` | `visitor_id`, `visitor_registration_id`, `visit_start`, `visit_end` |
| **Webhooks (inbound)** | `uuid` (idempotency), `processed` flag, `TapEvent` DB row | All payload fields (`mac`, `site_id`, `card_no`, `door_id`, `name`, `direction`, `timestamp`, etc.) |
| **Webhooks (outbound)** | `event_type`, `room_id`, `room_status`, `booking_id`, `booking_status`, `credential_number`, `tap_event_name`, `tap_direction`, `timestamp` | Nothing — fully custom envelope |
| **Nuveq proxy** | `NuveqWebhookSetupRequest` wrapper (snake_case in, camelCase out) | All `NuveqSite`, `NuveqController`, `NuveqVisitorDoor`, `NuveqLiftGroup` fields are passthrough |
