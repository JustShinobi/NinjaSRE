# Deviations — 045 Proxmox Investigation Capabilities

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 1. T-026 — `proxmox_pbs_state` was not created; the existing PBS tool was extended

**Planned.** "`proxmox_pbs_state`: datastore usage, verification, garbage
collection, prune results."

**Done.** `integrations/proxmox_backup_server/tools/datastore_health.py` — which
feature 044 already shipped as `proxmox_backup_server_datastore_health` — gained
`prune_rules` and `proven_snapshot_count`, and its summary now says *unproven*
rather than only counting. No second tool was added.

**Why.** The existing tool already returned three of the four things T-026 names
(usage, verification, garbage collection) from the same four endpoints a new one
would have read. A second capability over the same store would have been two
entries in the catalogue answering the same question, two descriptions for the
model to choose between, and — because `resolve_for` scores both — a live chance
of the model picking the one that omits prune. The catalogue-wide contract in
`tests/contract/integrations/test_catalogue_wide_guarantees.py` already treats a
second declaration of the same subject as a defect for skills; the same argument
holds for tools and nothing enforces it, which is exactly when it gets done
wrong.

What was missing is now present:

| T-026 asks for | Where it is |
|---|---|
| datastore usage | `total_bytes`, `used_bytes`, `estimated_full_date` (already there) |
| verification | `unverified_snapshots`, **`proven_snapshot_count`** (new) |
| garbage collection | `garbage_collection_status`, `garbage_collection_last_run` (already there) |
| prune results | **`prune_rules`** (new) — the retention the *store* applies, which is not the retention the hypervisor's job asked for |

---

## 2. Three readings the Proxmox API does not publish, reported as undetermined

FR-004, FR-009 and FR-015 each ask for a number the vendor does not expose. In
all three the tool makes the reading it can, names the one it cannot, and names
what *would* publish it. None of them is silently omitted and none is invented.

| Requirement | What is missing | What the tool does instead |
|---|---|---|
| **FR-004** — "retransmits and knet latency" | Per-link latency and corosync's own retransmit counters live in `corosync-cfgtool` output on each node, and this integration is deliberately forbidden a shell. | `proxmox_corosync_links` counts retransmit *log entries* from `/cluster/log` — which is real and is the reading that distinguishes a degrading link — and returns an `undetermined` entry naming `corosync-cfgtool -n` for the counters and the latency. |
| **FR-009** — "which pool or datastore each disk backs" | Proxmox reports a disk as used for `LVM` and never says which volume group. Only ZFS publishes its device list. | `proxmox_disk_health` completes the map for ZFS and returns an `undetermined` entry per unmapped disk naming `pvs` and `lsblk`. |
| **FR-015** — "CPU steal" | Not in the API at any endpoint. It is visible inside the guest only. | `proxmox_guest_pressure` returns an `undetermined` entry saying so, with the reason that an investigation given no steal reading attributes a stolen CPU to the guest's own load every time. |

A fourth, smaller one: **a snapshot's reclaimable size is not published**.
`proxmox_reclaimable_space` carries `reclaims_bytes_known: false` on snapshot
entries rather than reporting zero, because a zero would rank the most dangerous
item last and would read as "this frees nothing".

**Why this shape rather than a gap in the spec.** NFR-003 already requires every
tool to state what it could not determine, and the alternative — dropping the
requirement — would have produced a tool whose silence is indistinguishable from
a healthy reading. That is the failure this whole wave exists to avoid.

---

## 3. Only one Proxmox skill may declare `requires: integrations: [proxmox]`

**Planned.** T-029 to T-033: five skills plus, from FR-025a, a sixth for the node
host layer. All six are Proxmox methodology, so all six would naturally declare
the integration they need.

**Done.** Six skills exist. `capabilities/skills/proxmox/SKILL.md` declares
`requires: integrations: [proxmox]`. The other five declare no `requires` at all
and reach their exclusion through `directs_tools`.

