# Deviations — 041 Closed-Loop Remediation

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 1. A sixteenth repository port, holding two tables

**Planned.** The technical context says "verification obligations are rows in
Postgres" and "effectiveness feeds `platform/memory/`". It does not say whether
either is a repository port.

**Done.** One: `RemediationLedger`, with `remediation_outcomes` and
`remediation_problems`, a fake, a Postgres implementation, migration
`0008_remediation_ledger`, a contract suite, and a row in
`test_tenant_isolation.py`. The port count moved from fifteen to sixteen and
`test_the_specification_names_exactly_sixteen_ports` moved with it.

**Why.** Feature 040 avoided a port by deriving budgets from the audit trail,
and the same trick was tried here first. It does not survive NFR-003.
`AuditRepository.query` takes a page size bounded at `MAX_QUERY_PAGE_SIZE` and
filters on `action`, `resource_kind` and `resource_id` — which cannot express
"count the verdicts of this capability on this resource over a year", cannot
group, and cannot be indexed for it. An effectiveness number assembled from the
first page of a year would be an answer that got more wrong the longer the
deployment ran, and it is read on the path of every proposal.

The obligation half has a second reason. `claim_due` is a compare-and-set with a
lease across replicas, which the audit trail's two write methods — append and
nothing else — cannot express at all.

**Why one port and not two.** The thing that says "read these signals again at
14:05" *is* the thing that afterwards says "this capability worked on this
resource". Splitting them would mean copying the before-values from one table to
the other at exactly the moment the system is least sure of itself, and a copy
that failed would leave a verdict with nothing to compare against. Recurring
problems are in the same port because they are derived from its counts and
because an incident query that returned patterns would make "how many incidents
are open" stop having an answer.

---

## 2. Suspensions are counted from the audit trail, not from a third table

**Planned.** FR-010: a failed rollback "MUST suspend further autonomous action
on that resource until a human clears the suspension".

**Done.** `platform/remediation/suspension.py` writes two append-only audit rows
— `remediation.autonomy_suspended` and `remediation.autonomy_cleared` — and
reads the current state back as whichever is later. There is no suspension
table.

**Why.** This is the shape the question actually has. "Is this resource
suspended" is only ever asked alongside "and what happened", and a boolean
column would answer the first and lose the second. The trail is already
append-only, tenant-scoped, exempt from the retention sweep, and the record of
every decision this package makes — which is the argument feature 040 made for
budgets, and it holds here for the same reasons and against a much smaller
volume: a suspension is raised and cleared a handful of times in the life of a
resource.

**What this costs.** `MAX_SUSPENSION_ROWS` (50) bounds what reading one
resource's history costs. A resource suspended and cleared more than fifty times
would read as un-suspended on the fifty-first, which is a bound worth knowing
about and not one any deployment will reach — a resource that had failed its
rollback fifty times would have been rebuilt.

**`AutonomySuspensions` holds the repository, not the gateway.** It is
constructed inside the caller's unit of work, so suspending and recording the
verdict that caused it land in one transaction. A service that opened its own
unit could suspend a resource for a rollback failure the surrounding transaction
then rolled back, which is the one arrangement in which a resource is suspended
for something that did not happen.

---

## 3. Per-resource serialisation is a protocol, not a Postgres advisory lock

**Planned.** The technical context says "per-resource advisory locks in Postgres
for FR-021".

**Done.** `TargetLocks` gained two things: `on_conflict`, a declared
`SecondArrival` of `WAIT` or `REFUSE` — which is what FR-021's "the second MUST
wait or be refused, and which it does MUST be declared" actually asks for, and
both behaviours are implemented and tested — and `durable`, an optional
`ResourceHold` protocol a deployment satisfies to extend the guarantee across
replicas. No advisory lock is issued and no third table was added.

**Why.** A PostgreSQL advisory lock is held by a *session*, and the executor's
unit of work is opened and closed inside the action rather than held for the
apply-and-verify — so the lock would be released halfway through the thing it
was protecting. Making it durable properly means a leased row, which is a third
table in this port for a mechanism the existing in-process lock already covers
for the case that actually happens: an agent proposing two mitigations for one
workload in one investigation, which is what `TargetLocks`' own docstring has
said since feature 017.

