# Plan — 043 Proxmox VE Integration

## Technical context

| Concern | Choice |
|---|---|
| Location | `integrations/proxmox/` and `integrations/proxmox_backup_server/`, following the existing integration layout exactly |
| Transport | The existing `ProxyTransport`, so the client holds no credential — the same reason the Kubernetes client was written by hand rather than using the official one |
| API | The Proxmox REST API over HTTPS, JSON responses |
| Auth | API token header by default; ticket and CSRF as a secondary path with refresh |
| Fixtures | Recorded responses per endpoint, from a two-node cluster in several states |
| Discovery | Feature 038's protocol |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| III — Read-only by default | This feature is reads only. | Every capability declares a read side-effect level, asserted structurally by SC-008. Writes are feature 046 and land behind feature 040's policy engine. |
| IV — Secrets never reach the agent | Proxmox tokens are long-lived and powerful. | The credential lives in the vault; the proxy injects it; SC-009 asserts structurally that no Proxmox code path holds one. This is the same reasoning that kept the Kubernetes client hand-written. |
| VIII — Layered architecture | A tier-2 integration. | It depends on `integrations/_base/` and `config/` only, and is reached from above through the capability registry. |
| IX — Capabilities are declared | New capabilities in a new domain. | Schema, rate limits, required privileges and side-effect level are declared in the integration's schema module like every other. |
| X — Operator owns their data | Guest configuration is personal infrastructure detail. | NFR-003 masks secrets before storage; nothing leaves the deployment. |

## Architecture decisions

**A hand-written client, for the same reason as Kubernetes.** The obvious move is
a Proxmox client library. The existing Kubernetes client's docstring records why
that was refused there: a library that loads its own credentials is a library
that holds a credential, and that behaviour is usually not configurable away.
Proxmox's API surface that an investigation needs is a bounded set of REST paths,
and writing them against the proxy transport is both smaller and compliant.

**Containers and virtual machines are distinct kinds.** Proxmox itself treats
them separately — different endpoints, different configuration, different
failure modes, different remediation. Flattening them into "guest" would make
every capability re-branch internally and would make the estate unable to express
"restart every container on this node".

**Multiple endpoints, with failover.** A two-node cluster configured with one
node's address becomes unreachable exactly when it matters most. Accepting a list
and failing over is a few lines here and the difference between a usable and a
useless integration during a node failure.

**Quorum state is a fact, not an error.** A cluster without quorum still answers
many reads. Treating the condition as a connection failure would hide the single
most important thing about a two-node cluster. It is read, recorded on the
cluster resource, and available to detectors.

**Privilege sufficiency is reported for read and for write separately.** A
read-only token is a legitimate, and for many operators preferable,
configuration. Verification that failed because write privileges were absent
would push operators towards over-privileged tokens; reporting the two separately
makes the safe choice the easy one.

**Certificate verification stays on.** Homelab Proxmox is almost always
self-signed, and the tempting default is to disable verification. Supplying the
certificate or pinning the fingerprint is barely harder and does not train the
operator to accept any certificate on their management plane.

## Phases

1. **Schema and auth.** Integration schema, capability declarations, required
   privileges, rate limits; token and ticket authentication through the proxy;
   certificate handling with pinning; multi-endpoint failover.
2. **Cluster reads.** Status and quorum, resources, configuration including
   corosync, log, HA state, cluster backup jobs.
3. **Node reads.** Status, storage, disks with SMART and ZFS, tasks, replication,
   certificates, updates, network, time sync.
4. **Guest reads.** Virtual machine and container status, configuration, usage,
   locks, snapshots, HA membership, task history, guest agent with the
   unavailable-agent distinction.
5. **Backup reads.** Task outcomes, datastore contents, per-guest last successful
   backup; Proxmox Backup Server as a second endpoint with its own credential.
6. **Tasks.** Identifier retention, bounded polling, log retrieval.
7. **Discovery.** Every declared kind, stable identity across rename and
   migration, reused-VMID handling, parentage and relationships, health mapping
   with raw retention.
8. **Verification and fixtures.** Privilege reporting for read and write,
   recorded responses covering healthy, degraded, no-quorum and node-down states.

## Risks

- **API surface drift across Proxmox versions.** Mitigated by NFR-005's single
  statement of tested versions and by fixtures captured per version, so an
  upgrade breaks a test rather than a deployment.
- **Fifty guests times several reads is a lot of calls.** Mitigated by preferring
  the cluster-wide resource list for discovery and reserving per-guest reads for
  investigation, and by NFR-001's declared call budget.
- **A reused VMID silently resurrects a deleted guest's history.** Mitigated by
  including a creation-time discriminator in the identity, tested explicitly.