**Why.** `tests/contract/integrations/test_catalogue_wide_guarantees.py::
test_every_integration_contributes_exactly_one_methodology_skill` is a committed
contract asserting exactly one skill per integration whose
`requires.integrations == (name,)`. Its reason is sound and is written down
there: two skills for one vendor are two standing index entries competing with
each other on every turn. Six would have been six.

The behaviour a reader would expect is preserved without weakening it.
`capabilities/registry/catalogue.py::resolve_for` excludes a skill when **every
tool it directs is excluded**, so the five skills that direct only Proxmox tools
are excluded from a team with no Proxmox exactly as though they had declared the
requirement — and the exclusion carries `proxmox` as the unmet requirement,
because `_requirements_of` reads it from the directed tools. Verified against the
real catalogue rather than reasoned about.

**What is genuinely different.** The one skill that carries the requirement is
the cluster-and-quorum skill, which is the entry point the others are reached
from, and it is the one whose index entry is paid for on every turn. The skill
index cost went from 6,083 to 6,538 tokens across 93 skills, against a 14,000
ceiling.

---

## 4. Estate and episodic memory are routed to in prose, not in `directs_tools`

**Planned.** T-035: "Routing to the estate and episodic memory for prior
occurrences before a cause is proposed."

**Done.** Every one of the six skills names `recall_similar_incidents` and
`query_service_topology` in its body, in a step placed before any cause is
proposed. Neither appears in `directs_tools`.

**Why.** Both are system tools that require no integration, so listing one in
`directs_tools` would make `resolve_for`'s "every directed tool is excluded" test
false for the five skills that rely on it — and all five would then be offered to
every team in the catalogue, Proxmox or not. Naming them in the body routes the
model to them without breaking the exclusion that §3 depends on.
`test_every_methodology_skill_routes_to_the_estate_and_to_episodic_memory`
asserts the routing per skill.

---

## 5. `proxmox_quorum_status` and `proxmox_cluster_health` both exist

T-002 asks for `proxmox_quorum_status`. Feature 044 shipped
`proxmox_cluster_health`, which reads `/cluster/status` and reports the margin.
Both are now in the catalogue and neither was removed.

**Why not merge them.** They read different things and answer different
questions. `proxmox_cluster_health` is **one call** and is what a sweep or a
first look uses. `proxmox_quorum_status` reads three endpoints and returns the
corosync configuration — `two_node`, `wait_for_all`, `last_man_standing` — plus
the explicit consequences of the state it found, which is what the two-node skill
branches on. Deleting the cheap one would have made every "is this cluster
deciding" question cost three calls; deleting the expensive one would have
dropped FR-002 and FR-003 entirely.

Their descriptions and `anti_examples` name each other, which is what selection
uses to tell them apart.

---

## 6. Two real defects found while testing, and fixed

- **`TaskRecord.finished` classified every failed task as still running.**
  Proxmox writes its own prose into `status` for a task that failed — `job
  errors`, `storage 'x' is not online` — and the property only recognised
  `stopped` and `OK`. Every failure therefore read as in-progress. That is not
  cosmetic: it is precisely the field that decides whether a guest's lock is held
  by live work or orphaned by dead work, and the two have opposite correct
  actions. `ended_at` is now decisive on its own, and the docstring says why.
- **`tests/support/proxmox.py`'s corpus had no `/nodes/<node>/disks/lvm`
  recording at all**, so `proxmox_storage_pressure`'s per-guest volume reading —
  the one that motivated the whole tool — was exercised only by a test that
  supplied its own. The recording is now in the corpus and the per-guest volumes
  are read by everything that reads storage.

---

## 7. `MAX_GUESTS_EXAMINED`: a call bound the plan did not name

Two tools need a per-guest read that does not scale: snapshots
(`proxmox_reclaimable_space`) and disk placement (`proxmox_replication_lag`).
Fifty guests is fifty calls, which is a budget an investigation does not have —
the same argument `integrations/proxmox/discovery.py::MAX_SWEEP_CALLS` already
makes for the sweep.

