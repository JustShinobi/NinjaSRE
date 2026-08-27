# Feature 038 — Estate Inventory and Health Model

- **Wave:** 10 — Autonomous operation
- **Branch:** `feat/038-estate-inventory`
- **Status:** Draft
- **Depends on:** 006, 012, 024

## Summary

The set of things the deployment is responsible for, and how each of them is
doing. A node, a virtual machine, a container, a datastore, a cluster, a service,
a backup job — discovered from the integrations that already exist, kept current,
and carrying a health state derived from evidence rather than declared.

Nothing in the first wave holds this. There are integrations that can answer
questions about infrastructure, a knowledge graph that models service topology,
and runs that reference resources by string. What is missing is the noun in
between: a resource the system knows it is watching, with an identity that
survives a restart, a state that means something, and a history.

Everything in the rest of this wave needs it. A detector needs something to
detect a change *on*. An autonomy policy needs a resource to scope a level *to*.
A closed-loop remediation needs a subject whose state it can compare before and
after. The dashboard needs something to summarise.

## User scenarios

### Primary story

An operator connects their hypervisor. Within a minute the console shows their
two nodes, their eleven virtual machines, their six containers, four datastores
and the backup job that covers them — each with a health state, a last-seen time,
and a link to what the system knows about it. They did not enumerate anything.

A month later a container is deleted. It disappears from the estate as gone, not
as unhealthy, and its history remains readable.

### Acceptance scenarios

1. **Given** a configured integration that can enumerate resources, **when**
   discovery runs, **then** the resources it reports appear in the estate with a
   stable identity, a kind, a parent where they have one, and their attributes.
2. **Given** a resource seen before, **when** discovery runs again, **then** it is
   updated, not duplicated — even if its display name changed.
3. **Given** a resource that discovery no longer reports, **when** the sweep
   completes, **then** it is marked absent with a timestamp, and its history is
   retained; it is not deleted and not marked unhealthy.
4. **Given** an integration that fails during discovery, **when** the sweep
   completes, **then** the resources it would have covered are marked stale with
   the reason, and resources from other integrations are unaffected.
5. **Given** a resource with a parent, **when** health is computed, **then** the
   parent's health accounts for its children, and the rule that produced it is
   inspectable.
6. **Given** a resource, **when** it is opened, **then** its current state, its
   recent state changes, the incidents that referenced it, and the runs that
   touched it are all reachable.
7. **Given** two integrations reporting the same underlying thing, **when**
   discovery runs, **then** they reconcile to one resource with both sources
   recorded, not two resources.
8. **Given** an estate of ten thousand resources, **when** the summary is
   requested, **then** it is answered within budget.
9. **Given** a resource whose health has not been refreshed within its declared
   interval, **when** it is read, **then** it reports as stale rather than as its
   last known state.

### Edge cases

- A resource that changes parent — a virtual machine migrated between nodes.
- A resource whose provider identity is reused after deletion.
- An integration that reports a resource with no stable identifier.
- Discovery running concurrently on two replicas.
- A resource whose kind the deployment does not model.
- Ten thousand resources appearing at once on first connection.
- A resource in maintenance, which is neither healthy nor a problem.
- Clock skew between the deployment and the source.

## Requirements

### Functional

**Model**

- **FR-001** A resource MUST carry: a deployment-stable identity, a kind, a source
  integration, a provider-native identifier, a display name, a parent reference
  where applicable, a set of typed attributes, labels, and an owning team node.
- **FR-002** Resource kinds MUST be declared, not free text, and the set MUST be
  extensible by an integration without changing the core model.
- **FR-003** A resource's identity MUST be derived from the source and the
  provider-native identifier, so it survives a rename, a restart and a
  re-discovery.
- **FR-004** A resource MUST support more than one source, reconciled to one
  record, with each source's contribution attributable.
- **FR-005** Relationships between resources MUST be expressible beyond
  parentage — depends-on, backs-up, replicates-to, hosted-on — and MUST reuse the
  knowledge graph rather than introducing a second graph.

**Discovery**

- **FR-006** An integration MUST be able to declare a discovery capability that
  enumerates the resources it can see.
- **FR-007** Discovery MUST run on a schedule per integration, with the interval
  configurable, and MUST be triggerable on demand.
- **FR-008** Discovery MUST be incremental where the source supports it and
  MUST tolerate a full re-enumeration where it does not.
- **FR-009** A resource absent from a successful sweep MUST be marked absent with
  a timestamp, never deleted.
- **FR-010** A failed sweep MUST NOT mark anything absent. It MUST mark the
  affected resources stale, with the failure recorded.
- **FR-011** Concurrent discovery across replicas MUST converge to one result;
  the mechanism MUST be the same lease-based claiming the scheduler already uses.

**Health**

- **FR-012** A resource MUST carry a health state from a declared, closed set,
  including at minimum: healthy, degraded, unhealthy, unknown, stale, absent, and
  maintenance.
- **FR-013** Health MUST be derived from named signals with recorded values, and
  the derivation MUST be inspectable — an operator MUST be able to see why a
  resource is degraded.
- **FR-014** Health MUST NOT be a free-text status copied from the provider. A
  provider status MUST map into the closed set through a declared mapping, with
  the raw value retained.
- **FR-015** A parent's health MUST roll up from its children through a declared
  rule, and the rule MUST be visible on the parent.
- **FR-016** Health older than a per-kind freshness interval MUST report as stale.
- **FR-017** A resource MUST be placeable in maintenance for a bounded window,
  and maintenance MUST be distinct from healthy.

**History and query**

- **FR-018** Every health transition MUST be recorded with its timestamp, its
  previous state, and the signal that caused it.
- **FR-019** The estate MUST be queryable by kind, health, source, label, team,
  parent and freshness, and MUST support a summary rollup.
- **FR-020** A resource MUST link to the incidents that referenced it and the
  runs that touched it.
- **FR-021** History MUST be retained under the deployment's existing retention
  policy, not a new one.

### Non-functional

- **NFR-001** A summary over ten thousand resources MUST answer within a declared
  budget.
- **NFR-002** A discovery sweep MUST be bounded in time and in the number of
  provider calls it makes, and MUST respect the integration's rate limits.
- **NFR-003** Discovery MUST hold no credential; it MUST call providers through
  the credential proxy like every other integration call.
- **NFR-004** The estate MUST live in the single datastore, in the same schema
  the rest of the platform uses.
- **NFR-005** A provider attribute that would carry a secret or a personal
  identifier MUST pass through the existing masking rules before storage.

## Success criteria

- **SC-001** Discovery run twice against an unchanged source produces no
  duplicates and no spurious transitions.
- **SC-002** A renamed resource updates rather than duplicating.
- **SC-003** A failed sweep marks nothing absent; a successful one marks the gone
  resource absent and retains its history.
- **SC-004** Two sources describing one thing reconcile to one resource with both
  attributed.
- **SC-005** Every health state on every kind is explainable — a test asserts the
  derivation is retrievable for each.
- **SC-006** A ten-thousand-resource summary answers within budget.
- **SC-007** Two replicas running discovery concurrently converge to one result.
- **SC-008** A resource in maintenance is excluded from problem counts and
  included in the estate.

## Out of scope

- Detecting that something is wrong and acting on it — feature 039.
- Provider-specific discovery implementations — features 044 and 047 add them.
- A configuration management database with change approval over resources.
