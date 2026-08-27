# Deviations — 046 Proxmox Remediation Capabilities

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 1. The Definition of done's real-cluster item cannot be satisfied

**Planned.** "Every action exercised once against a real cluster in feature 049's
harness." (NFR-003, and the third line of the Definition of done.)

**Done.** Every action is exercised twice against the *recorded* cluster — once
against a Proxmox task that succeeds and once against one that fails —
parameterised over the whole declaration set, in
`tests/unit/capabilities/remediation/test_proxmox_plane.py`. Nothing has been run
against a live hypervisor.

**Why.** Feature 049's harness does not exist. It is a later feature in the same
wave, and there is no cluster-backed scenario harness in the repository to hang
the run on. Writing something adjacent to it here would either be a second
harness for 049 to replace, or a harness that quietly needs an address and a
token — which is the thing `make verify` on a laptop exists to rule out.

**What this means for the definition of done.** The item is genuinely unmet and
deliberately so. It is the only one. NFR-002 — "testable against recorded task
outcomes, including failures, without a live cluster" — is met in full, and the
sweep is written so that pointing it at a live cluster later is a change of
transport rather than a change of test.

---

## 2. The three bands of FR-006 map onto five risk classes

**Planned.** FR-006 names three bands: "the lowest class", "the middle class",
"the highest class". The scale `RiskClass` offers is five.

**Done.** The bands are read as the ranges the five-class scale already means,
and the mapping is stated in `risk.py`'s module docstring:

| FR-006's band | Classes used | Why that reading |
|---|---|---|
| lowest | `trivial`, `low` | Everything at or below `DEFAULT_RISK_BOUND`, which is what "may run unattended under the ordinary posture" means operationally |
| middle | `moderate` | One class, and it is the one whose description — "undone only by a further action" — is exactly what the band contains |
| highest | `high`, `critical` | The scale distinguishes "not reversible without a restore" from "can destroy data with no other copy", and the second is the distinction FR-008 turns on |

Clearing an orphaned lock is therefore `trivial` and starting a stopped guest is
`low` — both "the lowest class" in the band sense, and they differ because
starting a guest commits a node's memory and disk to it and clearing a flag does
not. Collapsing them into one class would have thrown away the difference for
the sake of a word.

**Why this is not a licence.** The mapping is asserted, not assumed:
`test_the_lock_clear_and_the_guest_start_are_inside_the_default_risk_bound`
checks the band rather than the class name, so a later edit that moved either of
them out of the band fails.

---

## 3. Thirteen capabilities in one package, not thirteen packages

**Planned.** "`capabilities/tools/remediation/proxmox_*/`, following the existing
applier layout" — which is a package per capability, each with `tool.py`,
`read_state.py`, `apply.py`, `rollback.py`, `verify.py`.

**Done.** One package, `capabilities/tools/remediation/proxmox/`, with the
capabilities grouped by family (`guests.py`, `movement.py`, `storage.py`,
`backups.py`) over shared machinery (`risk.py`, `declaration.py`,
`preconditions.py`, `components.py`, `plane.py`, `escalation.py`, `signals.py`).

**Why.** The existing layout is five files per capability because each of the
seven cross-vendor capabilities has a genuinely different reader, applier,
generator and verifier. These thirteen do not: they differ in which fields they
read, what state they intend, and what their undo reads like — which is a
declaration — and they are identical in *how* those four components are
assembled. Sixty-five files, sixty of them near-copies, is sixty chances for one
of them to handle an unreadable target differently from the rest, which is the
exact failure `_base.py` was written to prevent for the original seven.

The shape that replaced it keeps the property the plan wanted: each capability
still declares its own reader fields, intent, rollback narrative and
verification, and `components_for` assembles them. What is shared is the
assembly, not the judgement.

---

## 4. Every capability declares a `ProxmoxRemediation`, which the plan does not name

**Not in the plan at all.** `declaration.py` adds a declaration type carrying the
capability's category, endpoint, method, preconditions, rollback, verification,
privileges, snapshot fields, identity fields, intent function, and whether it
writes configuration or assumes a node is dead.

**Why.** FR-002 requires the failure to be "at registration, not runtime", and
the strongest available form of that is a value that refuses to be constructed —
so a capability missing a piece is an import error and nothing incomplete can
reach the registry because nothing incomplete can exist. That needs somewhere for
the six things to be declared together, and the `@tool` metadata is the wrong
place: it is shared with eighty-five integrations and has no notion of a
precondition or a Proxmox privilege.

The declaration is also what makes SC-002 and SC-008 sweeps rather than lists.
The risk class is a *property* reading the table rather than a field, so the two
cannot drift; the endpoint is declared rather than derived, so the prohibition
check has something to read that is not the implementation.

---

## 5. `identity_fields` is a subset of `fields`, and had to be

