---
name: tracing-tempo
display_name: Tempo investigation
description: TraceQL against Grafana Tempo: which traces match a latency or error condition, and the slowest of them, for estates storing traces in object storage.
domain: tracing
applies_when:
  alert_sources: [tempo]
  tags: [tracing, traces, traceql]
directs_tools:
  - tempo_trace_statistics
  - tempo_slow_traces
requires:
  integrations: [tempo]
---

# Tempo investigation

## Order of operations

1. **Shape before detail.** Call `tempo_trace_statistics` over the symptom
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
   `tempo_slow_traces`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Tempo
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Tempo specifics

- TraceQL: `{ resource.service.name = "checkout" && duration > 1s }`. The braces are part of the syntax and a bare service name is not a valid query.
- `rootServiceName` and `rootTraceName` are the two fields a search result carries without fetching the trace, and are the useful groupings.
- `spss` limits spans per span-set, which is what keeps a search answer small when traces are wide.
