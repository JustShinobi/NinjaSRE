---
name: logstore-VENDOR
display_name: VENDOR log investigation
description: Log search and aggregation. Statistics before samples, always.
domain: logstore
applies_when:
  alert_sources: [VENDOR]
  tags: [logs, errors, search]
directs_tools:
  - VENDOR_log_statistics
  - VENDOR_sample_logs
requires:
  integrations: [VENDOR]
---

# VENDOR log investigation

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **Count before reading.** Aggregate by status, service, and host over the
   symptom window. Four hundred thousand lines have a shape; fifty lines
   chosen before you know the shape tell you about fifty lines.
2. **Compare against normal.** The same aggregation over an equivalent window
   before the symptom. A count is only meaningful against a baseline.
3. **Sample where the counts point.** Now read individual lines, from the
   group the aggregation singled out.
4. **Extract the error, not the log line.** The message and stack are the
   evidence; the surrounding fields are context.

## What this is not for

- Establishing that something changed — a metric answers that in one query.
- Latency across services, which is a tracing question.

## Notes for this vendor

- The query syntax, and any escaping this vendor requires.
- The retention window, which bounds how far back an investigation can look.
- Whether the aggregation is sampled, and above what volume.
