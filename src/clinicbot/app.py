"""HTTP entry point: the WhatsApp webhook, health probes and an operations summary."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from .config import Settings, get_settings
from .conversation import BookingFlow, FlowConfig
from .messages import t
from .models import Appointment, Conversation, OutboxEvent, ProcessedMessage, make_session_factory
from .triage import LlmTriage, RuleTriage, Triage
from .whatsapp import (
    CloudApiSender,
    IncomingMessage,
    RecordingSender,
    Sender,
    parse_messages,
    signature_valid,
)

log = logging.getLogger(__name__)


def build_triage(settings: Settings) -> Triage:
    if settings.triage_mode == "llm":
        return LlmTriage(settings.llm_base_url, settings.llm_api_key, settings.llm_model,
                         settings.llm_timeout_seconds)
    return RuleTriage()


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker | None = None,
    sender: Sender | None = None,
    triage: Triage | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    allow_unsigned: bool = False,
) -> FastAPI:
    settings = settings or get_settings()
    session_factory = session_factory or make_session_factory(settings.database_url)
    if sender is None:
        sender = (CloudApiSender(settings.whatsapp_api_base, settings.whatsapp_phone_number_id,
                                 settings.whatsapp_access_token)
                  if settings.whatsapp_access_token else RecordingSender())
    triage = triage or build_triage(settings)
    flow_config = FlowConfig(settings.slots_offered, timedelta(minutes=settings.min_notice_minutes))

    app = FastAPI(title="clinicbot", version="1.0.0")

    def process(message: IncomingMessage) -> None:
        with session_factory() as session:
            try:
                session.add(ProcessedMessage(message_id=message.message_id, received_at=clock()))
                session.commit()
            except IntegrityError:
                session.rollback()
                log.info("duplicate delivery of %s ignored", message.message_id)
                return
            if message.type != "text":
                convo = session.get(Conversation, message.phone)
                replies = [t("text_only", convo.language if convo else "ar")]
            else:
                replies = BookingFlow(session, triage, flow_config).handle(message.phone, message.text, clock())
        for reply in replies:
            sender.send_text(message.phone, reply)

    @app.get("/webhook")
    def verify(mode: str = Query(alias="hub.mode"), token: str = Query(alias="hub.verify_token"),
               challenge: str = Query(alias="hub.challenge")) -> Response:
        if mode == "subscribe" and token == settings.whatsapp_verify_token:
            return Response(challenge, media_type="text/plain")
        raise HTTPException(status_code=403)

    @app.post("/webhook")
    async def receive(request: Request, background: BackgroundTasks,
                      signature: str | None = Header(default=None, alias="X-Hub-Signature-256")) -> dict:
        body = await request.body()
        if not allow_unsigned and not signature_valid(settings.whatsapp_app_secret, body, signature):
            raise HTTPException(status_code=401, detail="bad signature")
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON") from exc
        # Acknowledge at once (Meta retries slow webhooks) and do the work after the response.
        for message in parse_messages(payload):
            background.add_task(process, message)
        return {"status": "ok"}

    @app.get("/health/live")
    def live() -> dict:
        return {"status": "up"}

    @app.get("/health/ready")
    def ready() -> dict:
        with session_factory() as session:
            session.execute(text("select 1"))
        return {"status": "ready"}

    @app.get("/ops/summary")
    def summary() -> dict:
        """Counts only, no patient data: safe for the clinic's IT dashboard."""
        with session_factory() as session:
            appointments = dict(session.execute(
                select(Appointment.status, func.count()).group_by(Appointment.status)).all())
            outbox = dict(session.execute(
                select(OutboxEvent.status, func.count()).group_by(OutboxEvent.status)).all())
        return {"appointments": appointments, "odoo_outbox": outbox}

    return app


def app_factory() -> FastAPI:
    """uvicorn entry point: uvicorn clinicbot.app:app_factory --factory"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return create_app()
