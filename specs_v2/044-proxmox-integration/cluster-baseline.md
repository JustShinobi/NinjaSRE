# Field baseline — cluster HAL9000

Live technical survey taken 2026-08-07 against the two-node Proxmox cluster this
wave is being built for. Everything below is measured, not assumed. It is the
reference environment for features 044–049 and the source of the example data in
the console mockups.

Also drawn on: the operator's infrastructure repository at `/root/infra-cluster`
on `pve02` — 13 postmortems, 55 runbooks, 3 ADRs, a validated YAML inventory, and
a GitOps control plane with `validate`/`plan`/`apply`/`drift`.

---

## 1. Topology

| | `pve01` | `pve02` |
|---|---|---|
| Address | `192.168.68.149` | `192.168.68.159` |
| Role (inventory) | primary | secondary |
| Proxmox | 9.2.6 | 9.2.6 |
| Kernel running | `7.0.14-8-pve` | `7.0.14-8-pve` |
| CPU / memory | 63% / 58% | 9% / 51% |
| Root filesystem | 31 GiB of 96 (33%) | 77 GiB of 96 (**80%**) |
| Physical NICs | 1 (`enp1s0`) | 2 (`enp1s0`, `eno1`) |
| Guests | ~55 | ~30 |

Cluster `HAL9000`, corosync `knet`, one link, `config_version: 2`, secure auth
on. 84 guests total: **82 containers, 2 virtual machines**. Load is markedly
asymmetric — `pve01` carries almost everything that runs, `pve02` carries the
warm pool and the heavy stateful guests.

---

## 2. Quorum — the finding that matters most

```
Expected votes: 2   Total votes: 2   Quorum: 2   Quorate: Yes
Nodeid 0x01  1 vote  Qdevice: NA,NV,NMW   192.168.68.149
Nodeid 0x02  1 vote  Qdevice: NR          192.168.68.159 (local)
Nodeid 0x00  0 votes Qdevice
```

`corosync.conf` has **no `device {}` block**, **no `two_node: 1`**, and **no
`wait_for_all`**. A quorum device appears in the membership view but contributes
zero votes, and on `pve01`:

```
● corosync-qdevice.service   loaded failed failed   Corosync Qdevice daemon
```

**Consequence, stated plainly: quorum margin is zero.** Losing either node drops
the cluster to 1 of 2 required votes. `pmxcfs` goes read-only, `/etc/pve` becomes
unwritable, and no guest can be started, stopped, migrated or reconfigured on the
survivor. The guests already running keep running.

HA is `fencing standby (CRM watchdog standby)`.

This is not hypothetical here. It happened on 2026-08-06 (§6).

---

## 3. Storage

**There is no ZFS on either node.** `zpool list` returns "no pools available" on
both. Storage is **LVM-thin** plus network shares. Any specification that leads
with ZFS is aimed at the wrong technology for this cluster.

### Thin pools — `pve02`

| LV | VG | Size | Data% | Meta% |
|---|---|---|---:|---:|
| `data` | `pve` | 349.9 G | **84.46** | 3.35 |
| `data-pool` | `data-pool` | 931.1 G | 72.38 | **31.98** |

### Thin volumes near their own ceiling — `pve02`

| Volume | Guest | Used |
|---|---|---:|
| `vm-100-disk-0` | CT100 plex | **99.60%** |
| `vm-115-disk-0` | CT115 adguard | **94.96%** |
| `vm-140-disk-0` | CT140 unbound | **93.00%** |
| `vm-161-disk-0` | CT161 orca | 76.88% |
| `vm-142-disk-0` | CT142 mydrive-gateway | 74.21% |

CT115 and CT140 are the two guests with DNS-stall postmortems (2026-07-17,
2026-07-20). A guest at 95% of its own volume while its datastore reports 84% is
precisely the distinction a datastore-level threshold cannot make.

### Datastores

| Datastore | Used | Status |
|---|---:|---|
| `TeraChad` | **96%** (7128 / 7452 G) | available |
| `GigaChad` | **93%** (1741 / 1863 G) | available |
| `local-lvm` @ pve02 | 84% | available |
| `local` @ pve02 | 80% | available |
| `fileserver-backup-smb` | 80% | available |
| `leslie` | 77% | available |
| `externo-local-pve02` | 75% | available |
| `local-lvm` @ pve01 | 56% | available |
| `remote-backup` | 19% | available |
| `externo-nfs-pve01` | — | **unknown** |
| `media-nfs-pve01` | — | **unknown** |

