# Feature 044 — Proxmox VE Integration

- **Wave:** 11 — Proxmox and the homelab
- **Branch:** `feat/044-proxmox-integration`
- **Status:** Draft
- **Depends on:** 007, 024, 038

## Summary

A first-class integration for Proxmox Virtual Environment: authentication through
the credential proxy, a read client covering the cluster, its nodes, its guests,
its storage, its tasks, its high-availability state, its replication and its
backups — and a discovery capability that populates the estate from all of it.

Neither prior-art system covers Proxmox at all. Between them they reach
Kubernetes, ECS, EKS, EC2, Lambda, RDS, S3, Azure, GCP and a great deal more;
a search of both trees for the hypervisor a self-hoster actually runs returns
nothing. This is the wave's largest genuinely new surface and the one with the
least to copy.

This feature is the foundation only: authentication, transport, reads, schema,
verification, discovery. What questions to ask is feature 045. What to change is
feature 046.

**The reference cluster is measured, not imagined.**
[`cluster-baseline.md`](cluster-baseline.md) is a live survey of the two-node
cluster this wave targets, taken 2026-08-07, alongside its operator's
thirteen postmortems and validated inventory. Three findings from it change this
feature's requirements directly: **there is no ZFS on either node** — storage is
LVM-thin, with two thin pools and three guest volumes above 93% of their own
ceiling; the failure that mattered most was **invisible at the API level and
obvious at the `systemd` unit level**; and the operator already maintains a
schema-validated inventory that declares intent the API cannot report.

## User scenarios

### Primary story

An operator creates an API token in the Proxmox web interface, pastes it into the
console, and presses verify. The verification says which cluster it reached, how
many nodes are in it, whether the token's privileges are sufficient for reading
everything the integration needs, and — separately — whether they extend to the
write operations feature 046 would need, so a read-only token is a supported and
clearly-labelled choice.

A minute later the estate holds their two nodes, eleven virtual machines, six
containers, four datastores, the backup jobs, and the replication jobs between
the nodes — each with health, each linked to its parent, each refreshing.

### Acceptance scenarios

1. **Given** an API token, **when** the integration is verified, **then** it
   reports the cluster name, node count, version, the privileges the token holds,
   and whether they suffice for read and for write.
2. **Given** a token with insufficient privileges, **when** verification runs,
   **then** it names the specific missing privilege and the path it was needed
   for, not a generic authorisation failure.
3. **Given** a self-signed certificate, **when** the integration connects,
   **then** it works when the operator has supplied the certificate or explicitly
   accepted its fingerprint, and refuses otherwise. Verification MUST NOT be
   disabled by default.
4. **Given** a configured integration, **when** discovery runs, **then** nodes,
   virtual machines, containers, datastores, pools, backup jobs, replication jobs
   and the cluster itself appear in the estate with correct parentage.
5. **Given** a guest that has migrated between nodes, **when** discovery runs
   again, **then** the same resource is updated with a new parent, not
   duplicated.
6. **Given** a node that is down, **when** discovery runs, **then** the cluster
   and the other node are still enumerated, the down node is reported as such,
   and its guests are stale rather than absent.
7. **Given** an asynchronous operation, **when** it is started, **then** its task
   identifier is retained, its status is pollable, and its log is retrievable.
8. **Given** the API rate-limiting or refusing, **when** it does, **then** the
   client retries within its policy and surfaces the provider's own message.
9. **Given** a cluster with no quorum, **when** reads are attempted, **then** the
   reads that still work do, the ones that do not report why, and the lack of
   quorum is itself a fact the estate records.
10. **Given** any call, **when** it is made, **then** it carries no credential
    from the agent's process; the credential proxy supplies it.

### Edge cases

- A single-node installation with no cluster.
- A node in the cluster running a different Proxmox version.
- A guest with no name set.
- A VMID reused after a guest was destroyed.
- A datastore visible from one node and not another.
- A guest on shared storage appearing under two nodes.
- An API token whose privilege separation flag changes its effective rights.
- A cluster reached through only one node's address when that node is down.
- A very long-running task whose log grows unbounded.
- Proxmox Backup Server as a separate host with its own API and credential.

