"""The WhatsApp booking flow as a small state machine.

Each incoming text moves one patient's Conversation row from one state to the next and returns the
replies to send. Numbered menus instead of free text everywhere except the visit reason, because
patients here mostly reply from phones, often in Arabic, and a typed "2" is never ambiguous.

    menu ──1──► symptoms ──triage──► slot ──n──► name ──► national_id ──► confirm ──yes──► booked
      │                     │          │0                                    │no
      │                     └► emergency (997) ◄── red flag                   ▼
      ├──2──► list upcoming          specialty ──n──► slot                  aborted
      └──3──► cancel_choice ──n──► cancelled
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import scheduling
from .messages import t
from .models import Conversation, Slot
from .text import detect_language, digits_only, normalize, valid_national_id
from .triage import SPECIALTIES, SPECIALTY_NAMES, Triage

RESET_WORDS = {"menu", "start", "hi", "hello", "قائمه", "القائمه", "مرحبا", "السلام عليكم", "هلا"}
TO_ENGLISH = {"en", "english", "انجليزي"}
TO_ARABIC = {"ع", "ar", "arabic", "عربي"}
YES = {"yes", "y", "ok", "confirm", "نعم", "اي", "ايوه", "ايه", "تمام", "موافق", "اكيد"}
NO = {"no", "n", "cancel", "لا", "الغاء"}
IDLE_RESET = timedelta(minutes=30)


@dataclass
class FlowConfig:
    slots_offered: int = 3
    min_notice: timedelta = timedelta(minutes=60)


def specialty_name(specialty: str, lang: str) -> str:
    en, ar = SPECIALTY_NAMES[specialty]
    return ar if lang == "ar" else en


class BookingFlow:
    def __init__(self, session: Session, triage: Triage, config: FlowConfig | None = None) -> None:
        self.session = session
        self.triage = triage
        self.config = config or FlowConfig()

    def handle(self, phone: str, text: str, now: datetime) -> list[str]:
        convo = self.session.get(Conversation, phone)
        if convo is None:
            convo = Conversation(phone=phone, state="start", language=detect_language(text), data={},
                                 updated_at=now)
            self.session.add(convo)
        elif now - convo.updated_at > IDLE_RESET:
            convo.state, convo.data = "start", {}

        replies = self._step(convo, text.strip(), normalize(text), now)
        convo.updated_at = now
        flag_modified(convo, "data")  # data is mutated in place; tell SQLAlchemy to save it
        self.session.commit()
        return replies

    # -- transitions -------------------------------------------------------------------------

    def _step(self, c: Conversation, raw: str, text: str, now: datetime) -> list[str]:
        if text in TO_ENGLISH or text in TO_ARABIC:
            c.language = "en" if text in TO_ENGLISH else "ar"
            return self._menu(c)
        if c.state == "start" or text in RESET_WORDS:
            return self._menu(c)

        handler = getattr(self, f"_on_{c.state}")
        return handler(c, raw, text, now)

    def _menu(self, c: Conversation) -> list[str]:
        c.state, c.data = "menu", {}
        return [t("menu", c.language)]

    def _on_menu(self, c: Conversation, raw: str, text: str, now: datetime) -> list[str]:
        if text == "1":
            c.state = "symptoms"
            return [t("ask_symptoms", c.language)]
        if text == "2":
            appointments = scheduling.upcoming(self.session, c.phone, now)
            if not appointments:
                return [t("none_upcoming", c.language)]
            return [t("upcoming", c.language, options=self._appointment_lines(appointments, c.language))]
        if text == "3":
            appointments = scheduling.upcoming(self.session, c.phone, now)
            if not appointments:
                return [t("none_upcoming", c.language)]
            c.state = "cancel_choice"
            c.data = {"cancel_ids": [a.id for a in appointments]}
            return [t("choose_cancel", c.language, options=self._appointment_lines(appointments, c.language))]
        return [t("menu", c.language)]

    def _on_symptoms(self, c: Conversation, raw: str, text: str, now: datetime) -> list[str]:
        result = self.triage.assess(raw)
        if result.emergency:
            c.state, c.data = "menu", {}
            return [t("emergency", c.language)]
        c.data = {"specialty": result.specialty, "triage_source": result.source}
        return self._offer_slots(c, now)

    def _offer_slots(self, c: Conversation, now: datetime, prefix: list[str] | None = None) -> list[str]:
        specialty = c.data["specialty"]
        slots = scheduling.next_slots(self.session, specialty, now, self.config.slots_offered,
                                      self.config.min_notice)
        c.state = "slot"
        c.data["offered"] = [s.id for s in slots]
        name = specialty_name(specialty, c.language)
        if not slots:
            return [*(prefix or []), t("no_slots", c.language, specialty=name)]
        options = "\n".join(f"{i}) {self._slot_line(s, c.language)}" for i, s in enumerate(slots, 1))
        return [*(prefix or []), t("slots", c.language, specialty=name, options=options)]

    def _on_slot(self, c: Conversation, raw: str, text: str, now: datetime) -> list[str]:
        if text == "0":
            c.state = "specialty"
            options = "\n".join(f"{i}) {specialty_name(s, c.language)}" for i, s in enumerate(SPECIALTIES, 1))
            return [t("choose_specialty", c.language, options=options)]
        slot_id = self._pick(text, c.data.get("offered", []))
        if slot_id is None:
            return [t("invalid_choice", c.language)]
        c.data["slot_id"] = slot_id
        c.state = "name"
        return [t("ask_name", c.language)]

    def _on_specialty(self, c: Conversation, raw: str, text: str, now: datetime) -> list[str]:
        specialty = self._pick(text, SPECIALTIES)
        if specialty is None:
            return [t("invalid_choice", c.language)]
        c.data["specialty"] = specialty
        return self._offer_slots(c, now)

    def _on_name(self, c: Conversation, raw: str, text: str, now: datetime) -> list[str]:
        if len(raw) < 3 or digits_only(raw):
            return [t("ask_name", c.language)]
        c.data["patient_name"] = " ".join(raw.split())[:120]
        c.state = "national_id"
        return [t("ask_id", c.language)]

    def _on_national_id(self, c: Conversation, raw: str, text: str, now: datetime) -> list[str]:
        national_id = valid_national_id(raw)
        if national_id is None:
            return [t("bad_id", c.language)]
        c.data["national_id"] = national_id
        c.state = "confirm"
        slot = self.session.get(Slot, c.data["slot_id"])
        return [t("confirm", c.language, name=c.data["patient_name"],
                  specialty=specialty_name(slot.specialty, c.language), doctor=slot.doctor,
                  branch=self._branch(slot, c.language), when=scheduling.format_when(slot.starts_at, c.language))]

    def _on_confirm(self, c: Conversation, raw: str, text: str, now: datetime) -> list[str]:
        if text in NO:
            c.state, c.data = "menu", {}
            return [t("aborted", c.language)]
        if text not in YES:
            return [t("invalid_choice", c.language)]
        appointment = scheduling.book(
            self.session, c.data["slot_id"], phone=c.phone, patient_name=c.data["patient_name"],
            national_id=c.data["national_id"], language=c.language, now=now)
        if appointment is None:
            # book() rolled back the session; reload the conversation before changing it.
            self.session.refresh(c)
            return self._offer_slots(c, now, prefix=[t("slot_taken", c.language)])
        c.state, c.data = "menu", {}
        return [t("booked", c.language, reference=appointment.reference)]

    def _on_cancel_choice(self, c: Conversation, raw: str, text: str, now: datetime) -> list[str]:
        appointment_id = self._pick(text, c.data.get("cancel_ids", []))
        if appointment_id is None:
            return [t("invalid_choice", c.language)]
        appointment = next(a for a in scheduling.upcoming(self.session, c.phone, now) if a.id == appointment_id)
        scheduling.cancel(self.session, appointment, now)
        c.state, c.data = "menu", {}
        return [t("cancelled", c.language, reference=appointment.reference)]

    # -- helpers -----------------------------------------------------------------------------

    @staticmethod
    def _pick(text: str, options: list):
        if text.isdigit() and 1 <= int(text) <= len(options):
            return options[int(text) - 1]
        return None

    @staticmethod
    def _branch(slot: Slot, lang: str) -> str:
        return slot.branch.name_ar if lang == "ar" else slot.branch.name_en

    def _slot_line(self, slot: Slot, lang: str) -> str:
        return f"{scheduling.format_when(slot.starts_at, lang)} - {self._branch(slot, lang)} ({slot.doctor})"

    def _appointment_lines(self, appointments, lang: str) -> str:
        return "\n".join(
            f"{i}) {a.reference}: {specialty_name(a.slot.specialty, lang)}, "
            f"{scheduling.format_when(a.slot.starts_at, lang)}, {self._branch(a.slot, lang)}"
            for i, a in enumerate(appointments, 1)
        )
