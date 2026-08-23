# Deviations — 048 Homelab Profile and Cluster Guardian

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 1. The shipped set is forty-six detectors, not "roughly thirty"

**Planned.** `spec.md`'s primary story says "roughly thirty detectors are live".

**Done.** Forty-six.

**Why.** The count is a consequence rather than a target. FR-009 through FR-014,
plus FR-013a and FR-013b, enumerate the conditions that MUST be covered, and
several of them are two detectors rather than one for reasons the requirements
themselves give:

- **Datastore usage** is two — high and critical. FR-010 says "datastore usage
  above thresholds", plural. Eighty-five per cent is advice and ninety-five is
  the point at which the next backup fails, and they want different severities
  and different remedies.
- **Guest saturation** is two — memory and CPU. FR-011 says "guest memory or CPU
  saturation sustained", and one detector over two signals is not expressible:
  a detector reads one signal.
- **Failed units** is two — any failed unit, and a unit that has been failed
  continuously. FR-013a asks for both explicitly, and they are genuinely
  different findings: the first is "something broke", the second is "and nobody
  is going to fix it".

Thirty was an estimate in prose; the requirement list is the specification, and
`MAX_DETECTORS` is 100, so nothing is truncated. A test asserts the whole set
fits inside that bound.

---

## 2. `homelab` is the same four components as `standard`, not a smaller set

**Planned.** FR-003 lists what the profile must include and says it must exclude
"components only a multi-team deployment needs". The `dev` profile's precedent
is to fold the credential proxy into the application process and save a
container.

**Done.** Four containers — Postgres, the credential proxy, the application, the
console — identical to `standard`. What differs is the ceiling: every service
carries a memory and CPU limit, the four sum to 4 GiB and 2 CPUs, and
`tests/contract/deployment/test_homelab_profile.py` holds the compose file and
`config/constants/deployment.py` to each other.

**Why.** The credential proxy's own container *is* the trust boundary — it is
the only process that holds a secret, and `AGENTS.md` names its isolation as one
of the non-negotiables. Folding it into the application to save about 256 MiB
would trade this deployment's one security boundary for six per cent of its
footprint, on the profile most likely to be running on the infrastructure it
manages. The multi-team components the requirement means are SSO, the
leader-claimed scheduler and Kubernetes sandboxing, and none of those is
present.

The consequence worth stating: `homelab` is not "small `standard`". It is
`standard` with an enforced ceiling and a different set of assumptions about
where it is running, and `DeploymentProfile`'s docstring says so.

---

## 3. `DEPLOYMENT_PROFILES` and the enum were reordered

**Not in the plan.**

`tests/unit/platform/startup/test_profiles_and_keys.py` asserts that concurrency
ceilings rise along `DeploymentProfile`'s member order. Appending `HOMELAB`
after `ENTERPRISE` broke it, correctly: the order is not decoration, it is what
stops a new profile being given a ceiling nobody compared to the others.

`homelab` was inserted after `dev` — the two share a ceiling of two concurrent
investigations, and both sit below `standard`. The constant tuple was reordered
to match, and its docstring now says the order is load-bearing so the next
person does not append.

---

## 4. Three Proxmox resource-kind names moved to `config/constants/hypervisor.py`

**Not in the plan.**

`KIND_STORAGE_POOL`, `KIND_REPLICATION_JOB` and `KIND_PHYSICAL_DISK` were
defined in `integrations/proxmox/discovery.py`, which is tier 2. The shipped
detector set declares which resource kinds each detector applies to, and it lives
in `platform/guardian/`, which is tier 3 and may not import tier 2.

The alternative was writing the three strings a second time, which is the "one
fact in two places" the repository's own conventions warn about. So the names
moved to the tier-4 constants module that already owns hypervisor facts, and
`discovery.py` imports them — its `ResourceKind` *declarations*, which are the
part that is genuinely the integration's, stayed where they were.

This is the same disposition feature 047 recorded for `PROXMOX_ESTATE_SOURCE`
and for the same reason.

