import json

import httpx
import pytest

from clinicbot.text import mask_pii, valid_national_id
from clinicbot.triage import LlmTriage, RuleTriage


@pytest.mark.parametrize("text", [
    "I have chest pain",
    "my father can't breathe",
    "she fainted at home",
    "عندي ألم في الصدر",
    "عندي الم بالصدر من ساعة",   # no hamza, different preposition
    "ضيق تنفّس شديد",            # with shadda
    "صعوبة في التنفس",           # ta marbuta
    "أُغمي عليه",                # with damma
    "نزيف شديد بعد الولادة",
])
def test_red_flags_are_emergencies(text):
    result = RuleTriage().assess(text)
    assert result.emergency is True


@pytest.mark.parametrize("text, specialty", [
    ("my son has a fever", "pediatrics"),
    ("ابني عنده حرارة", "pediatrics"),
    ("بنتي عندها طفح جلدي", "pediatrics"),     # a child first, whatever the complaint
    ("itchy rash on my arm", "dermatology"),
    ("حبوب في الوجه", "dermatology"),
    ("toothache since yesterday", "general"),  # "toothache" is not the word "tooth"
    ("broken tooth", "dentistry"),
    ("ألم في الضرس", "dentistry"),
    ("أنا حامل في الشهر الثالث", "obgyn"),
    ("knee hurts when I climb stairs", "orthopedics"),
    ("ألم في الركبة", "orthopedics"),
    ("بالركبه", "orthopedics"),               # prefix stripped
    ("kidney stones follow-up", "general"),   # "kid" must not match "kidney"
    ("أحسن موعد متاح", "general"),             # "سن" must not match inside "أحسن"
    ("headache and tiredness", "general"),
])
def test_keyword_routing(text, specialty):
    result = RuleTriage().assess(text)
    assert (result.emergency, result.specialty) == (False, specialty)


def llm_returning(content: str, calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_llm_picks_specialty_from_fixed_list():
    calls = []
    triage = LlmTriage("http://gw", "k", "m", 1, client=llm_returning('{"specialty": "dermatology"}', calls))

    result = triage.assess("something odd on my skin")

    assert (result.specialty, result.source) == ("dermatology", "llm")
    assert calls[0]["temperature"] == 0


def test_llm_is_never_asked_about_red_flags():
    calls = []
    triage = LlmTriage("http://gw", "k", "m", 1, client=llm_returning('{"specialty": "dentistry"}', calls))

    assert triage.assess("chest pain").emergency is True
    assert calls == []


def test_llm_receives_masked_text():
    calls = []
    triage = LlmTriage("http://gw", "k", "m", 1, client=llm_returning('{"specialty": "general"}', calls))

    triage.assess("my id is 1012345672 and phone 0551234567, fever")

    sent = calls[0]["messages"][1]["content"]
    assert "1012345672" not in sent and "0551234567" not in sent


@pytest.mark.parametrize("content", ['{"specialty": "cardiology"}', "not json", '{"x": 1}'])
def test_unexpected_llm_answers_fall_back_to_rules(content):
    triage = LlmTriage("http://gw", "k", "m", 1, client=llm_returning(content, []))

    result = triage.assess("ألم في الركبة")

    assert (result.specialty, result.source) == ("orthopedics", "rules")


def test_llm_outage_falls_back_to_rules():
    def down(request):
        raise httpx.ConnectError("refused")
    triage = LlmTriage("http://gw", "k", "m", 1, client=httpx.Client(transport=httpx.MockTransport(down)))

    assert triage.assess("rash").source == "rules"


def test_national_id_validation_accepts_arabic_digits():
    assert valid_national_id("١٠١٢٣٤٥٦٧٢") == "1012345672"
    assert valid_national_id("2123456788") == "2123456788"
    assert valid_national_id("1012345678") is None  # bad check digit
    assert valid_national_id("3012345675") is None


def test_mask_pii():
    assert mask_pii("id 1012345672, call +966551234567") == "id [ID], call [PHONE]"
