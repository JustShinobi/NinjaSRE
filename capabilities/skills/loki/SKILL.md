---
name: logstore-loki
display_name: Loki investigation
description: Log search over Loki's label index and LogQL, with the shape of a query counted before any line of it is read.
domain: logstore
applies_when:
  alert_sources: [loki]
  tags: [logstore, logs, logql]
directs_tools:
  - loki_log_statistics
  - loki_sample_logs
requires:
  integrations: [loki]
---

# Loki investigation

## Order of operations

1. **Shape before detail.** Call `loki_log_statistics` over the symptom
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
   `loki_sample_logs`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Loki
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Loki specifics

- LogQL is `{label="value"} |= "substring"`. The stream selector is mandatory and is what bounds the scan.
- Times are RFC3339 or Unix nanoseconds. Seconds are accepted and mean 1970, which returns nothing.
- `direction=backward` returns newest first, which is what a sample wants; the count is unaffected by it.
