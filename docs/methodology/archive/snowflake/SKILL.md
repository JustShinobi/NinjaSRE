---
name: database-snowflake
display_name: Snowflake investigation
description: Snowflake over its SQL REST API: what is running in the account now, and the slowest statements the query history recorded.
domain: database
applies_when:
  alert_sources: [snowflake]
  tags: [database, warehouse, sql]
directs_tools:
  - snowflake_session_statistics
  - snowflake_slow_queries
requires:
  integrations: [snowflake]
---

# Snowflake investigation

## Order of operations

1. **Shape before detail.** Call `snowflake_session_statistics` over the symptom
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
   `snowflake_slow_queries`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Snowflake
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Snowflake specifics

- `information_schema.query_history()` is per account and bounded to seven days; `snowflake.account_usage.query_history` reaches a year and lags by 45 minutes.
- `execution_status` is `RUNNING`, `SUCCESS`, `FAILED_WITH_ERROR`, or `BLOCKED`, and `BLOCKED` is the one that explains a stall.
- The role in the JWT decides what `query_history` returns: a role without MONITOR sees only its own statements, which reads as a quiet account.
