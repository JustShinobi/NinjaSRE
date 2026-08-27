# Feature 048 — Homelab Profile and Cluster Guardian

- **Wave:** 11 — Proxmox and the homelab
- **Branch:** `feat/048-homelab-profile-and-guardian`
- **Status:** Draft
- **Depends on:** 039, 040, 042, 044, 045, 046

## Summary

The deployment an individual actually runs, and the standing configuration that
makes it useful without being configured: one host, modest resources, a Proxmox
cluster connected, and a set of detectors and policies that watch a two-node
cluster the way somebody who has run one would.

Everything before this feature is general machinery. This is the assembly: the
profile that sizes it for a single small machine, the shipped detector set with
thresholds that are right for a homelab rather than for a data centre, the
default autonomy posture, and the escalation path that reaches a person who is
not on a rota.

It is also the feature that decides what "guardian" means. Not a system that
fixes everything — that is neither achievable nor desirable on somebody's own
infrastructure — but one that handles the recurring tedium unattended, catches
the things that quietly get worse until they are catastrophic, and knows the
difference between the two.

## User scenarios

### Primary story

An operator with a two-node cluster runs one command on a small machine. They
paste a Proxmox API token. Within a few minutes the estate is populated, roughly
thirty detectors are live with sensible thresholds, and the default posture is
propose-only.

Over the first week they read what it would have done. It caught a ZFS pool
crossing eighty per cent, a container whose backup had been failing for eleven
days, a guest left locked by a cancelled backup, and a certificate expiring in
three weeks. It did not do anything.

They then relax the posture where they agree: locks clear themselves, backups
retry themselves, everything else still asks. Six months later the cluster has
had four problems and they were told about all of them and woken by none.

### Acceptance scenarios

1. **Given** a single host with modest resources, **when** the homelab profile is
   deployed, **then** the whole stack runs within a declared memory and CPU
   footprint and stays within it under normal operation.
2. **Given** the profile, **when** it comes up, **then** it includes everything
   needed to be useful — database, gateway, console, observer, scheduler — and
   nothing that only a multi-team deployment needs.
3. **Given** a connected Proxmox cluster, **when** the guardian is enabled,
   **then** the shipped detector set becomes active, each with a threshold, and
   the operator can see every detector and what it watches.
4. **Given** the shipped detectors, **when** they are first enabled, **then** the
   default autonomy posture is propose-only, and nothing acts until the operator
   changes it.
5. **Given** a week of operation, **when** the operator reviews, **then** they can
   see what would have been done under a more permissive posture, and apply that
   posture with the preview in front of them.
6. **Given** a two-node cluster, **when** the guardian configures itself, **then**
   it detects the two-node topology and enables the detectors specific to it,
   including quorum survival and replication currency.
7. **Given** a problem, **when** the operator must be told, **then** it reaches
   them on a channel a person outside a company actually uses, and the message
   contains what happened, what was done, and what is needed.
8. **Given** a notification, **when** the problem resolves before it is read,
   **then** the resolution is sent too, so the operator is not chasing a
   finished problem.
9. **Given** the deployment running on the cluster it watches, **when** the
   cluster has a problem that affects the deployment, **then** the deployment
   says so plainly rather than appearing healthy or silently stopping.
10. **Given** an upgrade of the deployment, **when** it happens, **then**
    detectors, policies and estate survive it, and any detector whose definition
    changed is reported.
11. **Given** a restart of the host, **when** it comes back, **then** the
    deployment resumes, pending verifications are honoured, and no incident is
    lost.

### Edge cases

- The deployment running as a guest on the cluster it manages.
- A single-node Proxmox installation with no cluster.
- A cluster with three or more nodes — the profile must not assume two.
- A host that reboots during an autonomous action.
- An operator away for two weeks with escalations firing.
- A homelab behind a residential connection with intermittent outbound access.
- A cluster with no backups configured at all.
- Storage that fills while the deployment is writing to it.

## Requirements

### Functional

**The profile**

- **FR-001** A homelab deployment profile MUST exist alongside the existing
  profiles, bringing up the full stack on one host with one command.
- **FR-002** It MUST declare and stay within a memory and CPU footprint suitable
  for a small machine, and MUST state that footprint.
