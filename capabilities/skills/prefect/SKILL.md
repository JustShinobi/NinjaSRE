---
name: data_platform-prefect
display_name: Prefect investigation
description: Prefect flow runs: which are in which state, and the ones that failed, for the estates orchestrating their pipelines with it.
domain: data_platform
applies_when:
  alert_sources: [prefect]
  tags: [data_platform, orchestration, flows]
directs_tools:
  - prefect_pipeline_health
  - prefect_recent_failures
requires:
  integrations: [prefect]
---

# Prefect investigation

## Order of operations

1. **Shape before detail.** Call `prefect_pipeline_health` over the symptom
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
   `prefect_recent_failures`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Prefect
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Prefect specifics

- `state.type` is `COMPLETED`, `FAILED`, `CRASHED`, `RUNNING`, `PENDING`, or `CANCELLED`, and it is the grouping that answers the health question.
- `sort=START_TIME_DESC` is what makes a sample the most recent runs.
- Deployment name and flow name are separate fields, and an incident usually names the deployment.
