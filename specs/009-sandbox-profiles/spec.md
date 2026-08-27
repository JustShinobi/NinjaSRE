# Feature 009 — Sandbox Profiles

- **Wave:** 1 — Trust & Safety
- **Branch:** `feat/009-sandbox-profiles`
- **Status:** Draft
- **Depends on:** 001, 004, 007
- **Blocks:** 017, 030

## Summary

Three isolation profiles behind one port — `process`, `container`, and
`kubernetes` — governing where capability execution runs, what it can reach, and
what resources it may consume. Because feature 007 already removed credentials
from the agent's reach, sandboxing is about resource and egress control rather
than secret containment, which is what makes the lighter profiles genuinely safe.

## User scenarios

### Primary story

A developer runs the `process` profile locally with no Docker or Kubernetes.
A team runs `container` in production. A regulated enterprise runs `kubernetes`
with per-investigation pods and Envoy-enforced egress. All three execute the same
capability code with the same guarantees about what it can reach.

### Acceptance scenarios

1. **Given** any profile, **when** a capability executes, **then** it can reach
   only the credential proxy and hosts on the integration's allow-list.
2. **Given** the `process` profile, **when** a capability exceeds its CPU, memory,
   or wall-clock limit, **then** it is terminated and a structured error returned.
3. **Given** the `container` profile, **when** an investigation starts, **then** a
   container is provisioned with a read-only root filesystem, a writable scratch
   mount, and no host network access.
4. **Given** the `kubernetes` profile, **when** an investigation starts, **then** a
   pod is claimed from a warm pool, an Envoy sidecar enforces the egress
   allow-list, and a TTL bounds its lifetime.
5. **Given** a warm pool, **when** an investigation starts, **then** provisioning
   latency stays under the configured target.
6. **Given** an investigation ends or its TTL expires, **when** cleanup runs,
   **then** the sandbox and all its resources are removed.
7. **Given** a capability attempting to reach an unlisted host, **when** it runs in
   any profile, **then** the connection is refused and the attempt is audited.
8. **Given** two concurrent investigations, **when** both execute capabilities,
   **then** neither can observe the other's filesystem, processes, or network.
9. **Given** a sandbox that fails to provision, **when** it happens, **then** the
   investigation fails with a clear error and never falls back to an unsandboxed
   path.

### Edge cases

- A long-running capability (log tail) outliving the sandbox TTL.
- Warm-pool exhaustion under a burst of concurrent investigations.
- A node evicting a sandbox pod mid-investigation.
- A capability legitimately needing large scratch space (a large log download).
- Cleanup after an agent crash leaving orphaned sandboxes.
- The `process` profile on Windows, where cgroup-style limits are unavailable.

## Requirements

### Functional

**Port and profiles**

- **FR-001** A `Sandbox` port MUST define: provision, execute, stream, interrupt,
  and release.
- **FR-002** Three implementations MUST exist: `process`, `container`,
  `kubernetes`.
- **FR-003** All three MUST pass the same contract test suite, so capability
  behaviour is identical across profiles.
- **FR-004** The credential proxy MUST be reachable from every profile, and MUST be
  the only route to authenticated external calls.
- **FR-005** Profile selection MUST be deployment configuration, never per-capability.
- **FR-006** A provisioning failure MUST fail the investigation with a clear error.
  There MUST be no unsandboxed fallback.

**Resource bounds**

- **FR-007** Every profile MUST enforce CPU, memory, wall-clock, and scratch-disk
  limits from named constants.
- **FR-008** Exceeding a limit MUST terminate execution and return a structured
  error identifying which limit was hit.
- **FR-009** Process-count limits MUST be enforced, since capabilities may fork.

**Egress**

- **FR-010** Egress MUST be restricted to the credential proxy and the union of
  allow-listed hosts for the team's configured integrations.
- **FR-011** In `kubernetes`, egress MUST be enforced by a sidecar proxy, not only
  by application-level cooperation.
- **FR-012** A blocked egress attempt MUST be audited with target, capability, and
  investigation.

**Lifecycle**

- **FR-013** `kubernetes` MUST support a warm pool with a configurable size and a
  claim mechanism.
- **FR-014** Every sandbox MUST have a TTL, refreshable while an investigation is
  active.
- **FR-015** A reaper MUST remove expired and orphaned sandboxes, and MUST be safe
  to run concurrently across replicas.
- **FR-016** Sandboxes MUST be single-tenant: one investigation, never reused
  across tenants without a full reset.
- **FR-017** Interruption MUST propagate to the sandbox so cancellation (feature
  004, FR-016) actually stops work.

**Isolation**

- **FR-018** Concurrent sandboxes MUST NOT share filesystem, process namespace, or
  network namespace.
- **FR-019** The root filesystem MUST be read-only where the profile supports it,
  with an explicit writable scratch mount.
- **FR-020** Capability code and skill bodies MUST be delivered into the sandbox
  as immutable content; a sandbox MUST NOT be able to modify what it will execute
  next.

**Observability**

- **FR-021** Sandbox lifecycle events MUST be recorded in the run trace.
- **FR-022** Health MUST report pool size, active sandboxes, provisioning latency,
  and reaper status.

### Key entities

| Entity | Description |
|---|---|
| **SandboxProfile** | `process` \| `container` \| `kubernetes` |
| **SandboxSpec** | Resource limits, egress allow-list, TTL, scratch size |
| **SandboxInstance** | A provisioned sandbox with identity, state, and expiry |
| **WarmPool** | Pre-provisioned instances awaiting claim (`kubernetes`) |
| **Claim** | A tenant-scoped binding of an investigation to an instance |
| **EgressPolicy** | The allow-list derived from the team's configured integrations |
| **Reaper** | The concurrent-safe cleanup process |

## Success criteria

- **SC-001** The same contract suite passes against all three profiles.
- **SC-002** An egress attempt to an unlisted host is refused in all three
  profiles — verified by a test capability that tries.
- **SC-003** `kubernetes` warm-pool provisioning stays under the latency target at
  the configured pool size.
- **SC-004** Two concurrent investigations cannot observe each other — verified by
  a test capability probing filesystem, processes, and network.
- **SC-005** A killed agent leaves no orphaned sandboxes after one reaper cycle.
- **SC-006** Provisioning failure fails the investigation with no unsandboxed
  fallback.
- **SC-007** `process` profile works on Linux, macOS, and Windows, with the
  Windows limitation on resource limits documented and its weaker guarantees
  reported at start.

## Out of scope

- Credential handling (feature 007 — already solved before this feature applies)
- Deployment manifests and Helm packaging (feature 030)
- Autoscaling the warm pool (post-MVP)

## Clarifications

| Question | Resolution |
|---|---|
| Why is the light `process` profile acceptable at all? | Because feature 007 means there is no credential to contain. Remaining risks are resource exhaustion and unwanted egress, both of which `process` addresses adequately for single-tenant development. |
| Can an operator mix profiles? | No. Profile is deployment-wide (FR-005). Per-capability profiles would create a matrix of behaviours nobody could reason about. |
| What about the Windows resource-limit gap? | Job Objects cover process count and memory; CPU limits are weaker. The gap is documented and reported at start, and `process` on Windows is a development profile only. |
| Does sandboxing slow investigations? | `process` adds nothing measurable. `container` and `kubernetes` add provisioning latency, which is what the warm pool exists to remove (SC-003). |
