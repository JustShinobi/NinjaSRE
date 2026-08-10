# Quorum lost during a routine node reboot

A three-node cluster with one node already down lost quorum when the second was
rebooted for patching.

## Symptom

The cluster reported no quorum. Guest start, stop and migration were refused on
every remaining node.

## Investigation

One node had been down since the previous week for a failed disk and nobody had
reduced the expected vote count. Rebooting a second node left one vote out of
three.

## Root cause

Patching proceeded against a cluster that was already one node short, and the
quorum margin was never checked before the reboot.

## Correction

Added a quorum-margin check to the pre-reboot procedure and a detector that
reports a margin of zero before anybody reboots anything.
