# Middle Service API Specification

Base URL: `http://localhost:8000/api/v1`

## 1. Authentication

Client endpoints expect:
```http
X-Client-API-Key: <CLIENT_API_KEY>
```
Nuveq webhooks authenticate using the path token:
```http
POST /api/v1/webhooks/nuveq/{webhook_secret_token}
```

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
- Accepts Nuveq raw tap / status payload.
- Returns `{ "received": true, "uuid": "<event_uuid>" }` fast.

### 4.2 Client Webhook Notification Configuration
- **POST** `/webhooks/client-config`
```json
{
  "url": "https://client-booking-site.com/api/room-status-webhook",
  "secret": "whsec_supersecretkey",
  "is_active": true
}
```

---

## 5. Nuveq Sync / Explorer Proxy (Admin)

Endpoints enabling the client admin to discover available doors, controllers, and sites without needing Nuveq dashboard credentials:
- **GET** `/nuveq/sites`
- **GET** `/nuveq/controllers`
- **GET** `/nuveq/doors`
- **GET** `/nuveq/lift-groups`
- **POST** `/nuveq/setup-webhook` (Configures account-level webhook URL on Nuveq Cloud)