- **FR-003** It MUST include the database, gateway, console, credential proxy,
  scheduler and observer, and MUST exclude components only a multi-team
  deployment needs.
- **FR-004** It MUST support a local model endpoint as a first-class
  configuration, and MUST verify it through feature 043's probe at setup.
- **FR-005** It MUST provide backup and restore of its own state in one command
  each, and the restore MUST be tested.
- **FR-006** Upgrade MUST preserve estate, detectors, policies, incidents and
  history, and MUST report any detector whose shipped definition changed.
- **FR-007** It MUST survive a host restart, resuming the observer, the scheduler
  and any pending verification obligations.

**The shipped detector set**

- **FR-008** A detector set MUST ship with the Proxmox integration, enabled by
  choice rather than by default, each with a documented threshold and rationale.
Every detector below corresponds either to a condition that is **true in the
reference cluster right now** or to a **documented incident** in its
postmortems. See [`../044-proxmox-integration/cluster-baseline.md`](../044-proxmox-integration/cluster-baseline.md)
§9 for what the shipped set would raise against that cluster today.

- **FR-009** Cluster detectors MUST cover, at minimum: quorum lost; **quorum
  margin at zero** — one node loss away from unquorate; **quorum device
  configured but not contributing** — present in membership with zero votes or a
  failed daemon; corosync link degraded or lost; node unreachable; node clock
  skew beyond corosync tolerance; high-availability fencing occurred; a cluster
  node running a divergent version.
- **FR-010** Storage detectors MUST cover: datastore usage above thresholds;
  **thin pool metadata usage separately from data usage**; **per-guest thin
  volume approaching its own ceiling, independent of the datastore's level**;
  **datastore reporting an unknown status** — an unreachable share, distinct from
  a full one; growth trending to full within a declared horizon; SMART predicting
  failure. Where ZFS is present: pool degraded or faulted, capacity above the
  performance-degradation threshold, scrub overdue.
- **FR-011** Guest detectors MUST cover: guest stopped that was expected running;
  guest locked beyond a threshold; guest restart loop; guest memory or CPU
  saturation sustained; guest filesystem full as reported by its agent; a guest
  with no recent successful backup.
- **FR-012** Backup detectors MUST cover: job failed; job did not run when
  scheduled; **guest covered by no *enabled* job**; **a backup job that exists
  but is disabled**; **retention depth below a declared floor**; backup
  verification failed; Proxmox Backup Server datastore near full; garbage
  collection or prune overdue; replication lag beyond a declared recovery-point
  objective; **no replication jobs at all while guests sit on node-local
  storage**.
- **FR-013** Maintenance detectors MUST cover: certificate expiring; package
  updates pending beyond a threshold, with security updates distinguished; a node
  requiring reboot after a kernel update; and **a kernel installed but never
  booted** — an upgrade present on disk whose first real boot has not happened.
  That last one is not a refinement of the reboot-required detector: in the
  reference cluster's P1, `/var/run/reboot-required` was absent, the new kernel
  had been installed for weeks, and its first boot was an unplanned one during a
  power cut. Installed is not tested, and nothing signals the gap.
- **FR-013a** Host-layer detectors MUST cover: **failed `systemd` units on a
  node**; **a configured bridge that is absent or down**; and a unit that has
  been failed continuously beyond a threshold. The reference cluster's only total
  outage was invisible to every cluster-level and guest-level reading and plain
  in both of these, and it currently carries nine failed units on one node
  including the very script its postmortem singled out.
- **FR-013b** A detector MUST cover **the monitoring blind spot**: an
  observability stack hosted entirely within the estate it observes. It fires
  once, on discovery of the condition, and is cleared by acknowledgement rather
  than by recovery — it is a structural finding, not a transient one.
- **FR-014** Two-node-specific detectors MUST activate only when a two-node
  topology is detected, and MUST cover quorum survival configuration — that the
  cluster would lose quorum on a single node loss and how that is or is not
  mitigated.
- **FR-015** Every shipped detector MUST state its threshold, why that threshold,
  and what to do about it — visible in the console, not only in a document.
- **FR-016** Thresholds MUST be overridable per deployment and per resource
  without editing the shipped set.

