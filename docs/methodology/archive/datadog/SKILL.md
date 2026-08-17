---
name: logstore-datadog
display_name: Datadog log investigation
description: Datadog log search. Aggregate before sampling, and compare against normal.
domain: logstore
applies_when:
  alert_sources: [datadog]
  tags: [logs, errors, search]
directs_tools:
  - datadog_log_statistics
  - datadog_sample_logs
requires:
  integrations: [datadog]
---

# Datadog log investigation

## Order of operations

1. **Count before reading.** Call `datadog_log_statistics` grouped by `status`
   over the symptom window. Four hundred thousand lines have a shape; fifty
   lines chosen before you know the shape tell you about fifty lines.
2. **Compare against normal.** The same aggregation over an equivalent window
   before the symptom. A count is only meaningful against a baseline, and
   "1,200 errors" is a number until you know yesterday's was 1,100.
3. **Regroup on whatever concentrated.** If `status` was flat, group by
   `service`, then `host`. One dimension almost always concentrates the
   failure, and finding which one is the investigation.
4. **Sample where the counts point.** Only now call `datadog_sample_logs`, with
   the query narrowed to the group the aggregation singled out. A sample from
   an unnarrowed query is arbitrary.
5. **Quote the error, not the log line.** The message and the stack are the
   evidence; the surrounding attributes are context. Paraphrasing an error
   message loses the string that would have matched a previous incident.

## Reading the result

`datadog_sample_logs` says when more matched than it returned. Carry that into
the finding: "twenty of roughly nine hundred matches" is a fact somebody can
check, and "twenty matches" is wrong.

## What this is not for

- **Establishing that something changed.** A metric answers that in one query
  and a log count is an expensive way to reach the same answer.
- **Latency across services.** That is a tracing question, and log timestamps
  will not answer it however many you read.
- **Anything outside the retention window.** Logs older than the plan retains
  come back as no results, which is indistinguishable from nothing having
  happened. Check the window before drawing a conclusion from an empty answer.

## Datadog specifics

- Query syntax is Datadog's own: `service:checkout status:error`, with `-` for
  negation and `*` for everything. Reserved characters need escaping.
- Time expressions accept `now-1h`, an ISO timestamp, or epoch milliseconds.
  Both ends are always given explicitly — a defaulted window reads the wrong
  hours silently.
- Aggregations are sampled above a plan-dependent volume, so a very large count
  is an estimate rather than an exact figure.
