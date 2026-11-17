"""Background work: deliver the Odoo outbox and send next-day reminders.

Run as a separate process next to the web app:  python -m clinicbot.jobs  (loops every 30 s)
or once from cron/Kubernetes CronJob:           python -m clinicbot.jobs --once
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import scheduling
from .config import get_settings
from .conversation import specialty_name
from .messages import t
from .models import Appointment, Slot, make_session_factory
from .odoo import Odoo, OdooJsonRpc, deliver_pending
from .whatsapp import CloudApiSender, RecordingSender, Sender

log = logging.getLogger(__name__)

REMINDER_TEMPLATE = "appointment_reminder"  # registered in WhatsApp Manager in Arabic and English


def send_reminders(session: Session, sender: Sender, now: datetime) -> int:
    """Reminds patients whose appointment starts 20-26 hours from now, once each."""
    due = session.scalars(
        select(Appointment).join(Slot)
        .where(Appointment.status == "confirmed", Appointment.reminder_sent_at.is_(None),
               Slot.starts_at.between(now + timedelta(hours=20), now + timedelta(hours=26)))
    ).all()
    for appointment in due:
        lang, slot = appointment.language, appointment.slot
        params = [scheduling.format_when(slot.starts_at, lang),
                  slot.branch.name_ar if lang == "ar" else slot.branch.name_en,
                  specialty_name(slot.specialty, lang), appointment.reference]
        preview = t("reminder", lang, when=params[0], branch=params[1], specialty=params[2], reference=params[3])
        sender.send_template(appointment.phone, REMINDER_TEMPLATE, lang, params, preview)
        appointment.reminder_sent_at = now
        session.commit()
    return len(due)


def run_once(session: Session, sender: Sender, odoo: Odoo | None, now: datetime, max_attempts: int) -> dict:
    delivered = deliver_pending(session, odoo, now, max_attempts) if odoo else 0
    reminded = send_reminders(session, sender, now)
    return {"outbox_delivered": delivered, "reminders_sent": reminded}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    parser.add_argument("--interval", type=int, default=30, help="seconds between passes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    settings = get_settings()
    session_factory = make_session_factory(settings.database_url)
    sender: Sender = (
        CloudApiSender(settings.whatsapp_api_base, settings.whatsapp_phone_number_id, settings.whatsapp_access_token)
        if settings.whatsapp_access_token else RecordingSender()
    )
    odoo = (OdooJsonRpc(settings.odoo_url, settings.odoo_db, settings.odoo_user, settings.odoo_api_key)
            if settings.odoo_url else None)
    if odoo is None:
        log.warning("CLINICBOT_ODOO_URL not set: bookings stay in the outbox until it is")

    while True:
        with session_factory() as session:
            result = run_once(session, sender, odoo, datetime.now(UTC), settings.max_attempts)
        log.info("jobs pass: %s", result)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
