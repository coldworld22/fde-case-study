# 3. Sync to Odoo through a transactional outbox

Date: 2026-11-17 · Status: accepted

## Context

Odoo is the clinic's system of record, but it runs on a server in one branch whose uplink drops
two or three times a week. Calling Odoo while the patient waits would make the bot fail whenever
Odoo does. Writing to our database and then calling Odoo separately risks bookings that never
reach Odoo if the process dies in between.

## Decision

Booking a slot, creating the appointment and inserting an `outbox` row happen in one database
transaction. A separate worker delivers outbox rows to Odoo over JSON-RPC in id order, with
exponential backoff (1, 2, 4 … 60 minutes) and gives up after 6 attempts, marking the row
`failed` with the last error.

Delivery is idempotent: the Odoo calendar event id is stored on the appointment, so a retried
"created" event never makes a second calendar entry. A cancellation that arrives before the
booking ever reached Odoo results in nothing being created.

## Consequences

- Patients can book while Odoo is down; reception sees the bookings when it comes back.
- Odoo can lag by minutes during an outage. Reception was told to expect this.
- One more process to run (the worker), and failed rows need a human; the runbook covers both.
