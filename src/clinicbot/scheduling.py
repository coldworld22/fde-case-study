"""Slots, bookings and cancellations. Every change that Odoo must know about writes an outbox row
in the same transaction, so a booking can never exist without its sync event (or vice versa)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import RIYADH
from .models import Appointment, OutboxEvent, Slot

_REFERENCE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no 0/O or 1/I: read aloud at reception

_DAYS_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
_MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر",
              "أكتوبر", "نوفمبر", "ديسمبر"]


def format_when(moment: datetime, lang: str) -> str:
    local = moment.astimezone(RIYADH)
    if lang == "ar":
        period = "ص" if local.hour < 12 else "م"
        hour = local.hour % 12 or 12
        return f"{_DAYS_AR[local.weekday()]} {local.day} {_MONTHS_AR[local.month - 1]}، {hour}:{local:%M} {period}"
    return local.strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def next_slots(session: Session, specialty: str, now: datetime, limit: int,
               min_notice: timedelta) -> list[Slot]:
    """The earliest open slots, at most one per start time so patients see different times."""
    rows = session.scalars(
        select(Slot)
        .where(Slot.specialty == specialty, Slot.status == "open", Slot.starts_at >= now + min_notice)
        .order_by(Slot.starts_at, Slot.branch_id)
        .limit(limit * 4)
    ).all()
    chosen: list[Slot] = []
    seen: set[datetime] = set()
    for slot in rows:
        if slot.starts_at not in seen:
            chosen.append(slot)
            seen.add(slot.starts_at)
        if len(chosen) == limit:
            break
    return chosen


def book(session: Session, slot_id: int, *, phone: str, patient_name: str, national_id: str,
         language: str, now: datetime) -> Appointment | None:
    """Books a slot if it is still open. Returns None if someone else got there first.

    The conditional UPDATE is the concurrency control: two patients confirming the same slot at the
    same moment both run it, the database applies them one after the other, and only the first
    changes a row. This works the same on SQLite and PostgreSQL without explicit locks.
    """
    claimed = session.execute(
        update(Slot).where(Slot.id == slot_id, Slot.status == "open").values(status="booked")
    ).rowcount
    if claimed != 1:
        session.rollback()
        return None
    appointment = Appointment(
        reference="AMC-" + "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(6)),
        slot_id=slot_id, phone=phone, patient_name=patient_name, national_id=national_id,
        language=language, status="confirmed", created_at=now,
    )
    session.add(appointment)
    session.flush()
    session.add(OutboxEvent(kind="appointment.created", appointment_id=appointment.id,
                            next_attempt_at=now, created_at=now))
    session.commit()
    return appointment


def upcoming(session: Session, phone: str, now: datetime) -> list[Appointment]:
    return list(session.scalars(
        select(Appointment).join(Slot)
        .where(Appointment.phone == phone, Appointment.status == "confirmed", Slot.starts_at > now)
        .order_by(Slot.starts_at)
    ).all())


def cancel(session: Session, appointment: Appointment, now: datetime) -> None:
    appointment.status = "cancelled"
    appointment.slot.status = "open"
    session.add(OutboxEvent(kind="appointment.cancelled", appointment_id=appointment.id,
                            next_attempt_at=now, created_at=now))
    session.commit()


def seed(session: Session, start: datetime, days: int = 14) -> int:
    """Demo data: three branches, one doctor per specialty per branch, 08:00-16:00 Sunday to Thursday."""
    from .models import Branch
    from .triage import SPECIALTIES

    if session.scalar(select(Branch.id).limit(1)) is not None:
        return 0
    branches = [
        Branch(id=1, name_en="Abha - Al Mansak", name_ar="أبها - المنسك"),
        Branch(id=2, name_en="Khamis Mushait", name_ar="خميس مشيط"),
        Branch(id=3, name_en="Muhayil Asir", name_ar="محايل عسير"),
    ]
    session.add_all(branches)
    doctors = ["Dr. Sara Al-Qahtani", "Dr. Faisal Al-Shehri", "Dr. Huda Al-Asmari",
               "Dr. Omar Al-Ghamdi", "Dr. Noura Al-Alkami", "Dr. Khalid Al-Mutairi"]
    count = 0
    first_day = start.astimezone(RIYADH).replace(hour=0, minute=0, second=0, microsecond=0)
    for day in range(days):
        date = first_day + timedelta(days=day)
        if date.weekday() in (4, 5):  # Friday, Saturday
            continue
        for b_index, branch in enumerate(branches):
            for s_index, specialty in enumerate(SPECIALTIES):
                doctor = doctors[(s_index + b_index) % len(doctors)]
                for half_hour in range(16):
                    starts = date.replace(hour=8) + timedelta(minutes=30 * half_hour)
                    session.add(Slot(branch_id=branch.id, specialty=specialty, doctor=doctor,
                                     starts_at=starts))
                    count += 1
    session.commit()
    return count