---

## 5. Signals are namespaced to the guardian rather than named after exporters

**Not specified.** The plan says the detector set is "shipped configuration
loaded through the config service".

**Done.** Every shipped detector reads `guardian.<domain>.<reading>` — for
example `guardian.storage.thin_pool_metadata_percent` — and separately declares
where that reading comes from: `HYPERVISOR` for one this deployment polls, or
`PUBLISHED` with a metric matcher for one queried from the operator's own
monitoring.

**Why it had to.** A detector named after `node_lvm_thin_pool_metadata_used_percent`
would be a detector that stops working the day the operator's exporter changes,
and would also make the same condition two detectors on two clusters. Naming the
*reading* rather than the metric is what lets one detector work whether the
number arrived from feature 044's polling or feature 047's bridge.

The origin field is not decoration either. It is what makes NFR-002 computable:
`platform/guardian/load.py` derives the declared call rate from the shipped set
by counting only the hypervisor-origin sources, so adding a detector over a
reading Prometheus already scrapes costs the cluster nothing and the declaration
says so. The measured figure is 6.8 calls a minute against a ceiling of 12.

---

## 6. The firing and healthy fixtures live on the detector, not in the test

**Planned.** T-040: "Failing test per detector: fires on a fixture representing
its condition, does not fire on a fixture representing health."

**Done.** `ShippedDetector.firing` and `.healthy` are **required fields with no
default**, and `tests/contract/guardian/` drives the real evaluator over windows
built from them.

**Why.** A fixture table beside the set is a table somebody forgets to extend,
and SC-002's value is entirely in the forty-seventh detector being impossible to
add without both readings. Making them fields moves that from a convention to a
`TypeError`.

Most of the values are the surveyed cluster's own numbers rather than invented
ones — 96% for `TeraChad`, 99.6% for CT100's thin volume, 31.98% for the
`data-pool` metadata, `keep-last=2` for retention, nine failed units on `pve01`,
24 pending updates. That is what makes them fixtures representing the condition
rather than fixtures representing the threshold.

A third assertion was added beyond what T-040 asks: a healthy fixture must reach
a verdict rather than reporting `INSUFFICIENT`. Without it, a detector whose
duration outgrew the window would pass "does not fire" while proving nothing,
which is exactly how a shipped set drifts into silence.

---

## 7. The recommended preset acts on five capabilities, and two of them raise the
   risk bound

**Planned.** FR-018: "making low-risk reversible actions autonomous and leaving
the rest gated." The primary story says "locks clear themselves, backups retry
themselves".

**Done.** `proxmox_unlock_guest`, `proxmox_start_guest` and `proxmox_resume_guest`
at a `low` bound; `proxmox_retry_backup` and `proxmox_resync_replication` at
`moderate`, each stating why in its own reason string.

**Why the last two needed saying.** Feature 046's risk table classes both retries
as `MODERATE`, on the correct ground that a backup which ran cannot be un-run.
Nothing here reclassifies them — that table is not this feature's to edit — but
the preset raises its own bound for those two capabilities, because the
asymmetry runs the other way: retrying wrongly writes a copy nobody needed, and
not retrying leaves a gap discovered when the backup is wanted.

**What is deliberately absent.** `proxmox_reclaim_storage` and
`proxmox_remove_orphaned_volume` are `CRITICAL` with no undo, and
`proxmox_stop_guest` is `CRITICAL`. The primary story's "backups prune
themselves" was not implemented as an autonomous action for that reason: on a
homelab there is no second copy, and a preset that deleted backups unattended is
the one that ends with the whole system switched off.

---

## 8. Configuration went under `policies.observation.guardian`

**Not specified.** The plan says "shipped configuration loaded through the config
service, versioned, overridable without editing".

**Done.** `GuardianSettings` on `ObservationPolicySettings`, beside `detectors`
and `bridge`.