**Default posture**

- **FR-017** The default autonomy posture MUST be propose-only.
- **FR-018** A recommended posture MUST be offered as a single named preset that
  the operator can inspect and apply, making low-risk reversible actions
  autonomous and leaving the rest gated.
- **FR-019** Applying any posture MUST show feature 040's preview against recent
  history first.
- **FR-020** Backup windows and other regular activity MUST be detectable and
  offered as freeze windows, rather than requiring the operator to know they need
  one.

**Notification**

- **FR-021** Notification MUST work on channels an individual uses, and MUST NOT
  require a corporate account. The existing Telegram, Discord and email sinks
  MUST be first-class here.
- **FR-022** A notification MUST state what happened, what was done, what was not
  done and why, and what is needed from the operator.
- **FR-023** A problem resolving before its notification is acknowledged MUST send
  the resolution too.
- **FR-024** Notification MUST be rate-limited and digestible: a storm MUST become
  one message about many things, not many messages.
- **FR-025** Escalation MUST be bounded and MUST have an end, since there is no
  rota to escalate to.

**Self-awareness**

- **FR-026** The deployment MUST detect that it is running on the infrastructure
  it manages, and MUST say so.
- **FR-027** When a problem affects the deployment itself, it MUST report that
  plainly rather than appearing healthy.
- **FR-028** A heartbeat MUST be emitted to an external channel, so an operator
  learns that the guardian stopped rather than concluding all is well. **This is
  not optional and has no configuration that disables it while the guardian is
  enabled.** The reference cluster's P1 is precisely the case it covers: both
  nodes lost networking, the entire observability stack was hosted on one of
  them, and not a single alert fired — the incident was discovered by a human
  noticing that nothing responded, and diagnosed with a keyboard plugged into the
  machines. That cluster's own remediation plan lists an external dead-man's
  switch as its top open action.
- **FR-029** The deployment MUST warn, at setup and continuously, when it is
  running on the estate it manages *and* no external heartbeat destination is
  configured. That combination is the one in which the system cannot report its
  own death.
- **FR-030** Where the operator runs a declarative control plane over the same
  infrastructure, the guardian MUST be able to read its inventory as a source of
  declared intent, and MUST NOT write to anything that control plane owns. A
  remediation whose correct form is a change to that repository MUST be proposed
  as such rather than applied to the live host.

### Non-functional

- **NFR-001** Idle resource use MUST stay within the declared footprint over a
  long-running soak.
- **NFR-002** Detection MUST NOT add a load to the cluster that is itself
  noticeable; the total call rate MUST be declared and measured.
- **NFR-003** The profile MUST work with no inbound connectivity from the
  internet.
- **NFR-004** The profile MUST NOT assume two nodes; two-node behaviour is
  detected, not presumed.
- **NFR-005** Every shipped threshold MUST have a stated rationale; a threshold
  with no rationale MUST fail a test.

## Success criteria

- **SC-001** The profile brings up on one modest host in one command and stays
  within its declared footprint over a soak.
- **SC-002** Every shipped detector fires correctly on a fixture representing its
  condition, and does not fire on a fixture representing health.
- **SC-003** Every shipped detector has a threshold, a rationale and a remedy,
  asserted over the whole set.
- **SC-004** The default posture is propose-only, asserted on a fresh deployment.
- **SC-005** The recommended preset is inspectable and previewable before it
  applies.
- **SC-006** Two-node detectors activate on a two-node topology and not on a
  three-node one.
- **SC-007** A single-node installation runs without cluster detectors firing
  spuriously.
- **SC-008** A notification storm becomes one digest.
- **SC-009** A resolution before acknowledgement is sent.
- **SC-010** Host restart resumes the observer, the scheduler and pending
  verifications, losing no incident.
- **SC-011** Upgrade preserves estate, detectors, policies, incidents and history,
  and reports changed detector definitions.
- **SC-012** The deployment detects that it runs on the cluster it manages and
  reports a problem affecting itself.
- **SC-013** Backup and restore of the deployment's own state round-trips.

## Out of scope

- Managing anything other than Proxmox in the shipped set.
- High availability of the deployment itself.
- A hosted or multi-tenant offering.
