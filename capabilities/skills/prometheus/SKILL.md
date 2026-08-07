---
name: metrics-prometheus
display_name: Prometheus investigation
description: PromQL evaluation and the alert rules currently firing, from the server that holds the series rather than from a dashboard on top of it.
domain: metrics
applies_when:
  alert_sources: [prometheus]
  tags: [metrics, metrics, promql]
directs_tools:
  - prometheus_metric_statistics
  - prometheus_active_alerts
requires:
  integrations: [prometheus]
---

# Prometheus investigation

## Order of operations

1. **Shape before detail.** Call `prometheus_metric_statistics` over the symptom
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
   `prometheus_active_alerts`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Prometheus
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Prometheus specifics

- PromQL: `rate(http_requests_total{job="checkout",status=~"5.."}[5m])`. The range selector inside the query is separate from the window given to the call.
- `start` and `end` are RFC3339 or Unix seconds, and `step` is what decides how many points come back.
- Grouping by `metric.job` or `metric.instance` is what separates one bad instance from a fleet-wide change, and it is the first question worth asking.
