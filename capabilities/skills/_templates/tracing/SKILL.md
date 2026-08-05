---
name: tracing-VENDOR
display_name: VENDOR trace investigation
description: Distributed traces. The signal that answers where the time went.
domain: tracing
applies_when:
  alert_sources: [VENDOR]
  tags: [traces, latency, spans, dependencies]
directs_tools:
  - VENDOR_search_traces
  - VENDOR_get_trace
requires:
  integrations: [VENDOR]
---

# VENDOR trace investigation

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **Find slow traces, not average ones.** Search the tail of the latency
   distribution over the symptom window.
2. **Read the span tree, not the total.** The question is which span holds
   the time, and whether it holds it in itself or in a child.
3. **Compare against a fast trace of the same operation.** The difference
   between the two trees is usually the whole answer.
4. **Follow the time across the service boundary.** Time in a child service
   makes that service's investigation the next one.

## What this is not for

- Errors with no latency component, which the logs describe directly.
- Anything on a path that is not instrumented — check coverage first.

## Notes for this vendor

- The sampling rate, which decides whether the slow trace even exists.
- How this vendor names the operations an investigation will search for.
