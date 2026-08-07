---
name: cicd-vercel
display_name: Vercel investigation
description: Vercel deployments: how the recent ones have gone for a project, and the ones that errored, which is usually the whole story for a frontend incident.
domain: cicd
applies_when:
  alert_sources: [vercel]
  tags: [cicd, deployments, frontend]
directs_tools:
  - vercel_pipeline_statistics
  - vercel_failed_runs
requires:
  integrations: [vercel]
---

# Vercel investigation

## Order of operations

1. **Shape before detail.** Call `vercel_pipeline_statistics` over the symptom
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
   `vercel_failed_runs`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Vercel
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Vercel specifics

- `state` is `BUILDING`, `READY`, `ERROR`, or `CANCELED`; grouping by it answers whether a failure is new or the project has been red for a while.
- `app` is the project name and `projectId` is the identifier — both are accepted and only one of them appears in the answer.
- `created` is epoch milliseconds and is what lines a deployment up against the start of a symptom.
