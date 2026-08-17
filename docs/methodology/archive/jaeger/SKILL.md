---
name: tracing-jaeger
display_name: Jaeger investigation
description: Jaeger's trace store: where a service's operations concentrate latency, and the slowest traces behind that concentration.
domain: tracing
applies_when:
  alert_sources: [jaeger]
  tags: [tracing, traces, latency]
directs_tools:
  - jaeger_trace_statistics
  - jaeger_slow_traces
requires:
  integrations: [jaeger]
---

# Jaeger investigation

## Order of operations

1. **Shape before detail.** Call `jaeger_trace_statistics` over the symptom
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
   `jaeger_slow_traces`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Jaeger
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Jaeger specifics

- `minDuration` accepts Go duration strings — `1s`, `500ms` — and is the cheapest way to make a search return exemplars rather than a sample.
- `tags` takes a JSON object as a string, which is how an error-only search is expressed: `{"error":"true"}`.
- A trace's spans are nested under `spans`, so the operation grouping reaches one level down.
