# 1. One control plane per cluster

## Status

Accepted.

## Context

Two clusters were run from a single control plane for a year. Every upgrade of
the control plane was an outage window for both, and a misconfiguration in one
cluster's storage declaration was applied to the other.

## Decision

One control plane per cluster. The clusters are related by convention and by
naming, and by nothing that runs.

## Consequences

Two upgrades instead of one. A change that only makes sense applied to both has
to be applied twice, deliberately, which is the property this buys.