Both stop at twenty guests and **report the stop** as an `undetermined` entry
saying how many were not examined and why, so the count is explicitly a floor
rather than silently a total. NFR-002 is about result size and this is about call
count; they are different bounds and only the first was in the plan.

---

## 8. Structure — modules and helpers the plan's technical context does not name

| Module | Why |
|---|---|
| `integrations/proxmox/investigation.py` | Three obligations run through all seventeen tools — say what you could not determine, stay bounded by ranking, answer rather than dump — and each decays into a comment if it is not a function. `report()` is what makes "states what it could not determine" a property of the package rather than a habit of whoever wrote each tool, and the contract sweep asserts it over the whole set. |
| `ProxmoxClient.storage_configuration`, `.disk_smart`, `.zfs_pool_detail` | Three reads feature 044's survey did not need. The cluster-wide datastore declaration is what decides whether a guest can move at all; SMART attributes are what predict a failure the verdict does not; a ZFS pool's device tree is where the fault is when the pool still says `ONLINE`. |
| `ClusterConfiguration.last_man_standing`, `.links` | FR-002 names last-man-standing explicitly, and the declared rings are what make "a ring only one node has can never come up" a reading rather than a guess. |
| `HighAvailabilityState.services` | `/cluster/ha/resources` carries the definition and `/cluster/ha/status/current` carries what the manager currently believes. A view with only the first reports a resource as `started` while its node is being reset. |
| `PhysicalDisk.used_for` | The `used` field is what makes the incompleteness of the backing map in §2 legible rather than mysterious. |
| `tests/support/proxmox.py::investigating`, `RecordedProxmox`, `client_for` | A tool builds its own client from the process binding and takes no transport, so a tool test needs a bound access rather than a client. Putting it in the shared support module rather than in each of the five new test files is what stops five fakes disagreeing about what Proxmox does. |

---

## 9. Test-support deviations worth stating outright

- **`_ImpatientAccess`.** A capability constructs its own client and takes no
  retry policy, so the only place a test can shorten the schedule is the access
  binding. The sweeps in `tests/contract/integrations/
  test_proxmox_investigation.py` exercise nineteen tools against five recorded
  states plus an unreachable cluster; at the real backoff that file took 45
  seconds, and at one attempt it takes under two. What is being tested there is
  the tool's behaviour when a node does not answer, not the base client's
  backoff, which has its own tests in `tests/unit/integrations/
  test_base_client.py`.
- **`tests/unit/integrations/test_proxmox_reads.py` lost its local transport.**
  It had a path-keyed `RecordedTransport` and its own `client_for`; both now come
  from `tests/support/proxmox.py`, which additionally keys on the query string —
  SMART is read per disk, and a transport that dropped the parameter answered
  every drive with one drive's attributes. Same tests, one fake.
- **No sixth `ClusterState` was added.** The degraded cases each success
  criterion needs (a ZFS pool on a cluster that has none, a thousand snapshots, a
  live lock, a full host with an empty guest) are supplied per test through
  `investigating(responses=...)`. A sixth recorded state would have to be swept
  by every existing test that iterates `STATES`, for cases only one test reads.

---

## 10. `def walk(` was renamed `def descend(`

`tests/unit/integrations/test_proxmox_transport.py::
test_the_package_reimplements_neither_retry_nor_pagination` rejects `def walk(`
anywhere in the package, because a second pagination walk would make this vendor
behave differently from the other eighty-odd under load. The ZFS device-tree
recursion in `zfs_health.py` and `disk_health.py` is a tree traversal and not
pagination, but the guard is a string check and the guard is right to be blunt.
The functions were renamed rather than the check relaxed.

---

## 11. `plan.md` and `tasks.md` are headed "044"

Both documents open `# Plan — 044 Proxmox Investigation Capabilities` and
`# Tasks — 044 …` while `spec.md`, the directory and the branch all say 045.
Read as a typo in the headings rather than as a claim about which feature the
documents describe: their content is this feature's — the tool names, the phases
and the success criteria all match `spec.md` — and feature 044's work is already
committed. Nothing was changed on that basis; it is recorded because a reader
comparing the three files will notice.

