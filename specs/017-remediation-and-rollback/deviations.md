# Deviations — 017 Remediation and Rollback

What was built differently from `plan.md` and `tasks.md`, and what was not built
at all. Written at the point of the implementing commit (`e61bf89`) so the next
person reading the plan does not have to diff it against the tree to find out
where the two disagree.

Three sections: things done differently and why, things found wrong during
implementation, and things not done.

---

## 1. Deviations from the plan

### `restart_workload` keeps `write_irreversible`

**Plan says** (Remediation capability set, FR-024 table): `write_reversible`,
rollback "None needed; records prior pod identities for verification".

**Shipped**: `write_irreversible`, as it already was before this feature.

**Why**: the plan's own row is internally inconsistent. A `write_reversible`
action whose rollback column reads "none needed" is not reversible in the sense
the level means, and the capability shipped in feature 003 already declares
`WRITE_IRREVERSIBLE` with a planner whose plan says `reversible=False`. Changing
the level to match the table would have made the declaration disagree with its
own planner, and would have moved a shipped, tested capability to a weaker
classification on the strength of a table cell.

**Consequence**: `restart_workload` is gated identically either way (both levels
are above `read_sensitive`), so nothing about the control changes. Its generator
produces *recovery* steps rather than a reversal, marked `reversible=False`, so
it does not go down the waiver path — which is what the plan's "None needed"
was reaching for.

### `rollback_release` renamed to `rollback_deployment`

**Plan says**: `rollback_deployment`. **Repository had**: `rollback_release`.

Followed the plan. The rename touched two files outside the feature's own tree,
which is worth recording because it is the kind of edit a reviewer asks about:

- `capabilities/skills/remediation/SKILL.md` — the skill directed the old name,
  which fails registry validation as a dangling tool reference. Its
  `directs_tools` list also grew to cover all seven capabilities, and its
  action-selection table gained the four new rows.
- `docs/capabilities.md` — generated; regenerated with
  `PYTHONPATH=$PWD uv run python tools/generate_capability_docs.py`.

### Three modules the plan's project structure does not list

The plan's structure block names nine files under `platform/remediation/`. Three
more exist:

| Module | Why |
|---|---|
| `platform/remediation/components.py` | FR-025's four components need a declared contract, and it has to live in tier 3 for tier-2 capabilities to implement it. Putting it in `models.py` would have mixed protocols into a module of values. |
| `capabilities/tools/remediation/control_plane.py` | The capabilities need somewhere to reach a control plane. The plan assumed vendor integrations that do not exist yet, so this is one narrow port with a process-level binding, the same arrangement `topology_query` uses. |
| `capabilities/tools/remediation/_base.py` | Six of the seven capabilities differ only in *which fields* they read and write. Seven copies of "read the control plane, turn it into a snapshot" would be seven chances to handle an unreadable target differently. |

### `ApprovalService.queue` gained an `expiry_hours` parameter

**Plan says** (Technical context): "Feature 015's state machine, with a
remediation-specific expiry." It does not say how.

**Shipped**: a keyword parameter on `queue`, which narrows the organisation's
window and never widens it (`min(expiry_hours, policy.change_expiry_hours)`).

The alternative considered and rejected was constructing the remediation
approval service with a policy whose `change_expiry_hours` was fifteen minutes.
That would have made an organisation-wide setting mean something different
depending on which caller held the service, which is worse than one extra
parameter.

This is a change to a shipped feature's public signature. It is additive and
defaulted, so no existing caller changes.

### `RemediationApplier.apply` deliberately does nothing

The plan's sequence has approval, then plan persisted, then re-evaluation, then
execution. Feature 015's contract is that approval *applies* the change through
its applier. The two cannot both be true, so the applier records the grant and
`RemediationExecutor` performs the action.

`read` on that applier is not a no-op, and is why the type exists at all: it is
what feature 015's conflict detection fingerprints the target against. It finds
the right reader through `ChangeTarget.path`, which for a remediation carries the
capability name rather than a field within a document.

### Test-first was not followed for the platform layer

`CLAUDE.md` requires the failing test to land before the implementation, and
`plan.md` Phase 1 requires all eight gating proofs red before anything else.

**What happened**: `platform/remediation/` was written before its tests. The
capability set and the two corrections in section 2 went through a genuine
red→green cycle; the platform layer did not.

Recorded rather than papered over. Two of the tests written afterwards did fail
against the implementation and forced real changes — which is evidence they were
worth writing, and not evidence that writing them second was fine.

### Test module basenames

`tests/` has no `__init__.py` anywhere (the convention its own conftests state),
so pytest requires unique test module basenames across the whole tree.
`test_execution.py` collides with `tests/unit/core/agent/test_execution.py`, and
`test_audit.py` was renamed alongside it for symmetry:

- `test_remediation_execution.py`
- `test_remediation_audit.py`