Two datastores report `unknown` — NFS mounts that are down. On `pve01`,
`mnt-9S.mount`, `mnt-TeraChad.mount` and `mnt-pve-MyDrive.mount` are all in a
failed state.

---

## 4. Backups and replication

```
vzdump backup-7d831311  "pve01 baseline"   all=1   enabled 0   08:00
vzdump backup-33b5e58a  "pve02 baseline"   10 vmids enabled 1  07:00
vzdump backup-1f376301  "PostgreSQL"        node pve02 enabled 0  02:30,22:30
```

- The **`pve01` job is disabled**. Roughly 55 guests — including the entire
  observability stack, Traefik, Authelia, Infisical and WireGuard — are covered
  by **no enabled backup job**.
- The `pve02` job covers 10 VMIDs of about 30.
- The PostgreSQL job (CT129, a 900 GiB volume) is disabled, commented
  "sem politica automatica".
- Retention throughout is `keep-last=2`.

```
$ pvesr status
JobID  Enabled  Target  LastSync  NextSync  Duration  FailCount  State
(empty)
```

**No replication jobs exist.** With guests on node-local LVM-thin and no
replication, a node loss means its guests are unavailable until restored from a
backup — and for most of `pve01`, there is no current backup to restore from.

---

## 5. Pending updates

24 packages pending on both nodes, identical sets, including
`proxmox-kernel-7.0 7.0.14-9` — an upgrade from the `7.0.14-8` currently running.
Security updates among them: `jq`, `libjq1`, `libde265-0`, `libudisks2-0`,
`udisks2`, `linux-libc-dev`. Also `pve-manager 9.2.9`, `qemu-server 9.2.4`,
`pve-container 6.1.13`, `libpve-common-perl 9.2.1`, `frr 10.6.1-1+pve3`.

`/var/run/reboot-required` is absent on both nodes, so the usual signal does not
fire. This is the exact precondition of the 2026-08-06 incident: a kernel
installed and never booted, whose first real boot will be an unplanned one.

## 5b. Failed units

`pve01`: `mnt-9S.mount`, `mnt-pve-MyDrive.mount`, `mnt-TeraChad.mount`,
`corosync-qdevice.service`, `fileserver-vback-route.service`, `glances.service`,
`network-gateway-ha-hardening.service`, `nmbd.service`, `openipmi.service`,
`pve-container@103.service`.

`pve02`: `openipmi.service`.

`network-gateway-ha-hardening.service` is one of the two scripts the 2026-08-06
postmortem singled out for failing silently. It is now failing loudly and nothing
is watching.

---

## 6. What the postmortems teach

Thirteen documented incidents. The five findings that change this wave's specs:

**Detection is the weakest link, not diagnosis.** Detection sources recorded
across the incidents: "relato do usuário", "acesso a `winfsp.dev` falhou", and —
for the P1 — **"nenhum: diagnóstico exigiu acesso físico (HDMI/teclado)"**.

**The observability stack is hosted inside what it monitors.** Prometheus,
Alertmanager, Grafana, blackbox exporter and Loki all run as containers on
`pve01`. On 2026-08-06 both nodes lost networking and **no alert fired at all** —
the monitors went down with the thing they monitor. The postmortem's own action
NETQ-004 is "add a watcher external to the cluster (dead-man's switch)"; still
pending.

**Everything depends on `vmbr0` and nothing watches it.** A kernel upgrade
renamed `eth0` to `enp1s0`/`eno1`; `/etc/network/interfaces` still said `eth0`;
`ifupdown2` could not build `vmbr0`; corosync, `pmxcfs`, keepalived, the boot
hardening scripts and the observability stack all failed together. Recovery
needed physical access to both machines.

**Silent degradation is the recurring failure mode.** `disable-offloads.sh` and
`apply-gateway-ha-hardening.sh` both logged a warning and exited zero. keepalived
warned and kept running degraded. `systemd` therefore saw nothing wrong.

**It is a pattern, not an event.** 2026-04-05, 2026-08-05 and 2026-08-06 share a
root cause: network state is not reconverged declaratively at boot. Three
incidents in four months. Treating each as isolated produced the fourth.

---

## 7. Existing platform — what NinjaSRE must fit into, not replace

