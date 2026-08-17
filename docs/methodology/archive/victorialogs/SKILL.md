---
name: logstore-victorialogs
display_name: VictoriaLogs investigation
description: LogsQL against VictoriaLogs, counted by stream field before any line is read, for the estates that chose it for its ingest cost.
domain: logstore
applies_when:
  alert_sources: [victorialogs]
  tags: [logstore, logs, logsql]
directs_tools:
  - victorialogs_log_statistics
  - victorialogs_sample_logs
requires:
  integrations: [victorialogs]
---

# VictoriaLogs investigation

## Order of operations

1. **Shape before detail.** Call `victorialogs_log_statistics` over the symptom
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
   `victorialogs_sample_logs`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for VictoriaLogs
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## VictoriaLogs specifics

- LogsQL: `_stream:{app="checkout"} error` — the stream filter first, then the word filter, which is what keeps a query cheap.
- `_time:1h` inside the query is an alternative to the call's window and takes precedence over it.
- The `hits` endpoint counts without returning lines and is the cheapest possible connectivity check, which is why the probe uses it.
