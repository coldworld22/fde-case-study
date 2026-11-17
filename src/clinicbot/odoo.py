"""Pushes bookings into the clinic's Odoo (Contacts + Calendar) through the transactional outbox.

Odoo is the clinic's system of record for reception and billing, but it sits on a server in the
Abha branch with an unreliable uplink. So the bot never calls Odoo while a patient is waiting:
bookings are committed locally with an outbox row, and this worker delivers them with retries.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Appointment, OutboxEvent
from .triage import SPECIALTY_NAMES

log = logging.getLogger(__name__)


class OdooError(Exception):
    pass


class Odoo(Protocol):
    def upsert_patient(self, name: str, phone: str, national_id: str) -> int: ...
    def create_event(self, partner_id: int, title: str, start: datetime, stop: datetime,
                     description: str) -> int: ...
    def archive_event(self, event_id: int) -> None: ...


class OdooJsonRpc:
    """Minimal Odoo external API client (JSON-RPC, works on Odoo 15-18 with an API key)."""

    def __init__(self, url: str, db: str, user: str, api_key: str, client: httpx.Client | None = None) -> None:
        self._endpoint = url.rstrip("/") + "/jsonrpc"
        self._db, self._user, self._key = db, user, api_key
        self._client = client or httpx.Client(timeout=15)
        self._uid: int | None = None

    def _call(self, service: str, method: str, *args: Any) -> Any:
        response = self._client.post(self._endpoint, json={
            "jsonrpc": "2.0", "method": "call", "id": 1,
            "params": {"service": service, "method": method, "args": list(args)},
        })
        response.raise_for_status()
        body = response.json()
        if body.get("error"):
            raise OdooError(body["error"].get("data", {}).get("message") or body["error"].get("message"))
        return body["result"]

    def _execute(self, model: str, method: str, *args: Any, **kwargs: Any) -> Any:
        if self._uid is None:
            self._uid = self._call("common", "login", self._db, self._user, self._key)
            if not self._uid:
                raise OdooError("Odoo login failed")
        return self._call("object", "execute_kw", self._db, self._uid, self._key, model, method, list(args), kwargs)

    def upsert_patient(self, name: str, phone: str, national_id: str) -> int:
        # The national ID is the stable key; reception staff search patients by it.
        found = self._execute("res.partner", "search", [("ref", "=", national_id)], limit=1)
        if found:
            self._execute("res.partner", "write", found, {"mobile": phone})
            return found[0]
        return self._execute("res.partner", "create", {"name": name, "mobile": phone, "ref": national_id})

    def create_event(self, partner_id: int, title: str, start: datetime, stop: datetime, description: str) -> int:
        fmt = "%Y-%m-%d %H:%M:%S"  # Odoo stores naive UTC
        return self._execute("calendar.event", "create", {
            "name": title, "partner_ids": [(4, partner_id)],
            "start": start.astimezone(UTC).strftime(fmt),
            "stop": stop.astimezone(UTC).strftime(fmt),
            "description": description,
        })

    def archive_event(self, event_id: int) -> None:
        self._execute("calendar.event", "write", [event_id], {"active": False})


def backoff(attempts: int) -> timedelta:
    """1, 2, 4, 8, 16... minutes, capped at one hour."""
    return timedelta(minutes=min(2 ** (attempts - 1), 60))


def deliver_pending(session: Session, odoo: Odoo, now: datetime, max_attempts: int, batch: int = 50) -> int:
    """Delivers due outbox events in order. Returns how many were delivered."""
    events = session.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.status == "pending", OutboxEvent.next_attempt_at <= now)
        .order_by(OutboxEvent.id)
        .limit(batch)
    ).all()
    delivered = 0
    for event in events:
        appointment = session.get(Appointment, event.appointment_id)
        try:
            _apply(odoo, event.kind, appointment)
        except (OdooError, httpx.HTTPError) as exc:
            event.attempts += 1
            event.last_error = str(exc)[:500]
            if event.attempts >= max_attempts:
                event.status = "failed"
                log.error("outbox %s failed permanently after %d attempts: %s", event.id, event.attempts, exc)
            else:
                event.next_attempt_at = now + backoff(event.attempts)
            session.commit()
            continue
        event.status = "done"
        event.attempts += 1
        session.commit()
        delivered += 1
    return delivered


def _apply(odoo: Odoo, kind: str, appointment: Appointment) -> None:
    if kind == "appointment.created":
        if appointment.odoo_event_id:  # already delivered once; the retry is a duplicate
            return
        if appointment.status == "cancelled":
            # Cancelled before Odoo ever heard of it (e.g. Odoo was down): nothing to create or archive.
            return
        partner_id = odoo.upsert_patient(appointment.patient_name, appointment.phone, appointment.national_id)
        slot = appointment.slot
        specialty = SPECIALTY_NAMES[slot.specialty][0]
        appointment.odoo_event_id = odoo.create_event(
            partner_id,
            title=f"{appointment.reference} {specialty} - {appointment.patient_name}",
            start=slot.starts_at, stop=slot.starts_at + timedelta(minutes=30),
            description=f"Booked via WhatsApp. {slot.doctor}, {slot.branch.name_en}.",
        )
    elif kind == "appointment.cancelled":
        if appointment.odoo_event_id:
            odoo.archive_event(appointment.odoo_event_id)
    else:
        raise OdooError(f"unknown event kind {kind}")
