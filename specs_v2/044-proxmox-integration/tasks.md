# Tasks — 043 Proxmox VE Integration

## Phase 1 — Schema and authentication

- **T-001** Integration schema: base URL shape, capability declarations, required
  privileges per capability, rate limits, tested Proxmox versions in one place.
- **T-002** API token authentication through `ProxyTransport`; structural test
  that no Proxmox code path holds a credential.
- **T-003** Ticket and CSRF authentication with refresh before expiry.
- **T-004** Failing test: certificate verification is on by default; a supplied
  certificate and a pinned fingerprint both work; disabling requires an explicit
  audited setting.
- **T-005** Multi-endpoint configuration with failover; failing test that the
  cluster is reachable through a surviving node.
- **T-006** Retry, backoff and pagination through `integrations/_base/`; assert no
  Proxmox-specific reimplementation.

## Phase 2 — Cluster reads

- **T-007** Cluster status with quorum state, expected and current votes,
  per-node membership.
- **T-008** Cluster resource list; cluster configuration including corosync nodes
  and totem settings; cluster log.
- **T-009** HA resources, groups, manager status, fencing state.
- **T-010** Cluster backup job definitions and latest outcomes.
- **T-011** Failing test: with no quorum, reads that work do, reads that do not
  report why, and the quorum state is recorded as a fact.

## Phase 3 — Node reads

- **T-012** Node status: uptime, load, CPU, memory, swap, root filesystem,
  kernel and Proxmox version.
- **T-013** Storage list, per-datastore status and content.
- **T-014** Physical disks with SMART state; ZFS pool state where present.
- **T-015** Node task history; specific task status and log.
- **T-016** Replication jobs with last run, duration and failure.
- **T-017** Certificate expiry; pending package updates.
- **T-018** Network interface configuration; time synchronisation state.

## Phase 4 — Guest reads

- **T-019** Virtual machine and container as distinct kinds with a shared read
  interface where concepts coincide; assert they are not flattened.
- **T-020** Status, configuration, usage, lock state, HA membership, snapshots,
  pending configuration changes — for both kinds.
- **T-021** Guest task history.
- **T-022** Guest agent reads where available; failing test that an unavailable
  agent is distinguishable from an unhealthy guest.
- **T-023** A guest with no name set; a guest on shared storage visible from two
  nodes.

## Phase 5 — Backup reads

- **T-024** Backup task outcomes; retained contents per datastore; per-guest most
  recent successful backup.
- **T-025** Proxmox Backup Server as a separate integration with its own
  credential: datastore status, snapshots, verification outcomes,
  garbage-collection state, prune results.

## Phase 6 — Tasks

- **T-026** Task identifier retention; status polling; log retrieval.
- **T-027** Failing test: polling is bounded in time and calls, and reports a
  task still running rather than waiting indefinitely.
- **T-028** A long-running task whose log grows unbounded is read boundedly.

## Phase 7 — Discovery

- **T-029** Implement feature 038's discovery protocol for every declared kind.
- **T-030** Failing test: identity stable across rename and across migration.
- **T-031** Failing test: a reused VMID produces a distinct resource, not a
  resurrection.
- **T-032** Parentage and relationships: guests on nodes, nodes in cluster,
  datastores to nodes, replication between nodes, backup jobs covering guests.
- **T-033** Health mapping from provider states into the closed set, raw value
  retained; an unmapped state becomes `unknown`.
- **T-034** Failing test: with one node down, the cluster and surviving node
  enumerate and the down node's guests are stale, not absent.
- **T-035** Benchmark: two-node cluster with fifty guests within the declared
  time and call budgets.

## Phase 8 — Verification, masking and fixtures

- **T-036** Verification reporting cluster name, node count, version, and
  privilege sufficiency for read and write separately.
- **T-037** Failing test: an insufficient privilege is named, with the path it
  was needed for.
- **T-038** Failing test: a cloud-init secret in a guest configuration is masked
  before storage.
- **T-039** Structural test: every read capability declares a read side-effect
  level.
- **T-040** Recorded fixtures covering healthy, degraded, no-quorum, node-down
  and single-node-no-cluster states; assert the whole client is exercised with no
  live cluster.

## Definition of done

- SC-001 through SC-011 each proven by a named test.
- Discovery populates the estate for a real two-node cluster.
- `make verify` green.
