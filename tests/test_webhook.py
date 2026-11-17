import hashlib
import hmac
import json

import pytest
from conftest import NOW
from fastapi.testclient import TestClient
from sqlalchemy import select

from clinicbot.app import create_app
from clinicbot.config import Settings
from clinicbot.models import Appointment
from clinicbot.triage import RuleTriage
from clinicbot.whatsapp import RecordingSender

SECRET = "app-secret"


@pytest.fixture
def setup(session_factory):
    sender = RecordingSender()
    settings = Settings(whatsapp_verify_token="verify-me", whatsapp_app_secret=SECRET)
    app = create_app(settings, session_factory, sender, RuleTriage(), clock=lambda: NOW)
    return TestClient(app), sender


def payload(text: str, message_id: str, msg_type: str = "text") -> dict:
    message = {"from": "966551234567", "id": message_id, "type": msg_type}
    if msg_type == "text":
        message["text"] = {"body": text}
    return {"object": "whatsapp_business_account",
            "entry": [{"changes": [{"value": {"messages": [message]}}]}]}


def post(client, body: dict, secret: str = SECRET):
    raw = json.dumps(body).encode()
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/webhook", content=raw, headers={"X-Hub-Signature-256": signature,
                                                          "Content-Type": "application/json"})


def test_meta_verification_handshake(setup):
    client, _ = setup
    ok = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                        "hub.challenge": "12345"})
    assert (ok.status_code, ok.text) == (200, "12345")
    bad = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                         "hub.challenge": "1"})
    assert bad.status_code == 403


def test_rejects_unsigned_or_forged_requests(setup):
    client, sender = setup
    assert client.post("/webhook", json=payload("hi", "m1")).status_code == 401
    assert post(client, payload("hi", "m1"), secret="wrong").status_code == 401
    assert sender.sent == []


def test_full_booking_over_the_webhook(setup, session_factory):
    client, sender = setup
    for i, text in enumerate(["hi", "1", "rash", "1", "Ali Hassan", "1012345672", "yes"]):
        assert post(client, payload(text, f"wamid.{i}")).status_code == 200

    assert sender.sent[-1][0] == "+966551234567"
    assert "Booked" in sender.sent[-1][1]
    with session_factory() as s:
        assert s.scalar(select(Appointment)).slot.specialty == "dermatology"


def test_redelivered_messages_are_processed_once(setup):
    client, sender = setup
    post(client, payload("hi", "wamid.same"))
    post(client, payload("hi", "wamid.same"))

    assert len(sender.sent) == 1


def test_non_text_messages_get_a_polite_answer(setup):
    client, sender = setup
    post(client, payload("", "wamid.img", msg_type="image"))

    assert "النصية" in sender.sent[0][1]


def test_status_callbacks_are_ignored(setup):
    client, sender = setup
    body = {"entry": [{"changes": [{"value": {"statuses": [{"id": "x", "status": "read"}]}}]}]}

    assert post(client, body).status_code == 200
    assert sender.sent == []


def test_health_and_ops_summary(setup):
    client, _ = setup
    assert client.get("/health/live").json() == {"status": "up"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    for i, text in enumerate(["hi", "1", "rash", "1", "Ali Hassan", "1012345672", "yes"]):
        post(client, payload(text, f"w{i}"))

    assert client.get("/ops/summary").json() == {"appointments": {"confirmed": 1},
                                                 "odoo_outbox": {"pending": 1}}
