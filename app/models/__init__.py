import enum
from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def generate_uuid(prefix: str = "") -> str:
    short_id = uuid.uuid4().hex[:12]
    return f"{prefix}{short_id}" if prefix else short_id


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RoomStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    BOOKED = "BOOKED"
    IN_USE = "IN_USE"
    EXPIRED = "EXPIRED"
    MAINTENANCE = "MAINTENANCE"


class BookingStatus(str, enum.Enum):
    BOOKED = "BOOKED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    AUTO_CHECKED_OUT = "AUTO_CHECKED_OUT"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class Room(Base):
    __tablename__ = "rooms"

    id = Column(String(32), primary_key=True, default=lambda: generate_uuid("rm_"))
    name = Column(String(255), nullable=False)
    site_id = Column(Integer, nullable=False, index=True)
    controller_id = Column(Integer, nullable=False, index=True)
    door_number = Column(Integer, nullable=False)
    door_id = Column(Integer, nullable=False, unique=True, index=True)
    lift_group_id = Column(Integer, nullable=False, default=630)
    grace_minutes = Column(Integer, nullable=False, default=15)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    bookings = relationship("Booking", back_populates="room", lazy="selectin", cascade="all, delete-orphan")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(String(32), primary_key=True, default=lambda: generate_uuid("bk_"))
    room_id = Column(String(32), ForeignKey("rooms.id"), nullable=False, index=True)
    credential_number = Column(Integer, unique=True, nullable=False, index=True)
    visitor_id = Column(Integer, nullable=True)
    visitor_registration_id = Column(Integer, nullable=True, index=True)

    booker_name = Column(String(255), nullable=False)
    booker_email = Column(String(255), nullable=True)
    booker_phone = Column(String(50), nullable=True)

    visit_start = Column(DateTime(timezone=True), nullable=False, index=True)
    visit_end = Column(DateTime(timezone=True), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    status = Column(
        Enum(BookingStatus),
        default=BookingStatus.BOOKED,
        nullable=False,
        index=True,
    )

    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    checked_out_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    room = relationship("Room", back_populates="bookings", lazy="selectin")
    tap_events = relationship("TapEvent", back_populates="booking", lazy="selectin")


class TapEvent(Base):
    __tablename__ = "tap_events"

    id = Column(String(32), primary_key=True, default=lambda: generate_uuid("tap_"))
    uuid = Column(String(64), unique=True, nullable=False, index=True)
    mac = Column(String(32), nullable=True)
    site_id = Column(Integer, nullable=True)
    door_id = Column(Integer, nullable=True, index=True)
    card_no = Column(Integer, nullable=True, index=True)
    name = Column(String(100), nullable=False)
    direction = Column(String(20), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    raw_payload = Column(Text, nullable=False)
    processed = Column(Boolean, default=False, nullable=False)

    booking_id = Column(String(32), ForeignKey("bookings.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    booking = relationship("Booking", back_populates="tap_events", lazy="selectin")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    key = Column(String(128), primary_key=True)
    category = Column(String(64), nullable=False)
    response_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class ClientWebhookConfig(Base):
    __tablename__ = "client_webhook_configs"

    id = Column(String(32), primary_key=True, default=lambda: generate_uuid("cwh_"))
    url = Column(String(512), nullable=False)
    secret = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
