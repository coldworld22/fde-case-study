# 3. Rollout plan

Six weeks from kickoff to all three branches, with a go/no-go at each step.

| Week | Step | Who | Exit criterion |
|---|---|---|---|
| 1 | Discovery on site, metrics baseline | Me, ops manager, reception | Metrics and scope signed off ([discovery](01-discovery.md)) |
| 2 | Build; triage rules and Arabic wording reviewed by the medical director | Me, medical director | Director signs the red-flag list and emergency message |
| 2 | Meta Business verification, phone number migration, reminder templates submitted | Clinic admin, me | Templates `appointment_reminder` (ar, en) approved |
| 3 | Staging: real Odoo copy, test number, staff role-play 50 bookings | Reception team | 0 double entries, 0 wrong-branch bookings |
| 4 | **Pilot**: Abha branch, Dermatology and Dentistry only, 08:00-14:00 | 1 receptionist watching `/ops/summary` | Week of pilot: ≥ 30 bookings, no incidents, outbox never > 1 h behind |
| 5 | All specialties at Abha; QR code on reception desks and Google Maps listing | Ops manager | Unanswered morning calls trending down |
| 6 | Khamis Mushait and Muhayil Asir | Branch managers | Same as pilot |
| 8 | Metrics review against baseline | Sponsor, me | Decide phase 2 (insurance, payments) |

## Training (30 minutes per branch)

1. How WhatsApp bookings appear in the Odoo calendar (title starts with the `AMC-` reference).
2. Moving or cancelling a WhatsApp booking in Odoo: do it as usual; tell the patient on WhatsApp.
3. What to do if a patient says the bot didn't understand: book by hand, note the phrase, send it
   to IT so the keyword list can be extended.

## Rollback

The WhatsApp number keeps working without the bot. Pointing the webhook URL back to the old
inbox (one field in Meta's app dashboard) returns to manual replies in under a minute. Bookings
already made stay in Odoo.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Template approval delayed by Meta | Medium | Submitted in week 2; reminders are the only feature that needs it |
| Patients describe needs the keywords miss | High at first | Defaults to General Medicine (always safe); weekly review of unmatched reasons; optional LLM routing |
| Reception bypasses the bot and books by phone into WhatsApp-held slots | Medium | Both book the same Odoo calendar in phase 2; phase 1 slots are a separate block per day |
| Odoo outage longer than a day | Low | Outbox holds events; `/ops/summary` shows `pending`; runbook step to replay |
