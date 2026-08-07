---
name: cicd-railway
display_name: Railway investigation
description: Railway deployments and their status, for the services this project runs on it.
domain: cicd
applies_when:
  alert_sources: [railway]
  tags: [cicd, deployments, paas]
directs_tools:
  - railway_pipeline_statistics
  - railway_failed_runs
requires:
  integrations: [railway]
---

# Railway investigation

## Order of operations

1. **Shape before detail.** Call `railway_pipeline_statistics` over the symptom
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
   `railway_failed_runs`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Railway
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Railway specifics

- The API is GraphQL over a single endpoint; the operation is in the body and the path never changes.
- Records arrive wrapped in `edges[].node`, which is why the grouping field is `node.status`.
- `status` is `SUCCESS`, `FAILED`, `BUILDING`, `DEPLOYING`, or `CRASHED` — the last of which is the one that matters during an incident.