---

## Definition of done

| Criterion | Where it is proven |
|---|---|
| SC-001 | `test_proxmox_cluster_tools.py::test_a_two_node_cluster_with_one_node_down_reports_the_whole_arithmetic` and `::test_losing_quorum_is_reported_with_the_three_things_that_follow_from_it` |
| SC-002 | `::test_a_healthy_cluster_reports_its_margin_rather_than_a_bare_quorate`, `::test_a_cluster_with_room_to_spare_says_how_many_losses_it_survives` |
| SC-003 | `test_proxmox_storage_tools.py::test_thin_pool_metadata_exhaustion_is_reported_apart_from_data_exhaustion` — the degraded fixture has 96.1% metadata and 84.5% data |
| SC-004 | `::test_a_healthy_zfs_pool_above_the_capacity_threshold_is_flagged` — every device `ONLINE`, no errors, 96% capacity |
| SC-005 | `::test_no_reclaimable_item_is_returned_without_saying_what_it_protects` — asserted over every entry, and again in `test_proxmox_antipatterns.py` |
| SC-006 | `test_proxmox_guest_tools.py::test_a_lock_left_by_a_task_that_died_is_reported_as_orphaned_and_named` and `::test_a_lock_held_by_a_task_that_is_still_running_is_not_reported_as_orphaned` |
| SC-007 | `::test_host_storage_full_and_a_guest_filesystem_that_is_not_is_attributed_to_the_host` |
| SC-008 | `test_proxmox_backup_tools.py::test_an_unverified_backup_is_reported_as_unproven_rather_than_as_a_backup` |
| SC-009 | `::test_a_job_that_reports_success_but_has_not_run_for_a_week_is_read_by_exposure` |
| SC-010 | `test_proxmox_investigation.py::test_every_tool_against_an_unreachable_cluster_says_what_it_could_not_read`, parameterised over all nineteen |
| SC-011 | `test_proxmox_antipatterns.py` — one scenario per anti-pattern, each asserting both the tool's contradiction and the skill's warning |
| SC-012 | `test_proxmox_investigation.py::test_every_proxmox_capability_declares_itself_a_read` and `::test_no_proxmox_capability_module_calls_anything_that_writes` |

- **Every tool exercised against healthy, degraded and unreachable fixtures.**
  `test_every_tool_answers_in_every_recorded_state` covers all five recorded
  states for all nineteen; `test_every_tool_against_an_unreachable_cluster_…`
  covers the sixth case.
- **`make verify` green.** Lint, format-check, mypy strict over 1,607 files, all
  seven import contracts, all nine guard scripts, the console gate, and the
  suite: **11,465 passed, 22 skipped**, of which 274 are this feature's five new
  test modules. No pre-existing failure before or after.

---

## Not deviations, recorded because they look like they might be

- **Nineteen tools rather than the plan's implied set.** The plan's phases name
  seventeen; `proxmox_cluster_health` and `proxmox_protection_gaps` came from
  feature 044 and were kept (see §5). Both were migrated onto `report()` so that
  the "every result states what it could not determine" sweep is true of the
  whole set rather than of the new part.
- **`proxmox_storage_pressure` gained `consumers` rather than a new tool.**
  T-008 asks for per-datastore usage *with the largest consumers*; the tool that
  already reads the three fill levels is where the consumers belong, and a
  second tool would have read the same datastore list to add one field.
- **The corosync link tool has no `node` argument.** Links are a property of the
  cluster and the log is cluster-wide; a per-node argument would have implied a
  per-node answer that corosync does not have.
- **`proxmox_zfs_health` on a node with no ZFS returns success.** `applicable:
  false` with an empty pool list and a summary saying so. FR-008 asks for exactly
  this, and it is the one place where an empty result is the correct answer
  rather than a hidden failure — which is why it is stated as a field rather
  than left to be inferred from an empty list.