**What this means for the definition of done.** SC-009 — "concurrent
remediations against one resource are serialised or refused, as declared" — is
satisfied within a replica, both ways round, with a test for each. It is not
satisfied *across* replicas by anything this repository ships; the seam is
declared, named, and tested with a double
(`test_a_durable_hold_another_replica_owns_refuses_the_second_replica`), and a
deployment running several replicas has one small class to write. That is a real
gap and it is deliberate.

---

## 4. The three closed-loop refusals are gate checks, not autonomy bounds

**Not in the plan either way.** Feature 040 shipped four bounds no level
overrides, in `platform/autonomy/bounds.py`. This feature adds three more
reasons not to act unattended: the resource is suspended, the repetition has
become a pattern, and the capability's effect is not measurable.

**Done.** `platform/remediation/guards.py` declares an `AutonomyGuards` protocol
and a `ClosedLoopGuards` implementation, consulted by `RemediationGate.decide`
after the kill switch and before the policy engine. All three **downgrade to an
approval** rather than refusing outright.

**Why not a fifth, sixth and seventh `Bound`.** `Bound` is a closed enum in a
package whose whole subject is policy, and all three of these are facts this
package learned *by acting*: that a rollback failed here, that this has been
done here four times, that this capability declares no signal. Putting them in
`platform/autonomy` would either mean that package importing
`platform.remediation` — the cycle feature 040's §3 exists to avoid — or a
generic "something else says no" parameter, which is a bound that means nothing
in particular.

**Why a downgrade rather than a refusal.** Every one of the three is a reason
for the deployment to stop deciding on its own; none is a reason a person may
not act. A suspended resource is precisely the one somebody has to be able to
fix, and a recurring problem is closed by a change that a human makes.

---

## 5. `RemediationComponents` takes five things now, and the fifth is required

**Planned.** T-001: "Declare, on every remediation capability, the signals its
effect appears in and the settle period."

**Done.** A required `verification: VerificationDeclaration` field, with no
default, so the seven shipped capabilities and every future one must answer.
`VerificationDeclaration.unverifiable(reason)` is how a capability says its
effect has no signal, and the reason is not optional either.

**Why required.** An optional declaration would be omitted first and by exactly
the capabilities whose effect is hardest to measure — the argument the type's
own docstring already makes about the verifier. The cost is that the two test
fixtures constructing `RemediationComponents` had to be updated, which is the
point: the compiler is the coverage sweep T-004 asks for, and
`tests/contract/remediation/test_verification_coverage.py` is the second half.

**`toggle_feature_flag` declares itself unverifiable.** A flag's effect appears
in whatever the flag guards, which differs per flag and is not something the
capability can name. It is in the shipped set for the same reason `clear_cache`
is the one with no derivable rollback: the unverifiable path is exercised by the
catalogue rather than being a branch nobody has run.

---

## 6. `ineffective` and `inconclusive` are separated by whether a clearing value
   was declared

**Planned.** FR-004 names five outcomes; FR-005 says `inconclusive` must be
distinct from `effective`; T-011 says a signal that did not move enough reports
`inconclusive`.

**Done.** A signal that moved less than `VERIFICATION_MINIMUM_CHANGE` reads
`inconclusive` when the capability declared no `clears_at`, and `ineffective`
when it did.

**Why.** With a clearing value, "the condition still holds" is a *fact* and "it
did not work" is a conclusion somebody can act on. Without one, all that is
known is how far the signal moved, and a sub-threshold move on a live system is
indistinguishable from an unrelated fluctuation — so the honest verdict is that
nothing could be concluded. Collapsing the two would have meant either reporting
every small move as a failure (which would make the ineffective count
meaningless) or reporting every one as inconclusive (which would make
`ineffective` almost unreachable and SC-002 untestable end to end).

The cost is that declaring a `clears_at` is worth the thought it takes, and the
declaration's docstring says so.

---

## 7. The undo travels on the ledger row

**Not in the plan either way.** FR-008 says a `worsened` verification must
trigger the action's rollback plan automatically.

