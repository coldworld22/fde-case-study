# 1. Discovery

> Representative scenario. "Abha Medical Clinics" is a composite of the kind of client I work
> with in the Asir region; names, numbers and people are illustrative. The engineering is real
> and runs in this repository.

## The client

A private outpatient group with three branches (Abha, Khamis Mushait, Muhayil Asir), six
specialties, about 40 doctors. Reception runs on **Odoo 17** (Contacts, Calendar, Invoicing),
hosted on a server in the Abha branch.

## What they asked for

> "Patients keep calling and nobody answers. We want booking on WhatsApp, with AI."

## What discovery found (week 1: two days on site, one day remote)

Method: a morning shift sitting with reception at the Abha branch, two weeks of call logs and
WhatsApp chats, and interviews with the operations manager, two receptionists, the IT
contractor and the medical director. Figures below are illustrative for the scenario.

| Observation | Evidence | Consequence for the design |
|---|---|---|
| Phone lines are the bottleneck, not doctors' calendars | ~35% of calls unanswered at 08:00-10:00; same-week slots still free in 4 of 6 specialties | Self-service booking is the win; nothing has to change in scheduling |
| Patients already message the clinic on WhatsApp | A receptionist answers ~120 WhatsApp chats a day from her own phone | Use the official WhatsApp Business Cloud API on the clinic's number, not a new app |
| Most patients write in Arabic, many with Arabic-Indic digits | Sample of 200 chats: 83% Arabic, ID numbers typed as ١٠٢… | Arabic first, English second; normalise digits everywhere |
| "AI" mainly meant "it knows which doctor I need" | Wrong-specialty bookings cost a wasted slot and a second visit | Route by specialty. Do not diagnose |
| A few patients describe emergencies in chat | Two chest-pain messages in the sample | Red-flag check that redirects to 997 and can never be overridden by a model |
| Odoo is the system of record but its uplink drops | IT contractor: 2-3 outages a week, minutes to hours | Bot must work while Odoo is down; sync with retries |
| Reception searches patients by National ID | Odoo `ref` field already holds IDs for ~70% of patients | Use National ID (Luhn-checked) as the patient key |
| No-shows are ~18% | Odoo calendar export | Reminder the day before |

## Stakeholders

| Who | Cares about | Sign-off on |
|---|---|---|
| Operations manager (sponsor) | Answered demand, no-shows | Scope, go-live |
| Medical director | Patient safety | Triage rules and emergency wording |
| Reception lead | Not doing double entry | Odoo calendar format |
| IT contractor | Not being paged at night | Hosting, runbook |
| DPO (outsourced) | PDPL compliance | Data stored, retention, model usage |

## Success metrics (agreed with the sponsor)

| Metric | Baseline | Target after 8 weeks |
|---|---|---|
| Share of bookings made without a phone call | 0% | ≥ 40% |
| Unanswered calls 08:00-10:00 | ~35% | ≤ 15% |
| No-show rate for WhatsApp bookings | ~18% | ≤ 10% |
| Emergency messages answered with 997 guidance | n/a | 100%, within seconds |
| Double entry by reception | every WhatsApp booking | none |

## Out of scope for phase 1 (and why)

- **Payments and insurance approval**: needs the insurers' portals; phase 2.
- **Free-text medical Q&A**: clinical risk, no medical sign-off.
- **Doctor-level choice**: patients said they care about the time and branch first; reception can
  still move the booking in Odoo.
- **Nafath identity verification**: right for phase 2 if the clinic adds e-prescriptions.

## Constraints

- Patient data stays in Saudi Arabia (PDPL; the clinic's preference). Hosting in a Riyadh region.
- Any LLM call must not carry identifiers. The system must work with no LLM at all.
- WhatsApp: business-initiated messages (reminders) need pre-approved templates.
