---
name: incident-VENDOR
display_name: VENDOR incident context
description: Timeline, responder history, and whether this has happened before.
domain: incident
applies_when:
  alert_sources: [VENDOR]
  tags: [incident, oncall, escalation, postmortem]
directs_tools:
  - VENDOR_search_incidents
  - VENDOR_get_incident_timeline
requires:
  integrations: [VENDOR]
---

# VENDOR incident context

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **Search for prior incidents on the same component first.** A recurrence
   already has a diagnosis, and reproducing it from scratch is the most
   expensive way to reach an answer somebody already wrote down.
2. **Reconstruct this incident's timeline.** Detection, acknowledgement,
   escalation, and every status change, with times. The gaps are as
   informative as the entries.
3. **Read the current incident against the prior one's resolution.** If it
   matches, say which incident and what fixed it. If it does not, say what is
   different — that difference is usually the finding.
4. **Report MTTR context, not an MTTR number.** "Twenty minutes in, against a
   median of eight for this service" is a decision; "MTTR 20m" is a statistic.

## What this is not for

- Diagnosing the failure. The incident record says what people did, not what
  the system did; the telemetry says the second.
- Deciding whether to escalate. That is a human decision with a policy behind
  it.

## Notes for this vendor

- How similar incidents are matched — service, tags, free text — and how good
  that matching actually is here.
- Whether timeline entries include automated transitions or only human ones.
- Retention, which bounds how far back "has this happened before" can look.
