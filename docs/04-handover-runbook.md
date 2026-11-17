# 4. Handover runbook

For the clinic's IT contractor. Everything here can be done without the original developer.

## Running it

```bash
cp .env.example .env              # fill in WhatsApp and Odoo values
docker compose up -d --build      # bot, worker, PostgreSQL
docker compose run --rm seed      # first time only: branches and slots
```

The webhook URL to register in Meta (WhatsApp > Configuration) is
`https://<your-domain>/webhook`, with the verify token from `CLINICBOT_WHATSAPP_VERIFY_TOKEN`.
Subscribe to the `messages` field.

## Daily check (2 minutes)

```bash
curl -s https://<your-domain>/ops/summary
# {"appointments": {"confirmed": 412, "cancelled": 37}, "odoo_outbox": {"done": 449, "pending": 0}}
```

| You see | Meaning | Do |
|---|---|---|
| `pending` small and falling | Normal | Nothing |
| `pending` growing | Odoo unreachable | Check Odoo is up and the API key works; the worker catches up by itself |
| `failed` > 0 | An event gave up after 6 attempts | See "Replaying failed Odoo events" |
| `/health/ready` not `200` | Database unreachable | `docker compose ps`, then `docker compose logs db` |

## Replaying failed Odoo events

```sql
-- See why they failed
SELECT id, kind, appointment_id, attempts, last_error FROM outbox WHERE status = 'failed';
-- After fixing the cause (e.g. a rotated API key), retry them
UPDATE outbox SET status = 'pending', attempts = 0, next_attempt_at = now() WHERE status = 'failed';
```

## Common changes

| Change | Where | Deploy |
|---|---|---|
| Message wording | `src/clinicbot/messages.py` (Arabic and English side by side) | Rebuild image |
| A phrase that should route to a specialty | `KEYWORDS` in `src/clinicbot/triage.py`, plus a test in `tests/test_triage.py` | Rebuild image |
| Red-flag phrases | `RED_FLAGS` in `triage.py`. **Medical director sign-off required** | Rebuild image |
| Turn on LLM routing | `CLINICBOT_TRIAGE_MODE=llm` and the `LLM_*` variables | Restart `bot` |
| Rotate WhatsApp or Odoo secrets | `.env` | `docker compose up -d` |

## Rotating the WhatsApp access token

Use a **System User** token from Meta Business Settings (does not expire), not the 24-hour test
token. Put it in `CLINICBOT_WHATSAPP_ACCESS_TOKEN` and restart `bot` and `worker`.

## Backups

PostgreSQL volume `db`: nightly `pg_dump` to the clinic's backup share, 30 days kept. Odoo
remains the system of record; the bot's database can be rebuilt from scratch without losing
bookings already synced.

## Contacts

| Topic | Owner |
|---|---|
| Wording, specialties, branches | Operations manager |
| Red flags and emergency message | Medical director |
| Hosting, secrets, backups | IT contractor |
| Meta account and templates | Clinic admin (Business Manager owner) |
