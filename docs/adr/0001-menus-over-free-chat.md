# 1. Numbered menus, not a free-chat agent

Date: 2026-11-17 · Status: accepted

## Context

The client asked for "AI on WhatsApp". A fully conversational agent (an LLM with booking tools)
demos well, but in a clinic it can book the wrong day, invent a branch, or answer medical
questions nobody signed off on. Patients here mostly use mid-range Android phones and type in
Arabic dialect with Arabic-Indic digits.

## Decision

The flow is a state machine with numbered choices. Free text is accepted in exactly one place,
the visit reason, and only to choose a specialty. Every other step is a number, a name, an ID
or yes/no, in Arabic or English.

## Consequences

- Every path is covered by tests; a booking can only happen after an explicit "yes".
- Works identically with or without an LLM.
- Less "magical" than a chat agent. The medical director and the reception lead preferred it.
- Adding a step (e.g. insurance) means adding a state, not re-prompting a model.