**Why there.** Whether this team runs the shipped detector set is a policy about
what it watches, which is what `policies.observation` already holds. Feature 039
put detectors there and feature 047 put the bridge there, both for the same
reason and both recorded as such. A seventh top-level section would have made
"the guardian" a concern separate from observation, which it is not.

`DetectorOverrideSettings` has two scopes and no third — deployment-wide and
per-resource — because anything more expressive is a rule language, and the
reason not to build one is the reason a detector has four condition kinds.

---

## 9. The console page renders a document the server resolved

**Not in the plan.** T-043 says "Detector documentation visible in the console,
not only in a file".

**Done.** `GET /v1/config/{node_id}/guardian` resolves the shipped set against
the node's topology and overrides and returns the whole thing — rationale,
threshold and remedy included. `surfaces/console/pages/guardian.py` renders that
mapping and holds no rule of its own.

**Why it is recorded.** The first implementation imported
`platform.guardian.resolution` into the console and resolved there. That is
faster, avoids a round trip, and is forbidden:
`tests/architecture/test_console_is_a_pure_client.py` names
`platform.config_service` among the areas the console must never reach, and the
risk it guards is precisely this one — a console whose idea of what a threshold
resolves to quietly diverges from the deployment's. The test caught it, which is
the whole point of having it.

The rationale travels *with* the detector rather than behind a second call, and
that is deliberate: the requirement is about when somebody reads the reasoning,
and a second round trip is a click.

---

## 10. The heartbeat pushes; nothing schedules the push, and self-placement is
    not called at startup

Recorded as a gap rather than claimed.

**What is real.** `HeartbeatPusher` builds the payload, sends it through a
transport protocol, advances a sequence number a watcher can see a gap in,
refuses to advance it on a failed push, and raises rather than swallowing a
delivery failure — a dead-man's switch whose own failures were silent would be a
second copy of the problem it exists to catch. It owns no timer: `is_due`
answers "should one go now" and whatever drives the deployment's clock asks,
which is the same shape `EscalationRegistry` takes and for the same reason.

FR-028's "no configuration that disables it while the guardian is enabled" is
structural rather than a rule somebody remembers: the only setting is *where* to
push, and an empty destination is refused at construction, because treating it
as "off" would be a disable switch under another name.

**What is not.** Nothing schedules the tick that calls `is_due`, and no
transport implementation ships. Both are composition — a scheduler job kind and
an outbound HTTP client — and composition here is feature 030's concern, which
is the same seam features 039 and 047 left for the same reason.

**Self-placement is computed but nothing calls it at startup.**
`platform/guardian/selfaware.py` answers "am I a guest of what I watch" and
"which open incidents are about me", both proven against the real estate
resource type. Nothing invokes it during the startup sequence, so FR-026's "MUST
detect ... and MUST say so" is available in one call and not yet said by
anything at boot.

A deployment wiring this needs three lines in its composition root: locate
itself against the estate, construct a `HeartbeatPusher` if a destination is
configured, and ask `is_due` on the observation tick. The `HeartbeatReadiness`
warning covers the case where it does not — which is the honest handling, since
the warning is exactly "nothing outside this deployment would notice if it
stopped".

---

## 11. Two "Definition of done" items cannot be satisfied as written,
    and a third turned out to be already met

**SC-001's soak.** `platform/guardian/footprint.py` judges a soak, refuses to
conclude from one shorter than twenty-four hours, and reports a rising floor
separately from a peak — all tested. No twenty-four-hour soak has been run,
because `make verify` takes seconds by design and a gate that took a day is a
gate people learn to skip. The declared ceiling *is* enforced, by the container
runtime, and that half is asserted against the compose file.

**SC-013's backup and restore round-trip — covered, and nothing was added.**
Checked rather than assumed: `tests/contract/persistence/test_operations.py::
test_a_backup_restores_into_a_clean_database_with_its_integrity` already dumps,
restores into a clean database, and asserts referential, vector and graph
integrity on the way back out. `make backup` and `make restore` are the one
command each that T-005 asks for, and `platform/startup/backup.py` decides
restore, migrate-forward or refusal before anything is written.