## Requirements

### Functional

**Authentication and transport**

- **FR-001** The integration MUST authenticate with an API token, and MUST support
  both privilege-separated and non-separated tokens.
- **FR-002** Ticket-and-CSRF authentication MUST also be supported for
  deployments that cannot issue tokens, with the ticket refreshed before expiry.
- **FR-003** The credential MUST live in the vault and MUST be supplied by the
  credential proxy. No Proxmox code may read a credential.
- **FR-004** Certificate verification MUST be on by default. A self-signed
  certificate MUST be supported by supplying the certificate or by explicitly
  pinning its fingerprint. Disabling verification MUST require an explicit,
  audited setting.
- **FR-005** The client MUST accept more than one endpoint address for a cluster
  and MUST fail over between them, so a cluster stays reachable when the node
  named in the configuration is the one that is down.
- **FR-006** Retry, backoff and pagination MUST use the existing integration base
  rather than a Proxmox-specific implementation.

**Reads — cluster**

- **FR-007** The client MUST read cluster status, including quorum state,
  expected and current votes, and per-node membership.
- **FR-008** The client MUST read the cluster resource list, the cluster
  configuration including corosync node and totem settings, and the cluster log.
- **FR-009** The client MUST read high-availability state: resources, groups,
  manager status, and fencing state.
- **FR-010** The client MUST read cluster-wide backup job definitions and their
  most recent outcomes.

**Reads — nodes**

- **FR-011** The client MUST read per-node status: uptime, load, CPU, memory,
  swap, root filesystem usage, kernel and Proxmox version.
- **FR-012** The client MUST read a node's storage list and per-datastore status
  and content.
- **FR-013** The client MUST read a node's physical disks, including SMART state.
- **FR-013a** The client MUST read LVM-thin pool state — data percentage and
  **metadata percentage separately** — and per-volume fill for every thin volume.
  LVM-thin is the primary storage technology in the reference cluster; ZFS is
  absent from it entirely.
- **FR-013b** The client MUST read ZFS pool state where ZFS is present, and MUST
  degrade cleanly where it is not. A node without ZFS is the ordinary case, not a
  read failure.
- **FR-013c** The deployment MUST be able to observe a node's failed `systemd`
  units, the presence and state of its configured bridges, and LVM thin-pool
  **metadata** usage. The cascade that caused the reference cluster's only total
  outage was visible in neither the cluster API nor the guest API, and was plain
  in these.
- **FR-013d** None of those three is exposed by the Proxmox REST API, and this
  client MUST NOT gain shell access to reach them. Article IV forbids the agent
  holding an SSH identity, and a hypervisor integration that could run arbitrary
  commands on both nodes is the single largest authority this system would ever
  hold. They MUST instead arrive as **metrics published by the node itself** —
  a node exporter and a textfile collector — read through feature 047's
  observability bridge.
- **FR-013e** A deployment with no such exporter MUST report these readings as
  **unavailable**, naming what would publish them, and MUST NOT report them as
  healthy. The distinction between "nothing is failing" and "nothing is looking"
  is the one this whole wave exists to preserve.
- **FR-014** The client MUST read a node's task history and a specific task's
  status and log.
- **FR-015** The client MUST read a node's replication jobs and their state,
  including last run, duration and failure.
- **FR-016** The client MUST read a node's certificate expiry and its pending
  package updates.
- **FR-017** The client MUST read a node's network interface configuration and
  its time synchronisation state.

**Reads — guests**

- **FR-018** The client MUST read, for both virtual machines and containers:
  current status, configuration, resource usage, lock state, high-availability
  membership, snapshots, and pending configuration changes.
- **FR-019** The client MUST read a guest's recent task history.
- **FR-020** Where a guest agent is available, the client MUST be able to read
  the guest's own view — filesystem usage, network, and whether the agent
  responds — and MUST clearly distinguish an unavailable agent from an unhealthy
  guest.
