---
name: data_platform-flink
display_name: Flink investigation
description: Flink's JobManager REST API: which jobs are running, and the ones that failed or restarted, which is where a streaming backlog starts.
domain: data_platform
applies_when:
  alert_sources: [flink]
  tags: [data_platform, streaming, jobs]
directs_tools:
  - flink_pipeline_health
  - flink_recent_failures
requires:
  integrations: [flink]
---

# Flink investigation

## Order of operations

1. **Shape before detail.** Call `flink_pipeline_health` over the symptom
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
   `flink_recent_failures`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Flink
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Flink specifics

- `state` is `RUNNING`, `FAILED`, `RESTARTING`, `CANCELED`, or `FINISHED`; `RESTARTING` repeatedly is the signature of a job in a crash loop and shows as `RUNNING` if only sampled once.
- `start-time` and `duration` are epoch milliseconds, and a long-running job's duration is not a problem in a streaming cluster.
- The JobManager address changes on failover in a high-availability setup, which is the argument for pointing this at a stable proxy rather than a pod.
