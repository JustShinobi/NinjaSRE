# A hard NFS mount stalled the whole node

One unreachable export took every process that touched the mount point with it.

## Symptom

Processes on the fileserver node entered uninterruptible sleep and never left.
The node answered ping and refused to schedule anything new.

## Investigation

The export the mount points at was on a datastore that had gone offline for a
firmware update. The mount is a hard mount with no timeout, so every read
blocked forever rather than failing.

## Root cause

A hard NFS mount with no timeout turns a temporary storage outage into an
indefinite node stall.

## Correction

Remounted with a bounded timeout and a soft failure. Added the mount to the
double-check queries so a stalled one is visible before somebody notices the
node.