**Not in the plan.** FR-003 and FR-004 say a precondition re-reads the target and
refuses when it changed. The obvious implementation compares the whole snapshot.

**Why it does not.** A running guest's uptime changes every second, and `uptime`
has to be in the snapshot because it is the only field that distinguishes a
reboot that happened from one that did not. Comparing the whole snapshot would
have refused every action against every running guest — a check that is right
about nothing and fires on everything, which is the kind that gets deleted.

So the declaration names the subset that says the target is *the same thing*:
where it lives and what holds it. `proxmox_unlock_guest` is the interesting case
— the lock is what it changes, so its identity is the node alone.

---

## 6. Writes live in `integrations/proxmox/writes.py`, as a subclass

**Not in the plan.** The plan's technical context names the executor, the
resolver, the obligations and the poller, and says nothing about where the HTTP
verbs go.

**Done.** `ProxmoxWriteClient(ProxmoxClient)`, in its own module, with an
explicit `WRITE_ENDPOINTS` list.

**Why a subclass rather than methods on the existing client.** `ProxmoxClient`'s
docstring says every method on it is a `GET` and gives the reason: a write among
eighty reads is one typo away from being called by something that thought it was
reading. That statement had to stay true. A precondition is a read taken
immediately before a write, though, so the two have to come from one object or
they are two different pictures of the cluster — which a subclass gives and a
separate client does not.

**Why the endpoint list exists.** So SC-008 can be swept over the client's whole
write surface rather than over the capabilities alone. A capability could declare
one endpoint while a client method offered another, and the test asserts over
both together.

**One behaviour worth naming.** A write does not fail over between endpoints and
is not retried across them, unlike every read. The first attempt may have landed,
and the second would be a change nobody approved.

---

## 7. The escalation is modelled, and is not performed by the reboot

**Planned.** FR-010: "A restart MUST attempt graceful shutdown first and escalate
to a hard stop only after a declared timeout, recording the escalation and
classifying the hard stop separately."

**Done.** `proxmox_reboot_guest` and `proxmox_shutdown_guest` never escalate —
the plane passes `force_stop=False` explicitly, with a comment saying why.
`escalation.py` decides whether an escalation is *due* and returns it as a
proposal carrying the hard stop's own risk class; performing it is
`proxmox_stop_guest`, through the gate, with its own approval.

**Why not an escalating action.** An action that silently became a hard stop
after a timeout is precisely the laundering FR-010 exists to prevent: an operator
who permitted the graceful shutdown unattended would have permitted the hard stop
unattended, and those are `moderate` and `critical`. Modelling the escalation as
a separate proposal is what lets the two be configured apart, which the plan's
own architecture note says is "the configuration most people actually want".

**The consequence.** "Records the escalation" is realised as an `Escalation`
value with a `to_record()`, produced by `escalation_for` and attached by whatever
holds the incident. Nothing in this feature's scope owns an incident timeline to
write it into, so the value is produced and returned rather than persisted here.

---

## 8. `proxmox_reclaim_storage` and `proxmox_remove_orphaned_volume` declare no rollback

**Planned.** FR-001 allows "its rollback plan or an explicit statement that none
exists". Nothing says which actions take which.

**Done.** Both deletions declare no rollback, with the reason, and take the
waiver path — refuse unless an operator explicitly accepts the absence, and audit
the acceptance. `clear_cache` was previously the only shipped capability on that
path; there are now three.

**Why.** A deleted snapshot has no undo. A plan claiming otherwise would be a
plan that could not run at the moment it was needed, and the absence of one is
itself the signal the waiver path exists to raise. The cost is real and
deliberate: neither action can run at any autonomy level without a human
accepting the missing plan, which is the correct posture for deleting somebody's
only recovery point.

---

## 9. The HA relocate uses the resource-configuration endpoint

**Planned.** FR-015: "An HA relocate MUST be distinct from a manual migration and
MUST be the highest risk class."

**Done.** It is a distinct capability at `high`, and it writes
`PUT /cluster/ha/resources/{sid}` — changing the group and requested state the
manager holds — rather than commanding a relocation directly.

**Why.** That is the write the REST API offers. `ha-manager crm-command relocate`
is a shell command on a node, and reaching a shell on a node is out of scope by
the specification's own last line and forbidden structurally by a test feature
044 already ships. Changing what the manager holds is the same act through the
interface this system is allowed to use, and it is honest about the difference:
the manager acts on its own schedule and may move other resources as a
consequence, which is what the capability's description and its class say.

**Why `high` rather than `critical`.** It moves guests and does not destroy data.
`critical` is reserved for actions that can lose something with no other copy —
FR-008's rule — and stretching it to cover an availability action would blur the
line the storage deletions depend on.

---

## 10. An offline migration is refused, including for a stopped guest

