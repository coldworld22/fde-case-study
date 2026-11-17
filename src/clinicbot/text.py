"""Text helpers for mixed Arabic/English WhatsApp input."""

import re

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIACRITICS = re.compile(r"[ً-ْـ]")  # harakat and tatweel
_ARABIC_LETTER = re.compile(r"[؀-ۿ]")


def normalize(text: str) -> str:
    """Lower-case, ASCII digits, and the Arabic spelling variants people mix up when typing quickly."""
    text = text.translate(_ARABIC_DIGITS).strip().lower()
    text = _DIACRITICS.sub("", text)
    text = re.sub("[أإآ]", "ا", text)
    return text.replace("ة", "ه").replace("ى", "ي")


def detect_language(text: str) -> str:
    return "ar" if _ARABIC_LETTER.search(text) else "en"


def digits_only(text: str) -> str:
    return re.sub(r"\D", "", text.translate(_ARABIC_DIGITS))


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def valid_national_id(text: str) -> str | None:
    """Saudi National ID (starts with 1) or Iqama (starts with 2): 10 digits with a Luhn check digit."""
    digits = digits_only(text)
    if len(digits) == 10 and digits[0] in "12" and luhn_ok(digits):
        return digits
    return None


def mask_pii(text: str) -> str:
    """Remove IDs and phone numbers before free text leaves for an external model."""
    text = re.sub(r"(?<!\d)[12]\d{9}(?!\d)", "[ID]", text.translate(_ARABIC_DIGITS))
    return re.sub(r"(?<![\d+])(?:\+966|00966|966|0)?5\d{8}(?!\d)", "[PHONE]", text)
