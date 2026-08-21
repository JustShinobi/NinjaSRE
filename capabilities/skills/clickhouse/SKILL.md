---
name: database-clickhouse
display_name: ClickHouse investigation
description: ClickHouse over its HTTP interface: what the server is currently executing, and the slowest queries in the log.
domain: database
applies_when:
  alert_sources: [clickhouse]
  tags: [database, olap, sql]
directs_tools:
  - clickhouse_session_statistics
  - clickhouse_slow_queries
requires:
  integrations: [clickhouse]
---

# ClickHouse investigation

## Order of operations

1. **Shape before detail.** Call `clickhouse_session_statistics` over the symptom
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
   `clickhouse_slow_queries`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for ClickHouse
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## ClickHouse specifics

- `FORMAT JSON` is what makes the answer parseable; without it ClickHouse returns tab-separated text and the client sees no records at all.
- `system.processes` is what is running now; `system.query_log` is what ran. An incident usually needs the first, then the second.
- On a cluster, `system.processes` is per node — `clusterAllReplicas` is what makes it cluster-wide, and it is worth adding to the query on a sharded install.
