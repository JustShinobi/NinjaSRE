# Declaring an overlay zone's MTU

An overlay zone reserves 50 bytes of every frame for its own header.

## The rule

The zone MTU must be at least 50 below the underlay MTU carrying it. An
underlay at 1450 gives an overlay of 1400. Declaring both at 1450 produces a
network where small packets pass and large ones vanish.

## Checking an existing zone

Read the zone declaration and the underlay interface. Compare. A difference
below 50 is a fault whether or not anything has noticed yet.
