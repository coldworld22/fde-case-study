"""WhatsApp Business Cloud API: webhook signature check, payload parsing and sending text replies."""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncomingMessage:
    message_id: str
    phone: str  # E.164 with +
    type: str
    text: str


def signature_valid(app_secret: str, body: bytes, header: str | None) -> bool:
    """Meta signs each webhook body with the app secret: X-Hub-Signature-256: sha256=<hex>."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def parse_messages(payload: dict) -> list[IncomingMessage]:
    """Extracts user messages; status updates (sent/delivered/read) are ignored."""
    messages = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                text = msg.get("text", {}).get("body", "") if msg.get("type") == "text" else ""
                messages.append(IncomingMessage(
                    message_id=msg["id"], phone="+" + msg["from"].lstrip("+"), type=msg.get("type", ""), text=text))
    return messages


class Sender(Protocol):
    def send_text(self, phone: str, body: str) -> None: ...

    def send_template(self, phone: str, template: str, language: str, params: list[str], preview: str) -> None:
        """Business-initiated messages (e.g. reminders) outside the 24-hour customer-service window
        must use a template approved by Meta; free text is rejected."""


class CloudApiSender:
    def __init__(self, api_base: str, phone_number_id: str, access_token: str,
                 client: httpx.Client | None = None) -> None:
        self._url = f"{api_base.rstrip('/')}/{phone_number_id}/messages"
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._client = client or httpx.Client(timeout=10)

    def send_text(self, phone: str, body: str) -> None:
        response = self._client.post(self._url, headers=self._headers, json={
            "messaging_product": "whatsapp",
            "to": phone.lstrip("+"),
            "type": "text",
            "text": {"body": body, "preview_url": False},
        })
        if response.is_error:
            log.error("WhatsApp send failed: %s %s", response.status_code, response.text[:300])
        response.raise_for_status()

    def send_template(self, phone: str, template: str, language: str, params: list[str], preview: str) -> None:
        response = self._client.post(self._url, headers=self._headers, json={
            "messaging_product": "whatsapp",
            "to": phone.lstrip("+"),
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": language},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}],
            },
        })
        if response.is_error:
            log.error("WhatsApp template send failed: %s %s", response.status_code, response.text[:300])
        response.raise_for_status()


class RecordingSender:
    """Keeps sent messages in memory: used by tests, the simulator, and when no token is configured."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_text(self, phone: str, body: str) -> None:
        self.sent.append((phone, body))
        log.info("whatsapp(out) to=%s…%s chars=%d", phone[:6], phone[-2:], len(body))

    def send_template(self, phone: str, template: str, language: str, params: list[str], preview: str) -> None:
        self.send_text(phone, preview)
