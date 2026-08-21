---
name: cicd-jenkins
display_name: Jenkins investigation
description: Jenkins build history: how a job has been doing lately, and the builds that failed, for the estates whose pipelines still run there.
domain: cicd
applies_when:
  alert_sources: [jenkins]
  tags: [cicd, ci, builds]
directs_tools:
  - jenkins_pipeline_statistics
  - jenkins_failed_runs
requires:
  integrations: [jenkins]
---

# Jenkins investigation

## Order of operations

1. **Shape before detail.** Call `jenkins_pipeline_statistics` over the symptom
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
   `jenkins_failed_runs`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Jenkins
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Jenkins specifics

- `tree=jobs[name,color]` is the cheapest useful call; `color` encodes both the last result and whether a build is running — `red`, `blue`, `blue_anime`.
- Range syntax `{0,20}` inside `tree` caps a nested list, which is how build history stays bounded.
- `timestamp` is epoch milliseconds, and it is the field to line up against the start of a symptom.
