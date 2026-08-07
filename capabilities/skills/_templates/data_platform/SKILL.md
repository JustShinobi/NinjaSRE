---
name: data_platform-VENDOR
display_name: VENDOR pipeline investigation
description: Consumer lag and backlog before broker or worker internals.
domain: data_platform
applies_when:
  alert_sources: [VENDOR]
  tags: [queue, stream, lag, backlog, pipeline, worker]
directs_tools:
  - VENDOR_consumer_lag
  - VENDOR_list_partitions
requires:
  integrations: [VENDOR]
---

# VENDOR pipeline investigation

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **Read lag first, and read its derivative.** Growing, flat, or draining is
   three different incidents. A large but shrinking backlog is a system
   recovering, and paging for it wastes the page.
2. **Split by partition or shard before concluding.** Aggregate lag hides the
   single hot key that is the whole problem, and the fix for one bad partition
   is not the fix for a slow fleet.
3. **Compare production rate against consumption rate.** Only one of the two
   changed, and which one decides whether to look upstream or at the workers.
4. **Only then read broker or worker internals.** They are the most expensive
   place to look and the least often the answer; a healthy broker serving a
   consumer group that stopped committing looks identical from the inside.

## What this is not for

- The correctness of what the pipeline produced. Lag says whether data is
  late, never whether it is right.
- A batch job's schedule, which is a scheduler question and has its own
  answer.

## Notes for this vendor

- What "lag" means here — messages, bytes, or time — because the three do not
  convert and the alert threshold was written against one of them.
- Whether the metric is per consumer group or per client, and how a rebalance
  shows up in it.
- Retention, because a backlog older than retention is data that is already
  gone rather than data that is late.
