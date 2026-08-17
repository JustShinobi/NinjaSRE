---
name: database-supabase
display_name: Supabase investigation
description: The Supabase management API: which projects exist in an organisation and in what state, for the estates that run their Postgres there.
domain: database
applies_when:
  alert_sources: [supabase]
  tags: [database, postgres, paas]
directs_tools:
  - supabase_session_statistics
  - supabase_slow_queries
requires:
  integrations: [supabase]
---

# Supabase investigation

## Order of operations

1. **Shape before detail.** Call `supabase_session_statistics` over the symptom
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
   `supabase_slow_queries`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Supabase
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Supabase specifics

- `status` is `ACTIVE_HEALTHY`, `PAUSED`, `INACTIVE`, or one of the transition states; grouping by it is the whole health question for a Supabase estate.
- Free-tier projects pause after inactivity, and a paused project is not a failure even though it looks like one.
- `region` on a project is what decides where its Postgres actually is, which matters for latency questions.