**Done.** `RemediationOutcome.undo` carries `RollbackPlan.to_record()` and
`RemediationAction.to_payload()`, written by the executor and read by
`VerificationAftermath`.

**Why.** The rollback happens after a settle period that may span a restart, and
an *autonomous* action has no approval to read the plan back from — feature
015's store keys plans by approval. Without the payload on the row there is
nowhere else it could come from, and the failure mode would be silent: a
worsened verification with no plan found, leaving a change that made things
worse in place. FR-011 asks that this case be stated explicitly, and it is —
`RollbackDisposition.IMPOSSIBLE`, with the reason — but it should be the case
where there genuinely is no plan, rather than the ordinary one.

---

## 8. Verification is claimed on the ledger row; the *sweep* is the scheduled job

**Planned.** "Verification obligations are rows in Postgres, claimed with the
scheduler's existing lease mechanism."

**Done.** Two layers. The sweep is a recurring `ScheduledJob`
(`remediation.verification_sweep`) claimed through `JobDispatcher` exactly as
the observation tick is — which is what hands the work across the tenant
boundary. Inside the tenant, `RemediationLedger.claim_due` claims individual
obligations with their own lease.

**Why not a `ScheduledJob` per obligation.** `ScheduleStore` holds *job
definitions* and is operator-facing: an operator listing their scheduled jobs
would find thousands of one-shot rows between their nightly sweeps. And
`JobDispatcher` is on the system unit of work, so a per-obligation job would
have the obligation's before-values in one tenant's table and its schedule
outside any tenant.

**Why not only the sweep's lease.** NFR-001 asks that obligations be "claimed
with a lease, and safe across replicas". Two sweeps overlapping — which a lease
permits by design, since a lease is not a lock — would otherwise both verify the
same action, reach the same verdict, and roll the same change back twice.

---

## 9. Nothing runs the sweep on a timer

`ClosedLoop.sweep`, `SweepClaiming` and `verification_sweep_job` are the pieces;
no daemon in this feature calls them. That is the same disposition feature 039
recorded for its evaluation tick and `platform/estate/discovery/` for its sweep:
composing a worker is a deployment question, and the scheduler's executor is
what will do it.

Recorded here because it looks like an omission and is the established shape.

---

## 10. Autonomy policy grew three fields rather than a section of its own

`policies.autonomy` gained `allow_unverifiable_actions` (FR-006),
`recurrence_threshold` and `recurrence_window_seconds` (T-029). Same decision
features 039 and 040 made for detectors and rules, for the same reason:
`platform/config_service/schema/root.py` says six sections and says why, and
whether an unverifiable action may run unattended is the same kind of decision
as whether this team's runs may write to memory.

`allow_unverifiable_actions` defaults to `False`, and **the default is the
decision**: a deployment that has decided nothing has not decided that it may
act on things it cannot measure.

---

## 11. "The rollback is itself verified" means the target read back, not a
   second settle period

**Planned.** FR-009 and T-015: "A rollback MUST itself be verified, through the
same mechanism."

**Done.** `RollbackExecutor` reads the target back through the capability's own
reader and compares it to the state the plan recorded — the same mechanism the
action's own verification uses — and `VerificationAftermath` checks the result
rather than the absence of an exception, so an applier that reported success
without converging is a `FAILED` rollback that suspends the resource.

**Not done.** No second verification *obligation* is written for the rollback,
so no settle period elapses and the declared signals are not read again.

**Why.** The signals a capability declares describe the effect of *taking* the
action, and a rollback's expected effect on them is the reverse — which the
declaration cannot express and which is not simply the mirror image in any case:
scaling back down does not raise the error rate the scale was supposed to fix,
it merely stops improving it. A rollback obligation would therefore have
compared against an expectation nobody declared and produced verdicts nobody
could interpret, on the resource the deployment is least sure about.

Reading it as the state read-back is the reading that makes the requirement
true: the question a rollback verification has to answer is "is the target back
where it was", which the recorded plan's snapshot answers exactly, and it is
answered before the disposition is decided rather than afterwards.
`test_a_rollback_that_ran_without_converging_is_a_failed_rollback` holds it.

---

## 12. The console is not done