**Planned.** FR-013/FR-014: prefer online, refuse rather than silently performing
an offline migration.

**Done.** The `online_migration_possible` precondition refuses when the guest
declares passthrough hardware **and** when the guest is not running.

**Why the second.** Proxmox performs the move offline for a stopped guest, and
that is a different action with a different cost from the one that was approved.
Refusing is the literal reading of FR-014 and the conservative one. It does mean
this deployment cannot move a stopped guest at all, which is a real limitation
and is stated in the capability's own anti-examples rather than left to be
discovered.

---

## 11. "The system proposes it to a human" has no channel of its own

**Planned.** FR-020: "No action may extend a thin pool or a ZFS pool; the system
MUST propose that to a human." Similarly FR-027 for node services.

**Done.** The prohibition is declared with the sentence a human is handed —
`ProhibitedOperation.why` — and `prohibition_for(path)` returns it, so anything
that refuses a prohibited path has the prose to show. There is no separate
"propose a pool extension" artefact.

**Why.** Proposing is feature 040's `Outcome.PROPOSE`, and it proposes *actions
this deployment could take*. A pool extension is not one — no capability performs
it, deliberately — so there is nothing to propose in that machinery's terms.
Inventing a second proposal channel for actions the system will never perform
would be a surface with one user and no gate behind it. The prohibition's stated
reason is the handover, and it is asserted to be non-empty for every prohibition.

---

## 12. Test files, and the existing tests that had to change

Three existing tests changed because this feature adds capabilities to sets they
sweep. None was loosened.

- **`tests/contract/remediation/test_remediation_capabilities.py`** — the
  `SCENARIOS` table gained thirteen rows and `NO_DERIVABLE_PLAN` gained two
  names. The suite is parameterised over `COMPONENTS`, which is exactly why it
  failed the moment the hypervisor writes were registered: that is the suite
  working.
- **`tests/unit/platform/remediation/test_rollback.py`** — asserted
  `len(COMPONENTS) == 7`. Replaced with an assertion that the capability names
  are unique, which is the property the count was standing in for and which does
  not need editing every time a capability lands.
- **`tests/contract/integrations/test_proxmox_investigation.py`** — asserted that
  *every* capability whose evidence source is Proxmox is a read. Narrowed to the
  capabilities under `integrations.proxmox.tools`, which is what the file is
  about, and a new test asserts the complement: anything else reaching Proxmox is
  a registered, gated write with an approval and a rollback plan. There is no
  third category, and a tool landing in one fails.

`tests/support/proxmox.py` gained a write-capable transport: it records what was
written including the query string, synthesises the task identifier Proxmox
answers a write with, and answers the subsequent status and log reads. The
`task_exit` it reports defaults to `OK`, so the failing case is something a test
has to ask for rather than something it gets by accident.

---

## 13. Constants went to a new domain module

`config/constants/hypervisor.py` — shutdown timeout, escalation timeout, five
settle periods, the backup collision window, the replication rate limit, the
reclamation cap, and the node count at which quorum becomes ambiguous.

**Why a new module rather than `closed_loop.py` or `security.py`.** These are
facts about a hypervisor, not about verification or about the approval gate. How
long a guest's operating system takes to close its files is not a preference an
operator holds. `config/AGENTS.md` says a new bound goes in "the domain module
that owns it", and none of the existing ones owns this domain.

---

## Not deviations, recorded because they look like they might be

- **`Sys.Console` is declared for the high-availability and replication
  capabilities.** It is a superset of what those endpoints strictly require.
  Declaring a *sufficient* privilege over-asks, which surfaces to an operator as
  "your token needs more"; declaring an insufficient one reports a token as
  sufficient for a job it cannot do, and the failure surfaces during an incident.
  `integrations/AGENTS.md` is explicit that the second is the worse error, and
  the reasoning is written beside both declarations.
- **The risk table is `risk.py` rather than a document.** NFR-004 asks for one
  place, documented, asserted against the registry. The module carries the
  reasoning in prose per row, `describe_table()` prints it, the generated
  capability reference carries every class, and `docs/remediation-and-rollback.md`
  carries the shape. A second hand-written copy would be the thing NFR-004 exists
  to prevent.
- **Preconditions run inside the control plane rather than in the executor.**
  The plan says the executor is used "unchanged", and it is: the checks happen
  where the write happens, which is inside the sandbox, holding the target's
  lock, immediately before the call. Putting them in the executor would have
  meant a hypervisor-specific hook on the object every other remediation shares,
  which is the Proxmox-specific path FR-018's neighbouring sentence rules out.
- **`proxmox_unlock_guest` has one writer for both directions.** Clearing the
  lock and putting it back are the same configuration edit with a different
  argument, and the rollback replays through the same capability. Two writers
  would be two chances to spell the configuration key differently.
