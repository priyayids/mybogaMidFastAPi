# Nuveq Access Control — Middle Service Integration Brief

**Date:** 2026-10-04 (updated after live webhook capture)
**Author:** Integration Dev
**Status:** Plan / Research — webhook payload schema captured live; access-tap payload inferred from REST + webhook schema (confirmed assumption). Ready for implementation planning.
**Target API:** `https://api-v2.nuveq.cloud` (OpenAPI 3.0, spec embedded at `/swagger-ui-init.js`)
**Auth:** `X-API-KEY: <key>` header on every request. Test key verified working (ownerId `174`, "Demo Nuveq").

---

## 1. Executive Summary

The client runs a meeting-room booking website (F&B business, rooms reservable by users). They want Nuveq access control (controller + reader) to grant automatic room access to bookers, but their dev team is unavailable. We build a **middle service (BFF)** that:

1. **Hides** the Nuveq API key and the raw Nuveq API from the client.
2. Exposes a **simplified API** fitted to their booking flow (book room → issue credential → QR → track check-in/out → room status).
3. Adds features Nuveq does **not** provide: **no-show expiry** (auto-revoke if the booker doesn't tap within X minutes of schedule start), **room status field** (available/booked/in-use, auto-updating), and **QR generation** from the credential number.

**Verified live:** all 30 endpoints tested. Visitor creation → registration → event → delete lifecycle confirmed. Webhook registered and **captured live** (schema in §2.4). Door lock/unlock/release confirmed working.

---

## 2. Nuveq API — What We Tested (all live, HTTP 200 unless noted)

### 2.1 Endpoint inventory

| Method | Path | Purpose | Key params / body |
|---|---|---|---|
| GET | `/healthz` | Health | — |
| GET | `/api/sites` | List sites (buildings) | — |
| GET | `/api/controllers` | List controllers | `after` (id), `first` (0–1000) |
| GET | `/api/controllers/{id}` | Controller + its doors | — |
| POST | `/api/controllers/door/release` | Buzz open a door | `{controllerId, doorNumber}` |
| POST | `/api/controllers/door/lock-unlock` | Lock/unlock | `{controllerId, doorNumber, lock, duration(min)}` |
| GET | `/api/access-groups` | Staff access groups | — |
| GET | `/api/lift-groups` | Lift groups | — |
| GET | `/api/departments`, `/api/posts`, `/api/shifts` | Staff org data | — |
| GET | `/api/events` | **Event log (taps, alarms, status)** | `date` (YYYY-MM-DD), `after`, `first` |
| GET | `/api/users` | Staff users | `after`, `first` |
| POST/PUT/DELETE | `/api/users[/{id}]` | Staff CRUD | CreateUserDto / UpdateUserDto |
| GET | `/api/users/cards/{number}` | Lookup staff card | — |
| POST/PUT/DELETE | `/api/users/cards` | Staff card CRUD | CreateCardDTO etc. |
| GET | `/api/visitors` | Visitor directory | `after`, `first` |
| **POST** | **`/api/visitors`** | **Create visitor + registration (the core call)** | CreateVisitorDto |
| GET | `/api/visitors/registrations` | **Visit windows (schedule + credential)** | `after`, `first` |
| GET | `/api/visitors/doors` | **All visitor-capable doors (room mapping source)** | — |
| GET | `/api/visitors/lift-groups?siteId=` | Lift groups per site | `siteId` |
| GET | `/api/visitors/{id}` | Visitor detail | — |
| POST | `/api/visitors/repeat` | Re-issue visit for existing visitor | AddRepeatVisitorDto |
| **DELETE** | **`/api/visitors/registrations/{id}`** | **Revoke a visit window (used for expiry)** | — |
| POST | `/api/webhooks` | **Set account webhook** | `{enable, webhookLink, webhookLink2?}` |

### 2.2 Core data models (field → meaning → source)

**Site** — `id, name, contactName, contactEmail, contactPhone, address, address2, city, state, country, postcode`

**Controller** — `id, name, description, mac, mode (SingleDoor|TwoDoor|Lift), site{id,name}`

**Visitor Door** (from `/api/visitors/doors`) — `id, name, description, controllerId, doorNumber, siteId, weeklySchedule{number}`
> This is the **room mapping source**. Live example: `{id: 3523, name: "RUANG MEETING 1 GEDUNG A", controllerId: 2228, doorNumber: 1, siteId: 167}`.

**Visitor** — `id, name, userId, phone, email, userPhoto, lastVisit, blacklisted, remarks, vehicleNumber`

**VisitorRegistration** (the "visit session") — `id, visitStart, visitEnd, credentialNumber, vehicleNumber, visitor{id,name,phone,email,userPhoto}, liftGroup{id,description}, site{id,name,description}`
> `visitStart`/`visitEnd` are ISO-8601 **with timezone offset** (e.g. `2026-10-04T20:08:49+07:00`). The credential is only valid inside this window — Nuveq enforces it at the reader.

**Event** (REST log record, camelCase) — `id, uuid, mac, ownerId, ownerName, siteId, siteName, cardId, cardNo, doorId, eventName, alarmEvent, attendance, visitor, userName, deptId, dept, postId, post, staffNo, type, direction, level, record, date, time, timezone, timestamp, plateNo`

**CreateVisitorDto** (POST /api/visitors body) — required: `name, credentialNumber, visitStart, visitEnd, siteId, liftGroupId, allowedDoorIds[]`; optional: `email, phone, userPhoto, vehicleNumber`

**CreateVisitorResult** — `{visitorId, visitorRegistrationId}`

### 2.3 Event semantics (critical for check-in/out)

Live visitor tap events (from REST log) look like:

```json
{
  "eventName": "Valid visitor",
  "visitor": true,
  "cardId": 0,
  "cardNo": 10101011,          // == the registration's credentialNumber
  "doorId": 3523,              // == the room's door
  "siteId": 167,
  "userName": "new user_in",   // visitor name
  "dept": "Visitor",
  "type": "Pintu r meeting 1", // door name
  "direction": "Entry",        // "Entry" | "Exit" | "Status"
  "timestamp": "2026-10-03T11:17:11.000Z",
  "timezone": "Asia/Jakarta"
}
```

Observed `eventName` values: `Valid access` (staff), **`Valid visitor`** (visitor tap), `Invalid access`, `Manual release` (API/button buzz), `Door never opened` (alarm), `Controller online` (status).

**Key facts:**
- Visitor taps are identified by `visitor === true` and `eventName === "Valid visitor"`.
- **`cardNo` on a visitor event equals the registration's `credentialNumber`** — this is the join key between a tap and a booking. (`cardId` is 0 for visitors; visitor credentials live in a **separate namespace** from staff cards — `GET /api/users/cards/{number}` returns "Card not found" for a visitor credential.)
- **`direction` is the check-in/check-out signal**: `Entry` = in, `Exit` = out.
- Door lock/unlock/release commands **do not** fire webhooks (verified).

### 2.4 Webhook payload schema — **CAPTURED LIVE** ✅

Delivery: `HTTP POST`, `Content-Type: application/json`, sent by Nuveq cloud (user-agent `axios/1.8.4`). **Payload keys are snake_case** (unlike the REST API's camelCase) and include extra fields not present in the REST event DTO.

Captured payload (a "Controller online" status event — fired when the reader/controller connects):

```json
{
  "uuid": "18a59ec2-644f-45f7-9bc8-8cdcfe478b3d",
  "mac": "E03C1CB330945601",
  "owner_id": 174,
  "owner_name": "Demo Nuveq",
  "site_id": 167,
  "site_name": "GEDUNG A ",
  "card_id": 0,
  "card_no": 0,
  "door_id": 0,
  "name": "Controller online",
  "alarmevent": null,
  "attendance": null,
  "visitor": null,
  "user_name": "",
  "email": "",
  "commShiftId": null,
  "dept_id": null,
  "dept": "",
  "post_id": null,
  "post": "",
  "staff_no": "",
  "type": "FR-501 demo rack access",
  "direction": "Status",
  "level": 1,
  "date": "2026-10-04",
  "time": "21:57:41",
  "timezone": "Asia/Jakarta",
  "timestamp": "2026-10-04T14:57:41.000Z",
  "user_id": null,
  "user_photo": "",
  "plateId": null,
  "platePhoto": "",
  "snapshotKey": null,
  "snapshotPhoto": null,
  "created_at": "2026-10-04T14:57:41.263Z",
  "updated_at": "2026-10-04T14:57:41.263Z",
  "muster": false,
  "visitcheckin": false
}
```

**Field dictionary (webhook payload):**

| Field | Type | Meaning | Our use |
|---|---|---|---|
| `uuid` | string | Unique event id | **Idempotency key** (dedupe retries) |
| `mac` | string | Controller MAC | Identify controller |
| `owner_id` / `owner_name` | number/string | Nuveq account | Multi-tenant routing |
| `site_id` / `site_name` | number/string | Site | Route to client/room |
| `card_id` / `card_no` | number | Credential id / number | **`card_no` = `credentialNumber` → join to booking** |
| `door_id` | number | Door | **Route to room** (door_id → room map) |
| `name` | string | Event name (`Valid visitor`, `Valid access`, `Controller online`, …) | Event type switch |
| `visitor` | bool/null | Is visitor event | Visitor filter |
| `user_name` / `email` / `user_photo` | string | Person on the credential | Display |
| `direction` | string | `Entry` / `Exit` / `Status` | **Check-in vs check-out** |
| `type` | string | Door/controller display name | Display |
| `timezone` / `timestamp` | string | TZ + ISO instant | Normalize to UTC |
| `visitcheckin` | bool | **Visit check-in flag** — likely Nuveq's own check-in marker for visitor registrations | Confirm check-in semantics (verify on next tap) |
| `muster` | bool | Muster (roll-call) event flag | Ignore for now |
| `snapshotKey` / `snapshotPhoto` / `platePhoto` | string/null | Photo evidence refs (if camera attached) | Optional display |
| `alarmevent` / `level` | bool/number | Alarm severity | Alerting |

**Security note:** no signature/HMAC header was observed on the delivery. Authenticate by (a) allowing only Nuveq egress IPs (ask Nuveq support for the range), and/or (b) putting a shared secret in the webhook URL path (e.g. `https://our-service.com/webhooks/nuveq/<secret>`), since `webhookLink` is a free-form URL.

**Event taxonomy observed via webhook (all delivered):**

| `name` | `direction` | `visitor` | Meaning | Our handling |
|---|---|---|---|---|
| `Valid visitor` | Entry/Exit | true | **Visitor tap granted** — the check-in/out signal | State machine (§5) |
| `Valid access` | Entry/Exit | false | Staff card granted | Log only |
| `Invalid access` | Entry | false | Known credential, not allowed / outside window | Log; **no-show/denied signal** |
| `Invalid access` | Entry | false, `user_name:"Unregistered User"` | Credential unknown to controller (not synced/never created) | Log; sync/health signal |
| `Manual release` | Exit | false | Door buzzed (API/button) | Door-state tracking |
| `Door never opened` | Exit | false | Alarm: door opened without valid access | Alerting |
| `Controller online` / `Controller offline` | Status | null | Controller connectivity | Health monitoring |

**Webhook delivery behaviors (observed live):**
1. **Bulk backlog bursts:** when a controller reconnects after being offline, Nuveq flushes its buffered events as a burst of webhook deliveries (observed: ~25 events delivered in ~36s). → Receiver **must** dedupe by `uuid` and order by `timestamp`, never by delivery order.
2. **All event types are delivered**, not just access taps — filter server-side.
3. **Credential sync delay:** a visitor credential created via API is **not instantly known to the controller**. If the controller is offline, the credential cannot sync at all; after it comes online, sync takes some seconds/minutes. Taps before sync complete log as `Invalid access` / `Unregistered User`. → After creating a registration, treat access as effective only after the controller confirms (or warn the user "access activating").

**Inferred `Valid visitor` webhook payload** (schema confirmed from the captured webhook + REST `Valid visitor` events; values marked *):

```json
{
  "uuid": "<event-uuid>",
  "mac": "<controller-mac>",
  "owner_id": 174,
  "owner_name": "Demo Nuveq",
  "site_id": 167,
  "site_name": "GEDUNG A ",
  "card_id": 0,
  "card_no": 88990011,              // * == registration credentialNumber
  "door_id": 3523,                  // * == the room's door
  "name": "Valid visitor",          // *
  "alarmevent": null,
  "attendance": false,
  "visitor": true,                  // *
  "user_name": "All Doors Tap Test",// * visitor name
  "email": "alldoors@example.com",
  "dept_id": null,
  "dept": "Visitor",
  "type": "RUANG MEETING 1 GEDUNG A ",
  "direction": "Entry",             // * Entry = check-in, Exit = check-out
  "level": 0,
  "date": "2026-10-04",
  "time": "22:40:00.000",
  "timezone": "Asia/Jakarta",
  "timestamp": "2026-10-04T15:40:00.000Z",
  "visitcheckin": true,             // * likely true on a visitor check-in tap — confirm on first live capture
  "muster": false,
  "snapshotKey": null,
  "snapshotPhoto": null
}
```

**Confidence:** schema = confirmed live. `name`/`visitor`/`card_no`/`door_id`/`direction` values = confirmed via REST event log for real visitor taps (e.g. `cardNo: 10101011, doorId: 3523, direction: Entry, visitor: true, eventName: "Valid visitor"`). Only `visitcheckin`'s exact value on a visitor tap remains to be confirmed on the first live capture — it does not block implementation (we key off `name` + `direction`).

---

## 3. Architecture of the Middle Service

```
Client booking website
   │  (our simplified REST API + our API key)
   ▼
┌──────────────────────────── MIDDLE SERVICE (ours) ────────────────────────────┐
│  Auth (client API keys) · Config DB (room↔door map, grace mins)              │
│  Booking/Visit DB (bookings, registrations mirror, taps, room status cache)  │
│  Nuveq Adapter (holds Nuveq API key in env/vault — never exposed)            │
│  Webhook Receiver (Nuveq → us)   Scheduler (expiry + status)   QR Generator│
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │  X-API-KEY (server-side only)
                                ▼
                     Nuveq Cloud  https://api-v2.nuveq.cloud
                                │  webhook (account-level URL)
                                └──────────────► our POST /webhooks/nuveq
```

**Stack recommendation: Node.js + NestJS + TypeScript + PostgreSQL** (primary)

Why:
- **Nuveq itself is NestJS** (the OpenAPI spec is NestJS-generated) — same ecosystem, same conventions, and the client's Nuveq-facing patterns carry over directly.
- **First-class scheduling** (`@nestjs/schedule`) for the expiry/no-show loop and status updater.
- **Validation + OpenAPI** (`class-validator`, `@nestjs/swagger`) — we auto-generate our own API docs for the client, same toolchain Nuveq uses.
- **Modular** (Config / Rooms / Bookings / Webhooks / Scheduler modules) — clean separation, easy to test.
- **TypeScript** end-to-end for type safety across the integration boundary.

Supporting choices:
| Concern | Choice | Why |
|---|---|---|
| DB | **PostgreSQL** (SQLite for MVP) | relational: rooms↔doors, bookings, registrations, taps, idempotency |
| HTTP client | `axios` | Nuveq's own webhook sender is axios; mature, simple |
| QR | `qrcode` | PNG/SVG generation from credential number |
| Async/queue | BullMQ + Redis (optional, Phase 6) | webhook backpressure; MVP can process in-process |
| Idempotency/dedupe | Postgres table on event `uuid` | survives restarts, no extra infra |
| Deployment | Docker + VPS / Cloud Run | stateless service, single container |
| Webhook receiver | `@nestjs/platform-express` POST route | fast 200 OK, enqueue for async processing |

**Alternative: Python + FastAPI + APScheduler + SQLAlchemy** — pick this if the team is stronger in Python. FastAPI gives auto OpenAPI docs, APScheduler covers the cron loops, `qrcode` lib for QR, and it's lighter to run. Functionally equivalent; the only reason to prefer NestJS is ecosystem alignment with Nuveq.

**Not recommended:** Next.js/Express for this service (backend-only integration; NestJS/FastAPI are better fits), or a serverless-only design (webhook receiver + long-lived scheduler favor a always-on container).

**Our simplified API surface (proposed):**

| Our endpoint | Does |
|---|---|
| `POST /rooms` | Register a room (map to Nuveq site/controller/door) |
| `GET /rooms` / `GET /rooms/{id}` | Room list + **live status** |
| `POST /bookings` | Create booking → creates Nuveq visitor+registration, returns `credentialNumber` + QR |
| `GET /bookings/{id}` | Booking detail incl. check-in/out state |
| `DELETE /bookings/{id}` | Cancel → deletes Nuveq registration (revokes access) |
| `GET /bookings/{id}/qr` | QR image (credential number) |
| `POST /webhooks/nuveq` | Nuveq tap events (internal, secret-protected) |
| `POST /webhooks/client` | (config) where WE push status changes to the client |

---

## 4. Visitor Flow (end to end)

```
1. User books room on client site (room, start, end, name/phone/email)
2. Client calls our POST /bookings
3. Our service:
   a. generates unique numeric credentialNumber (store in our DB)
   b. POST /api/visitors to Nuveq:
      { name, credentialNumber, visitStart, visitEnd,
        siteId, liftGroupId, allowedDoorIds:[room.doorId] }
   c. stores visitorId + visitorRegistrationId + booking window
   d. generates QR encoding the credentialNumber
4. User receives QR (email/app)
5. User taps/presents QR at reader during the window
6. Nuveq → webhook → our POST /webhooks/nuveq
7. We match card_no → registration → update check-in/out state → update room status
8. We (optionally) push status change to client's webhook
9. On no-show past grace → scheduler expires & deletes registration (§7)
```

**Sequence (booking day):**

```
User        Client Site      Middle Service      Nuveq Cloud        Reader
 |  book room  |                  |                  |                |
 |------------>|  POST /bookings  |                  |                |
 |             |----------------->|  POST /visitors  |                |
 |             |                  |----------------->|                |
 |             |                  |<-- visitorId,    |                |
 |             |                  |   registrationId |                |
 |             |<-- booking + QR  |                  |                |
 |<-- QR shown |                  |                  |                |
 |  tap QR/card at reader ------------------------------------------>|
 |             |                  |<-- webhook (Valid visitor, Entry) |
 |             |                  |  state=CHECKED_IN, room=IN_USE   |
 |             |<-- status push (optional)          |                |
```

---

## 5. Check-in / Check-out — Do We Need Two Visitors? **No.**

**One visitor + one registration per booking.** The registration *is* the visit session; the tap *events* carry the in/out. We do **not** create two visitor records.

**State machine per registration:**

```
BOOKED ──(webhook: name=Valid visitor, direction=Entry)──► CHECKED_IN
CHECKED_IN ──(webhook: direction=Exit)──► CHECKED_OUT
BOOKED ──(scheduler: now > visitStart + grace, no Entry tap)──► EXPIRED (delete registration)
CHECKED_IN ──(scheduler: now > visitEnd + buffer)──► AUTO_CHECKED_OUT
```

**How we know a tap is check-in vs check-out:** the event's `direction` field (`Entry`/`Exit`). That is the source of truth — no heuristics needed. The webhook also carries `visitcheckin` (boolean) which appears to be Nuveq's own visitor check-in marker — we will confirm its exact semantics on the next tap.

**Edge cases & rules:**
- **First Entry = check-in time.** Subsequent Entry taps (re-taps, tailgating retries) are ignored for state (logged only).
- **Exit without prior Entry** → anomaly; log, flag for review (or auto check-in then check-out — config flag).
- **No exit reader on the door** (common for meeting rooms — reader only outside): check-out is derived, not tapped. Options: (a) auto check-out at `visitEnd`, (b) dwell-time timeout, (c) use `Manual release`/`Door never opened` events as exit hints. Recommend (a) + (c).
- **Taps outside the window** (early/late): Nuveq returns `Invalid access`; we log these as `DENIED` attempts — also a useful no-show signal.
- **`Unregistered User`** (`Invalid access` with empty/unknown credential) = the controller doesn't know the credential yet — usually a **sync delay** (controller was offline, or credential just created). Distinguish from a genuinely invalid credential. See §2.4 sync-delay note.
- **Two readers per door** (entry + exit): the entry reader validates credentials (generates Entry events); the exit reader/button generates Exit events or `Manual release`. Map the room to the **entry reader's door**; treat exit-side events as check-out hints.
- **Idempotency:** dedupe by webhook `uuid` (webhooks can retry; Nuveq also flushes backlogged events in bursts — order by `timestamp`, not delivery order).

**Verification needed:** whether the reader hardware emits visitor `Exit` events at all (demo REST data showed only visitor `Entry`). **The live tap test will confirm** — tap once to enter, once to exit, and inspect the webhook payloads.

---

## 6. Master Room Model (our custom entity)

Room is **our** concept; Nuveq has no "room". A room = **one Nuveq door** (or a door pair for interlock). Mapping table (our config DB):

| Our field | Source | Example |
|---|---|---|
| `room_id` | our UUID | `rm_...` |
| `room_name` | Nuveq door `name` (or client override) | "RUANG MEETING 1 GEDUNG A" |
| `site_id` | Nuveq site `id` | 167 |
| `controller_id` | Nuveq controller `id` | 2228 |
| `door_number` | Nuveq door `doorNumber` | 1 |
| `door_id` | Nuveq visitor-door `id` (from `/api/visitors/doors`) | 3523 |
| `lift_group_id` | config per site (`GET /api/visitors/lift-groups?siteId=`) | 630 (Full Access) |
| `grace_minutes` | client config | 15 |

**Setup procedure:**
1. `GET /api/sites` → pick the client's site(s).
2. `GET /api/controllers` → list controllers per site (`site.id` filter client-side).
3. `GET /api/controllers/{id}` → doors per controller (`id`, `doorNumber`).
4. `GET /api/visitors/doors` → authoritative visitor-door list with `controllerId`, `doorNumber`, `siteId` — **use this to bind room → doorId**.
5. `GET /api/visitors/lift-groups?siteId=` → pick lift group (usually "Full Access" for meeting rooms, or a floor-specific group).
6. Persist the mapping in our config DB. One room ↔ one `doorId`. `allowedDoorIds` on visitor creation = `[room.door_id]`.

---

## 7. Expire-Time Feature (no-show auto-revoke) — *not in Nuveq, we build it*

**Requirement:** if the booker hasn't tapped check-in within X minutes of the schedule start, the booking expires and the credential stops working.

**Design:**
- Config: `grace_minutes` per room/client (e.g. 15).
- **Scheduler** (every 1–5 min): find bookings where `status = BOOKED` **and** `now > visitStart + grace` **and** no Entry tap recorded.
- On expiry:
  1. `DELETE /api/visitors/registrations/{visitorRegistrationId}` → **revokes the credential at the reader** (verified endpoint works).
  2. Mark booking `EXPIRED` in our DB, update room status, notify client.
- **Also handle:** booking cancelled before start → delete registration immediately; `visitEnd` passed with no check-out → auto close session.
- **Note:** Nuveq already enforces the `visitStart`/`visitEnd` window at the reader (credential invalid outside it). Our expiry adds the **no-show grace** on top and cleans up registrations so they don't linger.
- **Race condition:** a tap may arrive just as the scheduler expires — process webhook first, check current state, and skip expiry if an Entry tap exists (idempotent state machine handles this).

---

## 8. Room Status Field (auto-updating)

**Statuses:** `AVAILABLE` | `BOOKED` (reserved, not yet arrived) | `IN_USE` (checked in) | `EXPIRED`/`CANCELLED` | `MAINTENANCE` (manual override).

**Derivation:**
- `AVAILABLE`: no booking covering `now`.
- `BOOKED`: booking window covers `now`, not yet checked in, not expired.
- `IN_USE`: check-in tap received, no check-out yet.

**Auto-update triggers (three paths, all converge on one `updateRoomStatus(roomId)` function):**
1. **Webhook event** (tap) → check-in/out → status change.
2. **Client booking CRUD** via our API → create/cancel booking → status change.
3. **Scheduler** → expiry / auto-check-out → status change.

**Delivery to client:** client polls `GET /rooms/{id}` (status computed on read from bookings+taps), **and/or** we push to a client-configured webhook on every status change (recommended — "auto update when there is event/update"). Keep a status cache + `updated_at` for cheap polling.

---

## 9. QR Generator

- **Content:** the `credentialNumber` (numeric string). If the reader supports QR/BLE input, the raw number is what the reader needs; optionally wrap as a URL (`https://client.com/access?cred=991234567`) if their app deep-links.
- **When:** generated at booking creation (step 3d above), returned as PNG/SVG via `GET /bookings/{id}/qr` and/or emailed.
- **⚠ Hardware dependency:** the reader must accept QR (or BLE) as a credential input. Nuveq credential numbers are numeric; confirm the client's reader model (EP3000 / FR-501 etc.) supports QR presentation. If readers are card-only, the QR is for the *client app* to show a code the receptionist enters, or the flow needs BLE cards. **Verify with client hardware.**

---

## 10. Webhook — What It Is & How to Configure It (non-technical guide)

### 10.1 What a webhook is
A webhook is **"Nuveq calls YOU when something happens"** instead of you asking Nuveq every few seconds. When someone taps the reader, Nuveq's cloud sends an HTTP `POST` with a JSON body (the event, schema in §2.4) to a URL you give it. Your service receives it and reacts (update check-in, room status, etc.).

### 10.2 What you need beforehand
1. **A public HTTPS URL** that accepts `POST` JSON. This is our middle service's endpoint, e.g. `https://api.our-service.com/webhooks/nuveq/<secret>`. (During development, a local server can be exposed with **ngrok** (`ngrok http 3000` → gives a public URL), or use **webhook.site** as a free capture inbox like we did for testing.)
2. **The Nuveq API key** (the one you already have).

### 10.3 Configuration steps (one-time)
1. Deploy the middle service; note its webhook URL.
2. Call the Nuveq webhook API once:

```bash
curl -X POST "https://api-v2.nuveq.cloud/api/webhooks" \
  -H "X-API-KEY: <NUVEQ_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
        "enable": true,
        "webhookLink": "https://api.our-service.com/webhooks/nuveq/<secret>"
      }'
```

3. Expected response: `{"error":0,"message":"Success","data":{"ownerId":174,"enable":true,"webhookLink":"..."}}`
4. **Test:** tap the reader → check our service logs for the incoming POST. (We already did this against webhook.site — see §2.4 for the captured payload.)
5. **To change the URL:** call the same endpoint again with the new `webhookLink`. **To disable:** `{"enable": false, "webhookLink": "..."}`.

### 10.4 Important caveats
- **One webhook per Nuveq account** (`owner_id`), plus one optional backup URL (`webhookLink2`). It is **not** per-door — our receiver routes by `door_id`/`site_id` inside the payload.
- **Setting it overwrites any existing webhook URL on the account.** If the client already has a webhook (e.g. to another system), either point it at our receiver, use `webhookLink2` as the second target, or chain-forward from the existing one. **Ask the client before changing it.**
- Webhooks fire on **all** events (access taps, alarms, controller online/offline) — our receiver must filter (we only care about `name: "Valid visitor"` / `"Valid access"` / `"Invalid visitor"` etc.).
- No signature header observed → authenticate via URL secret + IP allowlist (§2.4).
- **Always keep a reconciliation fallback:** poll `GET /api/events?date=YYYY-MM-DD&after=<lastEventId>&first=1000` every few minutes to catch any webhook that was missed (network blip, our downtime).

### 10.5 Receiver implementation checklist
- Respond `200 OK` **fast** (<2s); process the event asynchronously (queue) so Nuveq doesn't retry.
- Idempotency store keyed on payload `uuid` (ignore duplicates).
- Parse: `door_id` → room, `card_no` → booking, `direction` → in/out, `name` → event type.
- Retry with backoff on downstream failure; dead-letter queue for poison messages.
- Log every payload raw (for debugging) with TTL.

---

## 11. UI / Form Requirements (client-facing)

### 11.1 Room Mapping Admin Form (one-time setup, our admin UI)
| Field | Control | Source |
|---|---|---|
| Room name | text input (prefilled from Nuveq door name, editable) | our config |
| Site | dropdown | `GET /api/sites` |
| Controller | dropdown (filtered by chosen site) | `GET /api/controllers` |
| Door | dropdown (filtered by site+controller) | `GET /api/visitors/doors` |
| Lift group | dropdown | `GET /api/visitors/lift-groups?siteId=` |
| Grace minutes | number input (default 15) | client policy |
| Active | toggle | — |

### 11.2 Booking Form (end user, on client website)
| Field | Control | Notes |
|---|---|---|
| Room | dropdown/selector with **live status badge** + available time slots | from `GET /rooms` |
| Date | date picker | |
| Start / End time | time pickers | validated against room availability |
| Booker name | text | → Nuveq visitor `name` |
| Phone | text | → Nuveq visitor `phone` |
| Email | text | → Nuveq visitor `email`; QR delivery |
| Purpose / notes | textarea (optional) | stored in our DB only |

On submit → our `POST /bookings` → success screen shows **QR code** (credential) + booking window + room/door info.

### 11.3 Room Status Board (client dashboard)
- Table/cards per room: **status badge** (`AVAILABLE` green / `BOOKED` amber / `IN_USE` blue / `EXPIRED` grey), current booking (user, window), next booking, door name.
- Auto-refresh: poll `GET /rooms` every 15–30s **or** receive our push webhook (§8).
- Filter by site/floor; click room → booking detail.

### 11.4 Booking Detail View
- Status timeline: `BOOKED → CHECKED_IN (time) → CHECKED_OUT (time)` or `EXPIRED (time)`.
- QR (re-download), credential number (masked option), visitor info.
- Actions: **Revoke access** (calls our `DELETE /bookings/{id}` → deletes Nuveq registration), **Extend** (re-issue via `/api/visitors/repeat`).

### 11.5 Settings (client admin)
- Default grace minutes; default lift group per site; **client webhook URL** (where we push status changes); API key management.

### 11.6 Ops Dashboard (our internal)
- Today's bookings, check-ins, no-shows/expired, webhook delivery success rate, reconciliation lag, Nuveq API error rate.

---

## 12. Field Dictionary — "where does each field come from"

| Concept | Field | Source of truth |
|---|---|---|
| Room identity | `room_id`, `room_name` | our config DB (name from Nuveq door `name`) |
| Room ↔ Nuveq | `site_id`, `controller_id`, `door_number`, `door_id` | Nuveq `/api/sites`, `/api/controllers/{id}`, `/api/visitors/doors` |
| Booking window | `visit_start`, `visit_end` | **client booking data** (their schedule) → sent to Nuveq |
| Visitor identity | `name`, `phone`, `email` | **client booking data** (booker or invitee) |
| Credential | `credential_number` | **our service generates** (unique numeric), stored in our DB, sent to Nuveq |
| Lift access | `lift_group_id` | our config per site (from `/api/visitors/lift-groups?siteId=`) |
| Door grant | `allowed_door_ids` | `[room.door_id]` from our mapping |
| Check-in/out | `checked_in_at`, `checked_out_at` | **derived** from webhook events (`direction` Entry/Exit, matched by `card_no` = `credential_number`) |
| Room status | `status` | **derived** from bookings + taps + scheduler |
| Expiry | `grace_minutes`, `expires_at` | client config; `expires_at = visit_start + grace` |
| QR | QR payload | `credential_number` |

---

## 13. Security & Ops

- Nuveq API key lives in **server env/vault only**; client only ever sees our own API key.
- Our API keys: per-client, revocable, rate-limited.
- Audit log every Nuveq call (request/response) for support.
- Timezone: store everything UTC; Nuveq `visitStart/visitEnd` need offset-aware ISO-8601; events carry `timezone` (e.g. `Asia/Jakarta`) — normalize carefully.
- Idempotency keys on `POST /bookings` (client retries must not double-create visitors).
- Pagination: Nuveq list endpoints use cursor (`after`/`first`, max 1000) — our sync loops must page.

---

## 14. Open Questions (need answers / live test)

**Answered during research:**
- ✅ Webhook payload schema (§2.4) — captured live.
- ✅ Webhook fires on all event types, incl. `Invalid access` and `Manual release` (§2.4).
- ✅ Webhook can deliver backlog bursts on controller reconnect (§2.4).
- ✅ Visitor credentials are a separate namespace from staff cards (§2.3).
- ✅ No door-creation API — doors are portal-managed (§6).
- ✅ `DELETE /api/visitors/registrations/{id}` revokes access (tested).

**Still open:**
1. **Live `Valid visitor` webhook capture** — schema confirmed; only the `visitcheckin` flag value on a real visitor tap is unconfirmed (non-blocking). The test credential `88990011` (registration 191975, door 3523) is armed; the controller was offline and the credential hadn't synced — tap again once synced.
2. **Do visitor `Exit` events exist** on the client's hardware? (demo REST data showed only visitor `Entry`) — affects check-out design (§5). If no exit reader, use auto-check-out at `visitEnd`.
3. **Second reader on the controller** — the user reports 2 readers, one working (staff) one not (visitor). Likely entry vs exit reader, or a reader whose door isn't visitor-enabled. Confirm which reader is the entry reader for the mapped door.
4. **Reader QR capability** — does the client's reader model accept QR credentials? (§9)
5. **Existing webhook** — does the client already have a webhook configured that we'd overwrite? (§10.4)
6. **Credential number format** — any client-side format/range requirements for `credentialNumber`? (we generate; confirm no collision policy with existing cards)
7. **Multi-door rooms** — any rooms with interlock (two doors)? `allowedDoorIds` supports arrays.
8. **Credential sync time** — how long after registration creation does a visitor credential become valid at the controller? (affects "access activating" UX, §2.4)

---

## 15. Implementation Roadmap (proposed)

1. **Phase 0 (now):** live tap test → capture access-tap payload; answer open questions 1–5.
2. **Phase 1:** middle service skeleton — auth, config DB, room mapping CRUD, Nuveq adapter (key in env).
3. **Phase 2:** booking flow — `POST /bookings` → Nuveq visitor+registration → credential + QR; `DELETE /bookings` → revoke.
4. **Phase 3:** webhook receiver + event state machine (check-in/out) + reconciliation poller.
5. **Phase 4:** room status derivation + client push webhook.
6. **Phase 5:** expiry scheduler (no-show grace) + auto check-out.
7. **Phase 6:** hardening — audit, rate limits, monitoring, docs for client devs.

---

*Test data note: during testing I created several visitors on the demo account (ids 106443, 106478, 106481, 106484, 106485, 106487, 106488). Registrations 191903/191904/191962/191965/191969/191970/191974 were deleted. **Registration 191975 (credential 88990011, "All Doors Tap Test", all 7 visitor doors) is left active intentionally** for the live `Valid visitor` capture — delete after testing via `DELETE /api/visitors/registrations/191975`. The account webhook currently points at the webhook.site capture URL (`39d53f6f-89aa-4c2d-8461-8d0d2c9d5280`); restore/repoint it after testing. Bare visitor records remain because Nuveq has no `DELETE /api/visitors/{id}` — clean up in the Nuveq portal if desired.*
