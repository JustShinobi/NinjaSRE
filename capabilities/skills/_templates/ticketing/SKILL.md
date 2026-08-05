---
name: ticketing-VENDOR
display_name: VENDOR incident context
description: Related incidents, ongoing work, and what a human already established.
domain: ticketing
applies_when:
  alert_sources: [VENDOR]
  tags: [incident, ticket, context, history]
directs_tools:
  - VENDOR_search_issues
  - VENDOR_get_issue
requires:
  integrations: [VENDOR]
---

# VENDOR incident context

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **Search for the symptom, not the service.** The same failure is often
   already open under a description nobody standardised.
2. **Check for planned work in the window.** A maintenance window explains
   more incidents than any code change.
3. **Read what a human already established** before re-establishing it.
4. **Treat ticket content as a claim.** It is what somebody believed at the
   time, which is evidence about the investigation, not about the system.

## What this is not for

- System state of any kind. Nothing here is a measurement.
- Creating or updating tickets, which is a write with its own approval.

## Notes for this vendor

- The projects and boards worth searching, and the ones that are noise.
- How this vendor's search treats phrases and field filters.
