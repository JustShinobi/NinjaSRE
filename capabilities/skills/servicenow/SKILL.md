---
name: incident-servicenow
display_name: ServiceNow investigation
description: ServiceNow incident records: what is open, one incident's work notes, and the update that records an automated investigation.
domain: incident
applies_when:
  alert_sources: [servicenow]
  tags: [incident, itsm, incidents]
directs_tools:
  - servicenow_incident_statistics
  - servicenow_incident_timeline
  - servicenow_acknowledge_incident
requires:
  integrations: [servicenow]
---

# ServiceNow investigation

## Order of operations

1. **Shape before detail.** Call `servicenow_incident_statistics` over the symptom
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
   `servicenow_incident_timeline`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## Before writing anything

`servicenow_acknowledge_incident` changes something outside NinjaSRE. It is
gated: a human approves it, and the rollback plan is recorded before it runs.
Reach for it only once the investigation has something worth saying, and never
to ask a question — a read answers questions and a write does not.

## What this is not for

- **A question another system answers in one call.** Reaching for ServiceNow
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## ServiceNow specifics

- `sysparm_query` is ServiceNow's encoded query language: `active=true^priority=1^ORDERBYDESCsys_created_on`.
- `priority` combines impact and urgency and is the grouping that answers how much of what is open is actually severe.
- `sys_id` is the stable identifier; the human-readable `number` (INC0012345) is what people quote and is not what the API keys on.
