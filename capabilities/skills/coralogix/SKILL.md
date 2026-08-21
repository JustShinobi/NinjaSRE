---
name: logstore-coralogix
display_name: Coralogix investigation
description: Coralogix log search over DataPrime or Lucene, counted by severity or application before any line is read.
domain: logstore
applies_when:
  alert_sources: [coralogix]
  tags: [logstore, logs, dataprime]
directs_tools:
  - coralogix_log_statistics
  - coralogix_sample_logs
requires:
  integrations: [coralogix]
---

# Coralogix investigation

## Order of operations

1. **Shape before detail.** Call `coralogix_log_statistics` over the symptom
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
   `coralogix_sample_logs`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Coralogix
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Coralogix specifics

- DataPrime is pipeline-shaped: `source logs | filter $l.applicationname == 'checkout' | limit 100`. Lucene is accepted on the same endpoint with a different syntax flag.
- Severity lives at `userData.severity` on a parsed log and is the grouping that answers 'how much of this is actually an error'.
- Timestamps are RFC3339 with a mandatory timezone; a naive timestamp is rejected.
