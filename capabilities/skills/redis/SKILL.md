---
name: database-redis
display_name: Redis Cloud investigation
description: The Redis Cloud control plane: which databases exist in a subscription and in what state, which is what an HTTP-reachable Redis can answer.
domain: database
applies_when:
  alert_sources: [redis]
  tags: [database, cache, redis]
directs_tools:
  - redis_session_statistics
  - redis_slow_queries
requires:
  integrations: [redis]
---

# Redis Cloud investigation

## Order of operations

1. **Shape before detail.** Call `redis_session_statistics` over the symptom
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
   `redis_slow_queries`, narrowed to the group the distribution
   singled out. A sample from an unnarrowed question is arbitrary.
5. **Quote what you found, not a paraphrase of it.** The exact string is what
   matches a previous incident; a summary of it is not.

## Reading the result

Both capabilities say when more matched than they returned. Carry that into the
finding: "twenty of roughly nine hundred" is a fact somebody can check, and
"twenty" is wrong.

## What this is not for

- **A question another system answers in one call.** Reaching for Redis Cloud
  because it is configured, rather than because it holds the evidence, spends an
  iteration and returns something plausible.
- **Anything outside the retention or history this deployment keeps.** An empty
  answer from beyond the window is indistinguishable from nothing having
  happened, and only one of those is a finding.

## Redis Cloud specifics

- `status` is `active`, `pending`, or `error`, and grouping by it answers whether any subscription is mid-change.
- Database endpoints are inside a subscription, so reading them is a second call per subscription id.
- Rate limiting is strict — a handful of requests a minute — so a walk that pages aggressively is the thing most likely to be throttled.
