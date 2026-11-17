import json
from datetime import timedelta

import httpx
from conftest import NOW, VALID_ID
from sqlalchemy import select

from clinicbot import scheduling
from clinicbot.jobs import send_reminders
from clinicbot.models import Appointment, OutboxEvent, Slot
from clinicbot.odoo import OdooError, OdooJsonRpc, deliver_pending
from clinicbot.whatsapp import RecordingSender


class FakeOdoo:
    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.events: dict[int, dict] = {}
        self.partners: dict[str, int] = {}

    def upsert_patient(self, name, phone, national_id):
        if self.fail_times:
            self.fail_times -= 1
            raise OdooError("connection reset")
        return self.partners.setdefault(national_id, len(self.partners) + 1)

    def create_event(self, partner_id, title, start, stop, description):
        event_id = len(self.events) + 100
        self.events[event_id] = {"partner": partner_id, "title": title, "start": start, "active": True}
        return event_id

    def archive_event(self, event_id):
        self.events[event_id]["active"] = False


def book(session, specialty="general", phone="+966551234567", hours_ahead=None):
    query = select(Slot).where(Slot.status == "open", Slot.specialty == specialty).order_by(Slot.starts_at)
    if hours_ahead is not None:
        query = query.where(Slot.starts_at >= NOW + timedelta(hours=hours_ahead))
    slot = session.scalar(query)
    return scheduling.book(session, slot.id, phone=phone, patient_name="Ali Hassan", national_id=VALID_ID,
                           language="en", now=NOW)


def test_delivers_booking_to_odoo(session):
    appointment = book(session)
    odoo = FakeOdoo()

    assert deliver_pending(session, odoo, NOW, max_attempts=6) == 1

    event = odoo.events[appointment.odoo_event_id]
    assert event["title"].startswith(appointment.reference)
    assert session.scalar(select(OutboxEvent)).status == "done"
    assert deliver_pending(session, odoo, NOW, max_attempts=6) == 0  # nothing left


def test_retries_with_backoff_then_succeeds(session):
    book(session)
    odoo = FakeOdoo(fail_times=2)

    assert deliver_pending(session, odoo, NOW, 6) == 0
    event = session.scalar(select(OutboxEvent))
    assert (event.attempts, event.next_attempt_at) == (1, NOW + timedelta(minutes=1))
    assert deliver_pending(session, odoo, NOW, 6) == 0  # not due yet
    assert deliver_pending(session, odoo, NOW + timedelta(minutes=1), 6) == 0
    assert deliver_pending(session, odoo, NOW + timedelta(minutes=3), 6) == 1
    assert len(odoo.events) == 1


def test_gives_up_after_max_attempts(session):
    book(session)
    odoo = FakeOdoo(fail_times=99)
    moment = NOW
    for _ in range(3):
        deliver_pending(session, odoo, moment, max_attempts=3)
        moment += timedelta(hours=2)

    event = session.scalar(select(OutboxEvent))
    assert (event.status, event.attempts, event.last_error) == ("failed", 3, "connection reset")


def test_cancellation_archives_the_odoo_event(session):
    appointment = book(session)
    odoo = FakeOdoo()
    deliver_pending(session, odoo, NOW, 6)

    scheduling.cancel(session, appointment, NOW)
    deliver_pending(session, odoo, NOW, 6)

    assert odoo.events[appointment.odoo_event_id]["active"] is False


def test_cancelled_before_odoo_heard_of_it_creates_nothing(session):
    appointment = book(session)
    scheduling.cancel(session, appointment, NOW)

    odoo = FakeOdoo()
    deliver_pending(session, odoo, NOW, 6)

    assert odoo.events == {}
    assert {e.status for e in session.scalars(select(OutboxEvent))} == {"done"}


def test_json_rpc_client_speaks_odoo_external_api():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["params"])
        params = body["params"]
        if params["method"] == "login":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": 7})
        model, method = params["args"][3], params["args"][4]
        result = {("res.partner", "search"): [], ("res.partner", "create"): 42,
                  ("calendar.event", "create"): 900}[(model, method)]
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    odoo = OdooJsonRpc("https://erp.example", "clinic", "bot@clinic", "key",
                       client=httpx.Client(transport=httpx.MockTransport(handler)))

    partner = odoo.upsert_patient("Ali", "+966551234567", VALID_ID)
    event = odoo.create_event(partner, "AMC-1 General", NOW, NOW + timedelta(minutes=30), "via WhatsApp")

    assert (partner, event) == (42, 900)
    create_event_args = calls[-1]["args"]
    assert create_event_args[1] == 7  # uid from login, reused
    assert create_event_args[5][0]["start"] == "2026-11-22 06:00:00"  # 09:00 Riyadh in naive UTC
    assert sum(c["method"] == "login" for c in calls) == 1


def test_json_rpc_errors_raise():
    def handler(request):
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1,
                                         "error": {"message": "Odoo Server Error",
                                                   "data": {"message": "Access Denied"}}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    odoo = OdooJsonRpc("https://erp.example", "db", "u", "k", client=client)
    try:
        odoo.upsert_patient("A", "+1", VALID_ID)
    except OdooError as exc:
        assert "Access Denied" in str(exc)
    else:
        raise AssertionError("expected OdooError")


def test_reminders_go_out_once_the_day_before(session):
    tomorrow = book(session, hours_ahead=24)
    book(session, specialty="dentistry", phone="+966509999999")  # today: no reminder yet
    sender = RecordingSender()

    assert send_reminders(session, sender, NOW) == 1
    assert send_reminders(session, sender, NOW) == 0
    phone, text = sender.sent[0]
    assert phone == tomorrow.phone
    assert tomorrow.reference in text and "Reminder" in text
    assert session.get(Appointment, tomorrow.id).reminder_sent_at == NOW