The homelab profile needed nothing for this because it changes nothing that
matters to it: one PostgreSQL, one named volume, one `pg_dump`. That test needs
a live database, so it runs under `make test-postgres` and skips with a message
naming what is missing on a laptop with no Docker — the pattern this repository
already established. This item is met by an existing named test rather than by a
new one, which is a better outcome than a second test asserting the same thing
about the same volume.

**Verification against a real cluster.** There is none reachable from the gate.
Every threshold and every fixture is drawn from the surveyed cluster's recorded
numbers, and the shipped set has not been run against a live Proxmox API. This
is the same disposition features 046 and 047 recorded, for the same reason:
feature 049 is the one that builds the harness.

---

## Not deviations, recorded because they look like they might be

- **One backup detector is gated on having a second node.** FR-012 lists "no
  replication jobs at all while guests sit on node-local storage" among the
  backup detectors, and every other backup detector applies at any size. This
  one cannot: replication is a copy onto *another* node, so on a single-node
  installation there is nowhere for it to go and "no replication jobs" is the
  arrangement rather than a finding. Left ungated it would fire on every
  single-node install on its first day, which is precisely the spurious cluster
  finding SC-007 exists to prevent. A test names it as the one exception, so the
  next detector that quietly needs a second node has to say so.

- **Constants written as "fire above" values.** `FAILED_UNITS_FIRE_ABOVE` is
  zero, not one, and `GUEST_RESTART_LOOP_FIRE_ABOVE` is two, not three. The
  detector condition is `> value`, so a constant named for the count that fires
  would be off by one at every call site — which is a defect that survives
  review because both readings look plausible. The names say which they are.

- **`storage-growth-to-full`'s threshold is derived arithmetic.**
  `STORAGE_GROWTH_PERCENT_PER_MINUTE` is computed from the high threshold and
  the declared horizon rather than written down, so the two cannot drift. The
  test's fixture is a ramp rather than a flat series, because a flat series has
  a rate of zero at any value and asserting that a growth detector does not fire
  on one would prove nothing.

- **The blind-spot detector is a state transition cleared by acknowledgement.**
  FR-013b asks for exactly that, and a test asserts it is the *only* detector in
  the set with that property — every other condition is one that can actually
  stop being true, and a second acknowledgement-cleared detector would be one
  somebody made structural by accident.

- **`compare({})` reports nothing rather than forty-six additions.** The first
  start after upgrading from a release that stored no fingerprints has nothing
  to compare against, and a report naming every detector as new is one nobody
  reads — including the next time, when it means something.

- **The fingerprint ignores prose.** A release that improves a rationale without
  moving a number has changed nothing an operator needs to review, and reporting
  it would train them to skip the report. A test asserts a reworded rationale
  produces the same fingerprint.

- **Test-first, per module rather than per phase.** The same sequencing features
  020 §7, 021 §7 and 047 recorded, for the same reason: a suite written against
  modules that do not exist can only fail on `ImportError`. Each module's tests
  were written, run and confirmed failing before the module existed — the
  topology suite was red against a missing `platform.guardian.topology`, the
  catalogue suite red against a missing `platform.guardian.catalogue`, and the
  fixture suite red on `longest_window_seconds` before it was green on
  forty-six detectors.

## Gate

`make verify` green: lint, format-check, mypy strict, all seven import
contracts, every guard script, the generated catalogues, the documentation
drift check, the console gate, and **12,568 passed, 22 skipped** — 654 tests
added, no pre-existing failure before or after.

Four generated artefacts were regenerated rather than edited, because the new
route changed each of them: `deploy/compose/.env.example`, the mock plane's
dataset and OpenAPI document (`python -m tools.mockplane build` and `contract`),
the console's TypeScript client (`make console-client`), and the configuration
reference page (`make docs`). Each has a check in the gate that fails on drift,
and each failed before it was regenerated.