- **FR-021** Containers and virtual machines MUST be distinct resource kinds with
  a shared read interface where the concepts coincide, and MUST NOT be flattened
  into one.

**Reads — backups**

- **FR-022** The client MUST read backup task outcomes, retained backup contents
  per datastore, and each guest's most recent successful backup.
- **FR-023** Proxmox Backup Server MUST be supported as a separate endpoint with
  its own credential, reading datastore status, snapshot lists, verification
  outcomes, garbage-collection state and prune results.

**Tasks**

- **FR-024** Every asynchronous operation MUST return a task identifier that is
  retained, pollable and whose log is retrievable.
- **FR-025** Task polling MUST be bounded in time and in calls, and MUST report a
  task still running rather than waiting indefinitely.

**Discovery and schema**

- **FR-026** The integration MUST implement feature 038's discovery capability,
  producing: cluster, node, virtual machine, container, datastore, storage pool,
  backup job, replication job, and physical disk.
- **FR-027** Resource identity MUST be stable across rename and migration, and
  MUST distinguish a reused VMID from the guest that previously held it.
- **FR-028** Parentage and relationships MUST be recorded: guests on nodes, nodes
  in the cluster, datastores available to nodes, replication between nodes,
  backup jobs covering guests.
- **FR-029** Provider states MUST map into the estate's closed health set through
  a declared mapping, with the raw value retained.
- **FR-030** The integration MUST declare its schema, its capabilities, its rate
  limits and its required privileges in the same form every other integration
  does.
- **FR-031** The integration MUST be able to take a declarative inventory — a
  schema-validated description of nodes, guests and services the operator already
  maintains — as a **second source** for the same resources, reconciled to one
  record under feature 038's multi-source rule.
- **FR-032** Where the inventory and the live API disagree, both values MUST be
  retained and the divergence MUST be expressible as a signal. An inventory says
  what *should* be true — role, expected state, ownership — which the API cannot
  report and which is exactly what a detector needs to notice drift.
- **FR-033** The integration MUST NOT write to any path a declarative control
  plane owns. Where the operator runs one, its components are read-only to this
  system.

### Non-functional

- **NFR-001** A discovery sweep over a two-node cluster with fifty guests MUST
  complete within a declared budget and a declared call count.
- **NFR-002** No read may have a side effect. Every read capability MUST be
  declared read-only and asserted.
- **NFR-003** Guest configuration may contain secrets — cloud-init passwords, SSH
  keys. These MUST pass through the existing masking rules before storage.
- **NFR-004** The client MUST be testable in full against recorded responses,
  with no live cluster.
- **NFR-005** The integration MUST work against the current Proxmox major version
  and MUST state, in one place, which versions it is tested against.

## Success criteria

- **SC-001** Verification against a real cluster reports name, node count,
  version and privilege sufficiency for read and for write separately.
- **SC-002** An insufficient privilege is reported by name with the path it was
  needed for.
- **SC-003** Certificate verification is on by default; a pinned fingerprint
  works; disabling requires an explicit audited setting.
- **SC-004** Discovery of a two-node cluster produces every declared resource
  kind with correct parentage, within budget.
- **SC-005** A migrated guest updates rather than duplicating; a reused VMID
  produces a distinct resource.
- **SC-006** With one node down, the cluster and surviving node enumerate, and the
  down node's guests are stale rather than absent.
- **SC-007** Endpoint failover reaches the cluster through a surviving node.
- **SC-008** Every read capability is declared read-only, asserted structurally.
- **SC-009** No Proxmox code path holds a credential, asserted structurally.
- **SC-010** The whole client is exercised against recorded responses with no live
  cluster.
- **SC-011** A cloud-init secret in a guest configuration is masked before
  storage.

## Out of scope

- Investigation tools and skills — feature 045.
- Any write operation — feature 046.
- Ceph, which a two-node cluster cannot sensibly run; the client may read its
  status where present but no capability depends on it.
- Managing Proxmox configuration files directly over SSH.
