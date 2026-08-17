---
name: metrics-amplitude
display_name: Amplitude investigation
description: Amplitude's product analytics: how user-facing event volume moved during a window, and which annotations mark what changed.
domain: metrics
applies_when:
  alert_sources: [amplitude]
  tags: [metrics, analytics, product]
directs_tools:
  - amplitude_metric_statistics
  - amplitude_active_alerts
requires:
  integrations: [amplitude]
---

# Amplitude investigation

## Order of operations

1. **Shape before detail.** Call `amplitude_metric_statistics` over the symptom
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
   `amplitude_active_alerts`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Amplitude
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Amplitude specifics

- `e` is a JSON object as a string: `{"event_type":"Checkout Completed"}`.
- Segmentation answers series labels and daily counts rather than a distribution across a field, so the grouping here is over the series Amplitude returned and is coarser than in the telemetry vendors.
- Annotations are the closest thing Amplitude has to a change history and are what line a metric movement up against a release.
