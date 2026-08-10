# Cluster double-check queries

The checks an experienced operator runs before believing the cluster is well.
Each one is a question with a number behind it, and each is worth watching
continuously rather than only when somebody remembers.

## Quorum margin is above zero

Read the expected and the current vote count. A margin of zero means the next
node to leave takes the cluster with it.

- signal: `cluster.quorum_margin`
- fires when: below 1

## No datastore is above its safe fill

A datastore past this cannot complete a snapshot of its largest guest.

- signal: `datastore.used_percent`
- fires when: above 85

## No backup is older than its schedule

A job that is disabled produces no failures and no backups.

- signal: `backup.age_hours`
- fires when: above 26

## No node is reporting failed units

A failed unit is a service somebody meant to be running.

- signal: `node.failed_units`
- fires when: above 0

## No mount is stalled

A hard mount against an export that has gone away blocks every process that
touches it.

- signal: `node.stalled_mounts`
- fires when: above 0
