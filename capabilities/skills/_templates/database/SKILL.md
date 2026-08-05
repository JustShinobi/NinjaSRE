---
name: database-VENDOR
display_name: VENDOR database investigation
description: Query performance, locking, and replication, read without touching data.
domain: database
applies_when:
  alert_sources: [VENDOR]
  tags: [database, queries, locks, replication]
directs_tools:
  - VENDOR_active_queries
  - VENDOR_query_statistics
requires:
  integrations: [VENDOR]
---

# VENDOR database investigation

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **Look at what is running now.** Long-running and blocked queries are
   the highest-signal observation available and cost one call.
2. **Check for lock contention** before query plans. A slow query holding a
   lock makes every other query look slow.
3. **Compare query statistics against normal.** A plan that changed is a
   different failure from a volume that changed.
4. **Check replication lag** whenever reads and writes disagree.

## What this is not for

- Reading application data. This is about the database's behaviour.
- Schema changes, which are a remediation with approval and rollback.

## Notes for this vendor

- Which statistics views this engine exposes, and their reset semantics.
- The cost of the introspection queries themselves under load.