The first attempt at this suite did add a `tests/unit/platform/remediation/__init__.py`
so relative imports from `conftest` would work. Removed: sibling suites
redeclare their constants at module level, and the approvals conftest says
explicitly why reaching into a conftest by module path is a trap.

---

## 2. Found wrong during implementation

Neither of these is a deviation from the plan — the plan does not go to this
level of detail. Both changed the shape of `models.py` from what a reader of
`plan.md` would expect, so they belong here.

### A rollback plan needs two snapshots, not one

`plan.md` lists `RollbackPlan` in `models.py` with no further detail, and the
obvious implementation carries one snapshot: the state to restore.

That is wrong, and the test suite caught it. Checking a rollback against the
*pre-execution* state refuses every legitimate rollback, because the action's
whole effect is that the target no longer looks like that. So a plan carries:

- `recorded_state` — where the undo goes;
- `applied_state` — what the undo expects to find, stamped by the executor from
  the post-execution read.

The code reads plausibly either way, which is exactly why it is now a field with
a comment rather than an assumption.

### An unreadable target is not an empty one

`StateSnapshot.unreadable` is a distinct value and `known` is checked at every
comparison. An empty snapshot fingerprints to a real hash and would compare equal
to another empty one, so a rollback would proceed against a target nobody could
read. `StateSnapshot.matches` therefore returns `False` for an unknown snapshot
compared with itself.

### `RollbackPlan`'s constructor invariants moved

Two checks that looked like constructor invariants are not:

- **Identity**: a capability's generator has no business choosing the identifier
  the deployment stores the plan under. `PlanFactory` assigns it; `to_stored`
  refuses a plan that never got one.
- **Emptiness**: an empty *derived* plan is the no-derivable-plan case and goes
  down the waiver path in `PlanFactory`. An empty *scoped* plan is correct and
  common — an action that changed nothing has nothing to undo — and rejecting it
  in the constructor made the honest answer unrepresentable.

---

## 3. Not done

### T033 — execution record persisted into the run trace

**Not done.** `ExecutionRecord.to_record()` exists and the audit trail carries
the same facts, but nothing writes the record to `RunTraceStore`. An
investigation's own trace therefore does not answer "what did this change"
without a join against the audit trail.

`RemediationExecutor` has no `gateway`/`scope`, so wiring this means either
giving it those or handing it a recorder port. The second is probably right —
the executor already takes an auditor, and a trace recorder is the same shape.

### `appliers_for()` still has no remediation entry

`platform/approvals/appliers.py` builds the applier map a deployment wires its
approval service with, and its docstring says: "Remediation is absent and stays
absent until feature 017 fills it. Its diff renderer and its side-effect gating
are already here, so wiring it is one entry in this map rather than a second
approval mechanism."

`RemediationApplier` exists and the gating suite wires it directly, but
`appliers_for()` was not extended. A deployment built through that helper will
raise `KeyError` on `ChangeType.REMEDIATION` when a remediation approval is
granted.

The reason it was left is a real one: `appliers_for` takes `config` and
`proposals`, both tier-3 services, and the remediation applier needs a
`ComponentRegistry` that is assembled in tier 2. Adding a `remediation:
ComponentRegistry | None = None` parameter is the fix and does not break the
tier rules — the caller supplies it.

### T014 — re-assert the registry build failure on missing `side_effect_level`

**Not done as a test in this feature.** Feature 003 enforces it and has its own
coverage. The task asked for a re-assertion here, on the grounds that a property
this feature depends on should fail in this feature's suite too. It does not.

### T027 — rollback invocable from every surface

**Partially done.** The window is enforced (`verification.require_window`,
default one hour) and `RollbackExecutor` is callable from anywhere. There are no
surfaces yet — CLI is feature 019, REST is 020, console is 021, chat is 022 — so
there is nothing to wire it into. The mechanism is complete; the reach is not,
and cannot be until those land.

### T051 — `make check-provenance`

There is no such Make target in this repository. `docs/provenance-map.md` was
updated by hand: the feature-017 rows in section 7 moved from REFERENCE to
ADAPT, and a "Feature 017 — written fresh, not adapted" table was added.

---

## Definition of done, as it actually stands

| Criterion | State |
|---|---|
| SC-001 no write without approval or allow-list | Green — asserted through all three entry points |
| SC-002 plan persisted before every executed write | Green — asserted from the store, across the whole set |
| SC-003 kill switch refuses immediately, overriding an approval | Green |
| SC-004 verification detects induced divergence | Green |
| SC-005 partial success produces a correctly-scoped plan | Green |
| SC-006 allow-listed action refused when conditions lapse | Green |
| SC-007 rollback refuses on target mismatch | Green |
| SC-008 denial lets the investigation continue | Green |
| `make verify` | Green — 3690 passed, 15 skipped |

The eight success criteria are met. The three open items above are wiring rather
than mechanism, and none of them weakens a control: T033 loses a record that the
audit trail also holds, the applier-map gap fails loudly rather than silently,
and T027 has no surface to reach yet.
