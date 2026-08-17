---
name: incident-blameless
display_name: Blameless investigation
description: Blameless's incident record: what is open, one incident's events, and the update that says an automated investigation is under way.
domain: incident
applies_when:
  alert_sources: [blameless]
  tags: [incident, incidents, retrospectives]
directs_tools:
  - blameless_incident_statistics
  - blameless_incident_timeline
  - blameless_acknowledge_incident
requires:
  integrations: [blameless]
---

# Blameless investigation

## Order of operations

1. **Shape before detail.** Call `blameless_incident_statistics` over the symptom
   window first. It returns a distribution rather than records, so it is
   affordable on a question that matches a great deal, and the group it singles
   out is where the detail should come from.
2. **Compare against normal.** The same call over an equivalent window before
   the symptom. A count is only meaningful against a baseline: "1,200" is a
   number until you know yesterday's was 1,100.
3. **Regroup on whatever concentrated.** If the first grouping was flat, group
   by another field. One dimension almost always concentrates a failure, and
   finding which one is the investigation.
4. **Read where the counts point.** Only now call
   `blameless_incident_timeline`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## Before writing anything

`blameless_acknowledge_incident` changes something outside NinjaSRE. It is
gated: a human approves it, and the rollback plan is recorded before it runs.
Reach for it only once the investigation has something worth saying, and never
to ask a question — a read answers questions and a write does not.

## What this is not for

- **A question another system answers in one call.** Reaching for Blameless
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Blameless specifics

- `status` is `active`, `mitigated`, or `resolved`; grouping by `severity` is what separates the ones that matter.
- Incident ids are stable and are what a retrospective refers to later.
- Timestamps are RFC3339 in UTC, and a naive timestamp is rejected rather than assumed.
