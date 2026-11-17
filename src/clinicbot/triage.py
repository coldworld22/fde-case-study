"""Routing a patient's description to a specialty, with emergencies decided by rules only.

Safety model (see docs/adr/0002-rules-decide-emergencies.md):
1. Red-flag rules run first, on every message, and cannot be overridden by the model.
2. Only if there is no red flag may an LLM suggest a specialty, from a fixed list.
3. Any model error, timeout or unexpected answer falls back to the keyword rules.
The bot never diagnoses; it only decides which clinic queue a booking goes into.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from .text import mask_pii, normalize

log = logging.getLogger(__name__)

SPECIALTIES = ["general", "pediatrics", "dermatology", "dentistry", "obgyn", "orthopedics"]

SPECIALTY_NAMES = {
    "general": ("General Medicine", "الطب العام"),
    "pediatrics": ("Pediatrics", "طب الأطفال"),
    "dermatology": ("Dermatology", "الجلدية"),
    "dentistry": ("Dentistry", "الأسنان"),
    "obgyn": ("Obstetrics & Gynecology", "النساء والولادة"),
    "orthopedics": ("Orthopedics", "العظام"),
}

# Phrases are matched after text.normalize(), so Arabic keywords are written in normalised form
# (ا for أ/إ/آ, ه for ة, ي for ى).
RED_FLAGS = [
    "chest pain", "can't breathe", "cant breathe", "cannot breathe", "difficulty breathing",
    "short of breath", "unconscious", "fainted", "seizure", "stroke", "severe bleeding",
    "heavy bleeding", "suicide", "kill myself", "overdose", "poison", "poisoned", "poisoning",
    "الم في الصدر", "الم بالصدر", "الم صدر", "ضيق تنفس", "ضيق في التنفس", "صعوبه في التنفس",
    "ما اقدر اتنفس", "فاقد الوعي", "اغماء", "اغمي", "تشنج", "جلطه", "نزيف شديد", "نزيف حاد",
    "انتحار", "تسمم", "جرعه زائده",
]

KEYWORDS = {
    "pediatrics": ["my son", "my daughter", "my child", "my baby", "kid", "kids", "infant", "toddler",
                   "طفل", "ولدي", "ابني", "بنتي", "رضيع", "اطفال"],
    "dermatology": ["rash", "skin", "acne", "itch", "eczema", "mole", "hair loss",
                    "جلد", "حبوب", "حكه", "طفح", "اكزيما", "شامه", "تساقط الشعر"],
    "dentistry": ["tooth", "teeth", "gum", "dental", "molar", "braces",
                  "سن", "اسنان", "ضرس", "لثه", "تقويم"],
    "obgyn": ["pregnant", "pregnancy", "period", "menstrual", "ultrasound",
              "حامل", "حمل", "الدوره", "دوره شهريه", "سونار"],
    "orthopedics": ["back pain", "knee", "joint", "fracture", "shoulder", "sprain", "neck pain",
                    "ظهر", "ركبه", "مفصل", "كسر", "كتف", "التواء", "رقبه"],
}


@dataclass(frozen=True)
class TriageResult:
    emergency: bool
    specialty: str
    source: str  # "rules" or "llm"


class Triage(Protocol):
    def assess(self, description: str) -> TriageResult: ...


_PREFIXES = ("وال", "بال", "فال", "ال", "لل", "و", "ب")


def _tokens(text: str) -> set[str]:
    """Words plus their forms without Arabic prefixes, so "بالركبه" matches "ركبه"."""
    words = re.findall(r"[\w']+", text)
    tokens = set(words)
    for word in words:
        for prefix in _PREFIXES:
            if word.startswith(prefix) and len(word) - len(prefix) >= 2:
                tokens.add(word[len(prefix):])
    return tokens


def _mentions(text: str, tokens: set[str], phrase: str) -> bool:
    # Phrases match as substrings; single words must be whole words ("kid" must not match "kidney").
    return phrase in text if " " in phrase else phrase in tokens


def has_red_flag(description: str) -> bool:
    text = normalize(description)
    tokens = _tokens(text)
    return any(_mentions(text, tokens, flag) for flag in RED_FLAGS)


class RuleTriage:
    def assess(self, description: str) -> TriageResult:
        if has_red_flag(description):
            return TriageResult(True, "general", "rules")
        text = normalize(description)
        tokens = _tokens(text)
        for specialty, words in KEYWORDS.items():
            if any(_mentions(text, tokens, word) for word in words):
                return TriageResult(False, specialty, "rules")
        return TriageResult(False, "general", "rules")


SYSTEM_PROMPT = (
    "You route outpatient clinic bookings. Given a patient's short description, reply with JSON only: "
    '{"specialty": one of ' + json.dumps(SPECIALTIES) + "}. "
    "Do not diagnose. Do not give medical advice. If unsure, choose \"general\"."
)


class LlmTriage:
    """Asks an OpenAI-compatible endpoint (for example llm-gateway) to pick a specialty."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float,
                 client: httpx.Client | None = None) -> None:
        self._url = base_url.rstrip("/") + "/v1/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._model = model
        self._client = client or httpx.Client(timeout=timeout)
        self._fallback = RuleTriage()

    def assess(self, description: str) -> TriageResult:
        if has_red_flag(description):
            return TriageResult(True, "general", "rules")
        try:
            response = self._client.post(self._url, headers=self._headers, json={
                "model": self._model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": mask_pii(description)[:500]},
                ],
            })
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            specialty = json.loads(content)["specialty"]
            if specialty in SPECIALTIES:
                return TriageResult(False, specialty, "llm")
            log.warning("LLM returned unknown specialty %r; using rules", specialty)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            log.warning("LLM triage failed (%s); using rules", type(exc).__name__)
        return self._fallback.assess(description)
