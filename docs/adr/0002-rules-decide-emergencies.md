# 2. Rules decide emergencies; a model may only choose a specialty

Date: 2026-11-17 · Status: accepted

## Context

Some patients describe emergencies in chat ("my father has chest pain"). The bot must tell them
to call 997, every time, in their language. An LLM is good at understanding varied phrasing but
can be wrong, slow, or unavailable, and its behaviour can change when the provider updates it.

## Decision

1. A red-flag list (English and Arabic, matched after normalising hamza, ta marbuta, alef maqsura
   and diacritics) runs first, on every visit reason.
2. If it matches, the patient gets the 997 message and the booking stops. No model is called.
3. Otherwise, in `llm` mode, the masked text goes to an OpenAI-compatible endpoint, which may only
   answer with one specialty from a fixed list, at `temperature: 0`.
4. Any error, timeout (4 s), malformed answer or unknown specialty falls back to keyword rules.
5. Unknown cases go to General Medicine, which can always see the patient.

The red-flag list is owned by the medical director; changes need their sign-off and a test.

## Consequences

- Safety-critical behaviour is deterministic and covered by tests in both languages.
- The LLM improves routing for unusual phrasing but can never make the system less safe.
- Some red-flag phrasings will be missed by keywords. The menu wording and the clinic's website
  still tell patients to call 997 for emergencies; the bot is not the only safety net.
