# Plan — 040 Closed-Loop Remediation

## Technical context

| Concern | Choice |
|---|---|
| Tier | Extends `platform/remediation/`, adding verification, effectiveness and recurrence beside the existing execution and gating |
| Durability | Verification obligations are rows in Postgres, claimed with the scheduler's existing lease mechanism |
| Signals | Read through feature 039's signal store, so verification and detection see the same values |
| Learning | Effectiveness feeds `platform/memory/` and strategy synthesis; no parallel store |
| Locking | Per-resource advisory locks in Postgres for FR-021 |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| I — Evidence over assertion | "It worked" is the assertion most worth checking. | FR-002 measures it. FR-005 makes "could not tell" a distinct outcome, so the system never claims an effect it did not observe. |
| II — Bounded autonomy | Repetition is unbounded autonomy in slow motion. | FR-017 to FR-019 bound it: the fourth identical action raises a pattern and suppresses repetition. |
| III — Read-only by default | Rollback is a write triggered without a human. | Accepted deliberately and narrowly: automatic rollback is the *restoration* of the state the system itself changed, it is bounded to that, and it is audited. FR-010 stops everything when it fails. |
| VII — Learning is measured | Effectiveness is the measurement. | FR-016 routes it into the existing memory and strategy machinery, where the ablation switches already exist to prove it helps. |
| XII — Test-first | Restart-durability is the property most likely to be assumed. | SC-005 is written first, with a real restart in the test. |

## Architecture decisions

**Verification is an obligation, not a wait.** The naive implementation sleeps
inside the run. That holds a run open past its wall-clock ceiling, loses the
verification when the process restarts, and makes the settle period compete with
the investigation's own budget. Instead the executor writes a durable obligation
with a due time, the run ends, and a claimant picks it up. This is the same shape
as the scheduler, and it reuses the same claiming.

**Inconclusive is a first-class outcome.** The single most damaging simplification
available here is treating "the signal did not clearly get worse" as success.
That produces a system with a high reported success rate and an operator who
stops believing it. Five outcomes, and `inconclusive` is the honest one.

**Automatic rollback is narrow.** It fires on `worsened` only — not on
`ineffective`, and not on `inconclusive`. An action that did nothing is left in
place and escalated; undoing it would be a second unattended write with no
evidence it helps. An action that made things worse is undone, because the state
it replaced is known to have been better.

**A failed rollback stops autonomy on that resource.** At that point the system
has changed something, failed to undo it, and does not know what state the
resource is in. Continuing to act on it autonomously is the worst available
option. Suspension is per resource, visible, and cleared by a human.

**Recurrence is a different noun.** Four incidents about the same container
filling up is not four problems; it is one problem and four symptoms. A
recurring-problem item names the pattern and is closed by a change — more disk, a
log rotation, a fixed leak — not by a fifth restart. Making it a distinct object
is what stops the system from being an efficient way to avoid fixing anything.

**Effectiveness feeds the existing memory.** The first wave already has episodic
memory, strategy synthesis, anti-patterns and ablation switches to prove learning
helps. A separate effectiveness store would be a second learning system whose
contribution nobody measures.

## Phases

1. **Verification declaration.** Signals and settle period on every remediation
   capability; the unverifiable case; a coverage sweep over existing capabilities.
2. **Obligations.** Durable verification rows, lease-based claiming, restart
   survival, the five outcomes, before-and-after value capture.
3. **Rollback.** Automatic rollback on `worsened`, rollback verification, failed
   rollback escalation and per-resource suspension, the no-longer-possible case,
   kill-switch consistency.
4. **Effectiveness.** Recording per resource, capability and condition; the query
   surface; availability to a proposal; routing into episodic memory and strategy
   synthesis.
5. **Recurrence.** Windowed counting per resource and capability, restart-durable;
   the recurring-problem item; suppression of autonomous repetition; clearing.
6. **Concurrency.** Per-resource serialisation; the declared behaviour for the
   second arrival; the absent-resource and moved-on-world cases.
7. **Surfaces.** Timeline entries, audit chain, gateway endpoints, CLI, and the
   console's "awaiting verification" state and effectiveness history.

## Risks

- **A signal that recovers for unrelated reasons is credited to the action.**
  Partly unavoidable; mitigated by recording the raw before-and-after values and
  the settle period alongside the verdict, so a human can disagree with the
  attribution, and by feeding effectiveness into memory where a wrong attribution
  is eventually contradicted by the aggregate.
- **Settle periods make the loop feel slow.** Accepted. A fast wrong answer about
  whether a remediation worked is the thing this feature exists to prevent.
- **Recurrence windows are hard to tune.** Mitigated by making the count and the
  window configurable per capability through the config service, and by raising a
  pattern rather than blocking, so a badly tuned window is visible before it is
  obstructive.
