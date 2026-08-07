---
name: logstore-sentry
display_name: Sentry investigation
description: Application errors as Sentry groups them: which issues are open, how often each is firing, and the events behind the ones that matter.
domain: logstore
applies_when:
  alert_sources: [sentry]
  tags: [logstore, errors, issues]
directs_tools:
  - sentry_log_statistics
  - sentry_sample_logs
requires:
  integrations: [sentry]
---

# Sentry investigation

## Order of operations

1. **Shape before detail.** Call `sentry_log_statistics` over the symptom
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
   `sentry_sample_logs`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Sentry
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Sentry specifics

- Search syntax is Sentry's own: `is:unresolved level:error release:4.2.1`, with `environment:` and `firstRelease:` as the two that most often narrow an incident.
- `sort=freq` orders by event count and `sort=date` by last seen. The first answers 'what is loudest', the second 'what is new'.
- A release tag is the cheapest link between an error and a deploy, and it is only there if the SDK was configured to send one.
