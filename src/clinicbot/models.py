from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """Stores aware datetimes as UTC and always returns aware UTC, on SQLite and PostgreSQL alike."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime; use timezone-aware values")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_en: Mapped[str] = mapped_column(String(80))
    name_ar: Mapped[str] = mapped_column(String(80))


class Slot(Base):
    """A bookable 30-minute slot for one specialty at one branch. Booking flips status open -> booked."""

    __tablename__ = "slots"
    __table_args__ = (UniqueConstraint("branch_id", "specialty", "starts_at", "doctor"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    specialty: Mapped[str] = mapped_column(String(40), index=True)
    doctor: Mapped[str] = mapped_column(String(80))
    starts_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | booked

    branch: Mapped[Branch] = relationship()


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(12), unique=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"))
    phone: Mapped[str] = mapped_column(String(20), index=True)  # E.164
    patient_name: Mapped[str] = mapped_column(String(120))
    national_id: Mapped[str] = mapped_column(String(10))
    language: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(12), default="confirmed")  # confirmed | cancelled
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())
    reminder_sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    odoo_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    slot: Mapped[Slot] = relationship()


class Conversation(Base):
    """Where each WhatsApp user is in the booking flow. One row per phone number."""

    __tablename__ = "conversations"

    phone: Mapped[str] = mapped_column(String(20), primary_key=True)
    state: Mapped[str] = mapped_column(String(30), default="start")
    language: Mapped[str] = mapped_column(String(2), default="ar")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime())


class ProcessedMessage(Base):
    """WhatsApp retries webhooks; remembering message ids makes handling idempotent."""

    __tablename__ = "processed_messages"

    message_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime())


class OutboxEvent(Base):
    """Changes Odoo must hear about. Written in the same transaction as the booking (transactional outbox)."""

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))  # appointment.created | appointment.cancelled
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"))
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending | done | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(UtcDateTime())
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime())


def make_session_factory(database_url: str) -> sessionmaker:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
