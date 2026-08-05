---
name: vcs-VENDOR
display_name: VENDOR change investigation
description: What shipped, when, and by whom, correlated against the symptom onset.
domain: vcs
applies_when:
  alert_sources: [VENDOR]
  tags: [deploy, change, release, code]
directs_tools:
  - VENDOR_list_recent_commits
  - VENDOR_get_change
requires:
  integrations: [VENDOR]
---

# VENDOR change investigation

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **List changes in the window before the onset.** Deploys land before
   symptoms appear, sometimes by hours.
2. **Filter to the failing component**, then widen only if nothing lands.
3. **Read the change, not the message.** What it touched decides whether a
   mechanism is plausible.
4. **Correlation is a suspect, not a cause.** Deploys are frequent; one
   near the onset is weak evidence until the mechanism connects them.

## What this is not for

- Establishing the symptom, which comes first.
- Configuration changes that do not pass through version control.

## Notes for this vendor

- The lag between a merge and the change being live.
- Whether deploys are traceable to commits at all in this setup.
