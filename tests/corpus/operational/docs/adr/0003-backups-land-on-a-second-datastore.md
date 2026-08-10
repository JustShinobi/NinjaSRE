# 3. Backups land on a second datastore

## Status

Accepted.

## Context

Backups written to the same datastore as the guests they protect are backups of
a datastore against every failure except the one that takes the datastore.

## Decision

Every backup job targets a datastore on separate hardware from the guests it
protects.

## Consequences

A restore is slower because it crosses the network. The datastore's own
capacity has to be planned for the retention, not for the working set.
