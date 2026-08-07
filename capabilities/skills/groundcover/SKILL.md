---
name: metrics-groundcover
display_name: groundcover investigation
description: groundcover's eBPF-derived service metrics and the monitors currently firing, for clusters instrumented without code changes.
domain: metrics
applies_when:
  alert_sources: [groundcover]
  tags: [metrics, metrics, ebpf]
directs_tools:
  - groundcover_metric_statistics
  - groundcover_active_alerts
requires:
  integrations: [groundcover]
---

# groundcover investigation

## Order of operations

1. **Shape before detail.** Call `groundcover_metric_statistics` over the symptom
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
   `groundcover_active_alerts`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for groundcover
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## groundcover specifics

- The query language is PromQL, so everything true of Prometheus queries is true here, including that the range selector is separate from the call's window.
- `metric.workload` and `metric.namespace` are the two labels that separate one failing deployment from a cluster-wide change.
- Monitors map onto the same alerting model as Prometheus rules, so a firing monitor here and an Alertmanager alert are often the same event twice.
