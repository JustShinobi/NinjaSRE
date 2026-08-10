# 2. An overlay network per workload class

## Status

Accepted.

## Context

A single flat network meant that any guest could reach any other, and the
firewall rules that expressed the actual policy had to enumerate every pair.

## Decision

One overlay zone per workload class — infra, apps, vk8s — with the policy
expressed between zones rather than between guests.

## Consequences

The rule count drops from the square of the guest count to the square of the
zone count. Every zone declaration must reserve 50 bytes of MTU for the overlay
header, which is a rule somebody has to remember.
