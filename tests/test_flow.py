from datetime import timedelta

from conftest import NOW, PHONE, VALID_ID
from sqlalchemy import select

from clinicbot import scheduling
from clinicbot.conversation import BookingFlow
from clinicbot.models import Appointment, Conversation, OutboxEvent
from clinicbot.triage import RuleTriage


def run(flow, *messages, now=NOW, phone=PHONE):
    replies = []
    for message in messages:
        replies = flow.handle(phone, message, now)
    return replies


def test_books_in_arabic_end_to_end(session):
    flow = BookingFlow(session, RuleTriage())

    replies = run(flow, "السلام عليكم", "1", "ألم في الركبة", "2", "سارة محمد", VALID_ID, "نعم")

    assert "تم الحجز" in replies[0]
    appointment = session.scalar(select(Appointment))
    assert appointment.slot.specialty == "orthopedics"
    assert appointment.slot.status == "booked"
    assert (appointment.patient_name, appointment.national_id, appointment.language) == ("سارة محمد", VALID_ID, "ar")
    assert appointment.reference in replies[0]
    outbox = session.scalars(select(OutboxEvent)).all()
    assert [e.kind for e in outbox] == ["appointment.created"]


def test_english_and_language_switch(session):
    flow = BookingFlow(session, RuleTriage())

    assert "Welcome" in run(flow, "hi")[0]
    assert "مرحباً" in run(flow, "عربي")[0]
    assert "Welcome" in run(flow, "EN")[0]


def test_emergency_stops_the_booking(session):
    flow = BookingFlow(session, RuleTriage())

    replies = run(flow, "hi", "1", "my wife has chest pain")

    assert "997" in replies[0]
    assert session.scalar(select(Appointment)) is None
    assert "describe the reason" in run(flow, "1")[0]  # back at the menu, "1" starts a new booking


def test_slots_respect_minimum_notice_and_offer_distinct_times(session):
    slots = scheduling.next_slots(session, "general", NOW, 3, timedelta(minutes=60))

    assert len(slots) == 3
    assert all(s.starts_at >= NOW + timedelta(minutes=60) for s in slots)
    assert len({s.starts_at for s in slots}) == 3


def test_invalid_id_is_asked_again(session):
    flow = BookingFlow(session, RuleTriage())

    replies = run(flow, "hi", "1", "fever", "1", "Ali Hassan", "1012345678")

    assert "isn't valid" in replies[0]
    assert "Please confirm" in run(flow, VALID_ID)[0]


def test_choose_another_specialty(session):
    flow = BookingFlow(session, RuleTriage())

    replies = run(flow, "hi", "1", "fever", "0")
    assert "Dentistry" in replies[0]

    replies = run(flow, "4")
    assert "Next available in Dentistry" in replies[0]


def test_slot_taken_while_confirming_offers_new_times(session):
    flow = BookingFlow(session, RuleTriage())
    run(flow, "hi", "1", "fever", "1", "Ali Hassan", VALID_ID)
    chosen_id = session.get(Conversation, PHONE).data["slot_id"]
    # Someone else books the same slot first.
    assert scheduling.book(session, chosen_id, phone="+966500000001", patient_name="Other",
                           national_id="2123456788", language="en", now=NOW)

    replies = run(flow, "yes")

    assert "someone just took that slot" in replies[0]
    assert "Next available" in replies[1]
    assert session.scalars(select(Appointment)).all()[0].phone == "+966500000001"


def test_list_and_cancel(session):
    flow = BookingFlow(session, RuleTriage())
    run(flow, "hi", "1", "rash", "1", "Ali Hassan", VALID_ID, "yes")

    listing = run(flow, "2")[0]
    assert "Dermatology" in listing

    run(flow, "3")
    replies = run(flow, "1")

    assert "is cancelled" in replies[0]
    appointment = session.scalar(select(Appointment))
    assert appointment.status == "cancelled"
    assert appointment.slot.status == "open"
    kinds = [e.kind for e in session.scalars(select(OutboxEvent).order_by(OutboxEvent.id))]
    assert kinds == ["appointment.created", "appointment.cancelled"]
    assert "no upcoming" in run(flow, "3")[0]


def test_idle_conversation_restarts_at_menu(session):
    flow = BookingFlow(session, RuleTriage())
    run(flow, "hi", "1")

    replies = run(flow, "fever", now=NOW + timedelta(hours=2))

    assert "Welcome" in replies[0]


def test_patients_do_not_see_each_others_appointments(session):
    flow = BookingFlow(session, RuleTriage())
    run(flow, "hi", "1", "rash", "1", "Ali Hassan", VALID_ID, "yes")

    assert "no upcoming" in run(flow, "hi", "2", phone="+966509999999")[0]
