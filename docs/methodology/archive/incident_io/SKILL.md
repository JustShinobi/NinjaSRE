---
name: incident-incident_io
display_name: incident.io investigation
description: incident.io's record of what is happening: the open incidents, one incident's timeline, and the acknowledgement that says somebody is on it.
domain: incident
applies_when:
  alert_sources: [incident_io]
  tags: [incident, incidents, response]
directs_tools:
  - incident_io_incident_statistics
  - incident_io_incident_timeline
  - incident_io_acknowledge_incident
requires:
  integrations: [incident_io]
---

# incident.io investigation

## Order of operations

1. **Shape before detail.** Call `incident_io_incident_statistics` over the symptom
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
   `incident_io_incident_timeline`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## Before writing anything

`incident_io_acknowledge_incident` changes something outside NinjaSRE. It is
gated: a human approves it, and the rollback plan is recorded before it runs.
Reach for it only once the investigation has something worth saying, and never
to ask a question — a read answers questions and a write does not.

## What this is not for

- **A question another system answers in one call.** Reaching for incident.io
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## incident.io specifics

- `incident_status.category` is `triage`, `live`, `learning`, or `closed`, and it is the grouping that separates what is happening from what is being written up.
- `severity.rank` is numeric and comparable; `severity.name` is not, and sorting by the name gives alphabetical order rather than importance.
- Pagination is an opaque `after` cursor in `pagination_meta`, not a page number.