**Observability already exists and is substantial.** CT137 prometheus, CT136
alertmanager, CT133 grafana, CT134 blackbox-exporter, **CT135
prometheus-pve-exporter**, CT112 loki, CT111 signoz, CT121 openobserve, CT138
gatus. Prometheus already carries `cluster-alerts.yml`,
`cluster-recording-rules.yml`, `resilience-alerts.yml`, `automation-alerts.yml`.

**There is a GitOps control plane.** `/root/infra-cluster` exposes an `infra` CLI
with `validate`, `plan`, `apply` and `drift` over components, with state in
`.infra-state/`. Guest and node configuration is owned by that repository.

**There is a validated inventory.** `inventory/cluster/{nodes,cts,vms,services,zones,proxmox-backup-jobs}.yaml`,
each with a JSON schema. This is a ready-made second source for the estate, and
the place where "expected running" is declared.

**A predecessor already runs.** CT159 `opensre`, currently stopped, took critical
Alertmanager alerts on `:9001`, used an LLM endpoint at
`https://omniroute.lan.kyo.ninja/v1`, and notified through Pushover. Its runbook
is `docs/runbooks/opensre-investigation.md`.

---

## 8. What this baseline changes in the specs

| # | Change | Why |
|---|---|---|
| 043 | LVM-thin is the primary storage technology; ZFS is optional and secondary. Read `lvs` data *and* metadata percentages, and per-volume fill. | No ZFS exists on either node; two thin pools and three near-full thin volumes do. |
| 043 | Read node `systemd` failed units and bridge presence. | The P1 cascade was invisible at the API level and obvious at the unit level. |
| 043 | Accept the repository inventory as a second estate source, reconciled. | It already declares intent — role, expected state — that the API cannot report. |
| 044 | A quorum tool must report *configured but non-contributing* quorum devices, not just vote counts. | A QDevice present in membership with zero votes and a dead daemon reads as "configured" to anything counting devices. |
| 044 | Thin-pool metadata and per-guest volume fill are distinct questions from datastore usage. | `local-lvm` at 84% while CT100 is at 99.6% of its own volume. |
| 045 | No action may touch `/etc/network/interfaces`, bridges, or the GitOps control plane's components. | Network state is owned by a repository with its own apply path; a second writer is how drift becomes an outage. |
| 046 | Ship mappings for `prometheus-pve-exporter` and node-exporter specifically, and honour existing alert rules rather than duplicating them. | Both are already deployed and already have rules. |
| 047 | Add detectors: quorum margin zero · quorum device configured but not contributing · kernel installed but never booted · backup job disabled · guest covered by no *enabled* job · zero replication jobs with node-local storage · failed systemd units · bridge absent · datastore status unknown · guest volume near full. | Each corresponds to a condition true in this cluster right now, or to a documented incident. |
| 047 | The external heartbeat is not optional. | The P1's total detection failure is exactly the case it covers, and NETQ-004 is still open. |
| 048 | Scenarios must be drawn from the postmortems, not invented. | Thirteen real incidents with known causes and known correct responses are better evaluation data than anything synthesised. |

---

## 9. Findings the system would raise today

If the guardian were running against this cluster now, in propose-only mode:

| Severity | Finding |
|---|---|
| critical | Quorum margin is zero — `corosync-qdevice.service` failed on `pve01`, no `two_node`, no `wait_for_all`. Either node's loss makes `/etc/pve` read-only. |
| critical | ~55 guests on `pve01` are covered by no enabled backup job; the job exists and is disabled. |
| critical | `TeraChad` at 96%. |
| high | No replication jobs with node-local guest storage — a node loss is unrecoverable within the cluster. |
| high | `GigaChad` at 93%; `local-lvm`@pve02 at 84%; `/` on `pve02` at 80%. |
| high | CT100 plex thin volume at 99.60%; CT115 at 94.96%; CT140 at 93.00%. |
| high | Kernel `7.0.14-9` installed on both nodes and never booted. |
| high | Observability stack hosted entirely on `pve01`, monitoring itself. No external watcher. |
| medium | Nine failed `systemd` units on `pve01`, including two NFS mounts and the gateway hardening script named in the P1. |
| medium | Two datastores reporting `unknown`. |
| medium | 6 security updates pending on both nodes. |
| medium | Backup retention `keep-last=2` across all jobs. |
