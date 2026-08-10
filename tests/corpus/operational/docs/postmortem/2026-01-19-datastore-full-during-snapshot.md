# A datastore filled during a snapshot and froze its guests

The snapshot allocated more than the datastore had left.

## Symptom

Four guests on one datastore stopped writing. The hypervisor reported the
datastore at 100% and the guests as running.

## Investigation

A snapshot was taken of the largest guest while the datastore was already at
84%. The snapshot's copy-on-write allocation consumed the remainder within the
hour.

## Root cause

Snapshots were taken without a free-space precondition, and the datastore's
high-water mark was reported but never gated on.

## Correction

Added a free-space precondition to the snapshot procedure and a detector on
datastore usage with a firing value below the point a snapshot can complete.