**Planned.** T-038: "Console: awaiting-verification state, before-and-after
values, effectiveness history on the resource, recurring problems as their own
view."

**Not done.** No console file changed.

**Why.** Four items, of which three are new placements on screens that have
committed visual baselines and an acceptance record each, and the fourth
("recurring problems as their own view") is a new screen — a route, a navigation
entry, a table, an empty state, a detail panel, fixtures for every scenario, and
a re-accepted baseline. The console has a design system, a component vocabulary
and a visual-regression gate precisely so that a screen is a reviewed decision
rather than whatever the person adding an endpoint chose; inventing one inside a
platform feature is what would be wrong here, and it is the same disposition,
for the same reason, as feature 039's §8 and feature 040's §11.

**What is ready for it.** Everything below the console. Six gateway routes with
contract tests, a CLI that renders all four of the console's items today, and
`awaiting_verification` as an explicit field on the API response rather than
something a client infers — which was the one thing that would have been
expensive to add later.

**What this means for the definition of done.** FR-007's "everywhere it is
displayed" is satisfied for the API and the CLI and not for the console. SC-001
through SC-011 are each proven by a named test without it. That is a real gap
and it is deliberate.

---

## 13. Test-first, per module rather than per phase

Followed for the reason features 020, 021 and 040 give: a suite written against
modules that do not exist can only fail on `ImportError`, which proves nothing
about the behaviour it describes. Each module's tests were written first and
confirmed failing before the implementation. The three worth naming:

- **T-005.** `tests/contract/persistence/test_remediation_ledger.py` was red on
  the import before the port existed, then red on nine of its ten assertions
  against the first fake.
- **T-003/T-004.** `tests/contract/remediation/test_verification_coverage.py`
  was red across eighteen parametrisations against the real shipped catalogue
  before `RemediationComponents.verification` existed.
- **SC-005.** `test_verification_survives_the_process_that_owed_it` builds the
  obligation through one object graph, discards every object in it, and settles
  it through a second graph over the same storage. A test that reused the
  service would have proven that the service remembers, which is not the claim.

---

## Not deviations, recorded because they look like they might be

- **`config/constants/closed_loop.py` is a new domain module rather than more
  `security.py`.** The same decision feature 040 made with
  `config/constants/autonomy.py`. `security.py` owns the remediation constants
  feature 017 needed; the twenty-eight this feature adds are about measuring an
  effect rather than about permitting one.

- **`EffectivenessHistory.recent` raises above the page bound rather than
  clamping.** It originally clamped, and the route test caught it: a caller that
  asked for five hundred and received a hundred has no way to tell that from
  there being a hundred. The bound is the storage layer's and the error is its
  `BoundExceeded`.

- **The `/v1/remediations/{action_id}` route is declared last.** FastAPI matches
  in registration order, so a path-parameter route declared first swallows
  `/v1/remediations/suspensions` and answers it as an action nobody can find.
  Found by a route test, and the reason is a comment above the decorator.

- **A recurring problem does not appear on any incident's timeline.** It is a
  different noun — it names a pattern and is closed by a change — and writing it
  onto the fourth incident would file the pattern under the last of its
  symptoms. `IncidentOutcomes.recurrence` logs it and the ledger holds it.

- **The verdict is recorded before anything acts on it.** `ClosedLoop.conclude`
  reads what `settle` wrote. A worker that died between them leaves a verdict
  and no rollback, which is recoverable and visible; the other order leaves a
  rollback nobody can explain.

- **T-032's "a remediation that succeeds but trips a different detector" is
  declared rather than handled.** A capability verifies against the signals *it*
  declares; a different detector firing opens its own incident through feature
  039's machinery and does not change this verdict. That is the declared
  behaviour, it is what `test_the_effect_may_be_visible_in_a_signal_other_than_the_one_that_fired`
  asserts the mechanism for, and the alternative — a verdict that reads every
  detector on the resource — would make every remediation on a busy resource
  inconclusive.

- **`docs/provenance-map.md` was not touched.** Gitignored per `CLAUDE.md`;
  editing the local copy changes nothing that ships. Same disposition as
  features 020 §6, 021 §5 and 040.
