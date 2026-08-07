---
name: logstore-openobserve
display_name: OpenObserve investigation
description: SQL search over OpenObserve streams, counted by field before any record is read, for the estates that chose it for its storage cost.
domain: logstore
applies_when:
  alert_sources: [openobserve]
  tags: [logstore, logs, sql]
directs_tools:
  - openobserve_log_statistics
  - openobserve_sample_logs
requires:
  integrations: [openobserve]
---

# OpenObserve investigation

## Order of operations

1. **Shape before detail.** Call `openobserve_log_statistics` over the symptom
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
   `openobserve_sample_logs`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for OpenObserve
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## OpenObserve specifics

- `SELECT * FROM logs WHERE level = 'error' AND service = 'checkout'` — the stream name is the table.
- Aggregation is available in SQL directly: `SELECT level, count(*) FROM logs GROUP BY level` pushes the counting to the server when the stream is large.
- `from` is the offset parameter, and a deep offset is slower rather than refused.
