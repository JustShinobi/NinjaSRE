# Deviations — 040 Autonomy Policy Engine

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 1. Budgets are counted from the audit trail, not from a table of their own

**Planned.** The technical context says "Kill switch and freeze in
`platform/trust_controls.py`'s existing shape; **budgets in Postgres**".

**Done.** Budgets are in Postgres — in the *audit* table.
`platform/autonomy/budget.py` declares a `SpendLedger` protocol with two
implementations: `InMemorySpendLedger`, which is the whole ledger for a
deployment with no persistence configured and says so, and `AuditSpendLedger`,
which appends one immutable row per spend (`autonomy.budget_spend`, keyed by the
budget and what it counts against) and reads the count back through
`AuditRepository.query`. There is no sixteenth repository port.

**Why.** Three reasons, in order of weight.

The audit trail already has every property a budget needs and none of the ones a
new table would have to earn: it is append-only, tenant-scoped, exempt from the
retention sweep, and already the record of every decision this package makes. A
budget derived from that record *is* the record; a second bookkeeping table is a
second thing that can disagree with it, and the disagreement would only ever be
discovered during an argument about what the system did.

`platform/persistence/ports/__init__.py` is the whole export surface of the
storage layer and
`tests/unit/platform/persistence/test_port_conformance.py` asserts the port
count deliberately — feature 039's own deviations note that "a fourteenth is a
specification change, not a refactor". Two of those in consecutive features, the
second one for a counter, is the wrong ratio.

The requirement the port would have existed for is T-020: *a budget interval
spanning a deployment restart*. That is proven —
`test_a_budget_interval_survives_the_process_that_was_counting` spends a budget
through one gate, discards it, builds a second gate over the same storage, and
asserts the third action is refused.

**What this costs.** The count is bounded by `MAX_AUTONOMY_BUDGET_ROWS` (100),
because `AuditRepository.query` takes a page size rather than a cursor. A budget
is spent long before a hundred rows, so the bound only ever caps what asking
costs — but a budget configured with a limit above a hundred would read as
unspent forever. Nothing enforces that today beyond the constant's own comment.

---

## 2. `MAX_AUTONOMY_PREVIEW_ACTIONS` is 200, not the 500 the first pass chose

Found by a route test, not by reading: `AuditRepository.query` raises
`BoundExceeded` above `MAX_QUERY_PAGE_SIZE` (200) rather than returning a
quietly shortened answer, so a preview asking for 500 failed with a 400 instead
of replaying a week.

The bound is now the storage layer's, and the constant says why. This is the
right way round: a preview that silently replayed half the history would be the
worst possible failure of this feature — reassuring, and wrong.

---

## 3. The autonomy engine does not import the existing kill switch; it depends on
   its *shape*

**Planned.** The plan says the kill switch lives "in
`platform/trust_controls.py`'s existing shape".

**Done.** `platform/autonomy/bounds.py` declares an `EmergencyStop` protocol
with `is_engaged` and `describe_for`, and
`platform.remediation.autonomy.kill_switch.KillSwitch` satisfies it
structurally. `describe_for` was added to that class — six lines, additive, with
its reason in its own docstring.

**Why.** `platform/remediation/gating.py` imports `platform.autonomy`, so
`platform.autonomy` importing `platform.remediation` would be a cycle through
two packages whose `__init__` modules both re-export widely. The alternative —
a second kill switch inside `platform/autonomy/` — is worse than a cycle: the
module's own docstring says a cached or duplicated switch "is a kill switch that
does not stop the next write", and a deployment with two switches is a
deployment where an operator engages one of them during the ten seconds in
which it matters.

Structural typing is what this repository already uses for exactly this seam —
`core/capability/types.py` says so at length — and it has the side benefit that
the bounds suite can supply a stop that is simply on, without a deployment.

---

## 4. When a policy engine is wired, the autonomous allow-list is not consulted

**Not in the plan either way.** Feature 017 shipped `ConditionEvaluator`, an
allow-list that can grant autonomy on its own. This feature adds a second
mechanism that can do the same thing.

**Done.** `RemediationGate.decide` consults the policy engine when one is
present and the allow-list when one is not. They are never both consulted.

**Why.** FR-020 asks for *exactly one* path from a proposed action to execution.
Two mechanisms that can each grant autonomy is not one path — it is a posture
nobody chose, arrived at by union, and the union of two reasonable relaxations
is the failure mode the allow-list's own docstring warns about for conditions.
Making the engine a *ceiling* over the allow-list was considered and rejected
for the mirror-image reason: an engine that said "act" and an allow-list with no
entry would then refuse, which would make the policy engine unable to grant
autonomy at all in the deployment that has not configured an allow-list.

The allow-list stays because a deployment mid-migration still has one, and
`test_a_gate_with_no_policy_engine_still_behaves_as_it_did` holds that path.

---

## 5. "Propose" is implemented as an approval request

**Planned.** Acceptance scenario 3: at `propose_only`, "nothing is executed and
a proposal is recorded with the exact operation a human could run".

**Done.** The engine returns `Outcome.PROPOSE`; the remediation gate implements
it by queuing an approval through feature 015's machinery, carrying the
resolution's explanation into the reason the model and the reviewer both read.
`ProposedAction.operation` carries the runnable operation and is on the approval
payload, the audit detail and the API response.

**Why.** A separate proposal store would be a second review queue beside the one
feature 015 owns, and an operator would have two places to look for "things
waiting on me". The spec's own out-of-scope list says the approval mechanism is
015's; using it is what that means. What a proposal *is* in this deployment is
an approval request with the operation on it.

---

## 6. Risk classes are declared on `ToolMetadata`, and reads are exempt

**Planned.** T-002: "Risk declaration on the capability; validation at
registration with a named error."

**Done.** `ToolMetadata.risk_class`, required of everything above
`read_sensitive` and refused at construction when it is missing or is not one of
the five. A value that is not a class is refused whatever the level, so a typo
on a read tool is caught the day it is written rather than the day somebody
raises that tool's level.

**A read tool is not required to declare one.** Nothing that cannot change
anything reaches the resolver, and requiring the field on two hundred read tools
would teach authors to fill it in without thinking — which is exactly how the
field on the tool that mattered ends up wrong. `risk_class_of("")` still answers
`critical`, so the fail-safe holds for anything that does reach the resolver.

**Twenty-three first-party tools were classified**, each with a comment giving
the three answers the scale is defined by. Bridged protocol tools are classified
`critical` explicitly in `capabilities/protocols/catalogue.py`, beside the
existing `DEFAULT_SIDE_EFFECT_LEVEL`, for the reason that module already gives:
a server nobody here controls declares nothing we would act on.

---

## 7. Policy lives under `policies.autonomy`, not in a seventh configuration
   section

Same decision feature 039 made for detectors, for the same reason:
`platform/config_service/schema/root.py` says six sections and says why, and
whether this team may act unattended is the same kind of decision as whether its
runs may write to memory.

The section validates at save time using the same closed sets
`platform.autonomy` builds its enums over — the scope kinds, the levels, the
risk classes, the budget counters, the timezone, the instant. `PolicySet` also
validates, because a document can arrive from an import as well as from a write;
the two agree because both read `config/constants/autonomy.py`.

---

## 8. Labels are a list of name/value pairs in configuration and a mapping
   everywhere else

`AutonomyScopeSettings.labels` is `tuple[AutonomyLabelSettings, ...]`, following
`CustomMaskingPattern`. A section with operator-chosen keys is not a closed
schema — `extra="forbid"` is what makes configuration a typed surface — and the
console cannot render a form for a shape nobody declared.

`platform/autonomy/configuration.py` is the one place the two shapes meet, in
both directions, and `test_a_reviewed_document_can_be_imported_as_a_configuration_write`
drives the round trip through the real service.

---

## 9. Two audit rows per permitted action, not one

An autonomy decision writes `autonomy.decision`. A permitted action *also*
writes one `autonomy.budget_spend` per budget it spends (§1). Refusals write
only the decision row.

Worth recording because it looks like duplication and is not: the decision row
is the explanation, keyed by the action; the spend rows are the ledger, keyed by
the budget. A query for "what did the policy engine decide" filters on the first
and is unaffected by the second.

---

## 10. The decision's audit detail carries the whole action

`AUTONOMY_DETAIL_ACTION` holds `ProposedAction.to_record()`, not only the
capability and the resource identifiers.

**Why.** A policy change is previewed by *re-deciding* the recorded actions
(FR-018), and a record that kept only identifiers could not answer a rule that
selects on a label or a resource kind — the preview would report no difference
where there is one. That is the specific way this feature could be reassuring
and wrong, so the record carries what a re-decision needs.

---

## 11. The console renders the rules and the bounds; it does not badge a
   resource or a proposal

**Planned.** T-034: "Console: resolved level and explanation shown on the
resource and on every proposal before it is acted on."

**Done.** `console/src/surfaces/screens/autonomy.tsx` now reads the real
`/v1/autonomy/policy/{node_id}` and `.../bounds` and renders the rules table in
resolution order, the dry-run notice, and the freezes, budgets and overrides
beside them. The permanent propose-only footer is unchanged. Two console
endpoints, two fixtures per scenario, and the visual baseline were re-accepted —
the acceptance record for `06-screen-autonomy.png` said in as many words that
"the rules table is the policy engine's data and arrives with it", and this is
it arriving.

**Not done.** The resolved level is not shown on the *resource* screen, and the
proposal card's `proposal.autonomy` field is not filled from the resolver.

**Why.** Both need a resolution per rendered row — the resource screen renders a
list, and a badge per row is a request per row unless the API grows a bulk
resolve. Inventing that endpoint inside a feature whose gateway surface is
already nine routes, and then designing a per-row badge against a console with
committed visual baselines and an acceptance record per screen, is two decisions
that belong to whoever owns the resource screen. The engine half is done and is
one call: `AutonomyService.explain` answers exactly this, and
`POST /v1/autonomy/policy/{node_id}/explain` serves it.

**What this means for the definition of done.** FR-023 is satisfied for the
autonomy screen and not for the resource or the proposal. That is a real gap and
it is deliberate — the same disposition, and for the same reason, as feature
039's §8.

---

## 12. Budget exhaustion raises through a listener protocol, not an incident

**Planned.** T-021: "Budget exhaustion downgrades to approval and raises its own
attention item."

**Done.** `AutonomyGate.exhaustion` is an optional `ExhaustionListener`, called
on the first decision a spent budget refuses, and a warning log line that is not
optional.

**Why.** Raising an incident would give `platform/autonomy/` a dependency on
`platform/incidents/`, and which surface a deployment wants told is its own
decision — the same shape, and the same reasoning, as
`platform/remediation/audit.py`'s `TeamNotifier`. What this package guarantees
is that something is told and that it is told with everything needed to act.

The moment chosen is the *first refusal*, not the spend that used the last of
it: the action that spent the last unit looked like every other successful
action at the time, and the fact worth telling somebody is that the deployment
has now stopped doing what it was configured to do.

---

## 13. Test-first, per module rather than per phase

Followed for the reason features 020 and 021 give: a suite written against
modules that do not exist can only fail on `ImportError`, which proves nothing
about the behaviour it describes.

Each module's tests were written first and confirmed failing for the right
reason. The two worth naming:

- **T-003/T-004.** `tests/contract/autonomy/test_risk_classification.py` was red
  across twenty-three parametrisations against the real discovered catalogue
  before `ToolMetadata.risk_class` existed, and against two constructions that
  should have been refused and were not.
- **T-028.** `tests/architecture/test_one_path_to_execution.py` was written
  before the resolver was wired to anything and was red on exactly the two
  assertions it was written for — the gate did not import `platform.autonomy`
  and `decide` did not consult it. It also carries two tests of *itself*: one
  showing it recognises a direct executor call, one showing it ignores something
  that merely shares the name, because a structural check nobody has shown a
  failure to is one that passes vacuously.

---

## 14. Two test modules renamed for a basename collision

`tests/unit/platform/autonomy/test_preview.py` collides with
`tests/unit/platform/config_service/test_preview.py`. pytest imports test
modules by basename, so it broke collection of the whole suite while passing in
isolation — the same failure feature 039 recorded in its §11.

Renamed to `test_policy_preview.py`.

---

## Not deviations, recorded because they look like they might be

- **`platform/autonomy/` is a new package under `platform/`, not a top-level
  one.** The plan says "tier 3, beside `platform/remediation/`", and that is
  where it is. No `.importlinter` change was needed, because tier 3's contracts
  are per-package rather than per-module.

- **A tie between two rules at the same specificity resolves to the *less
  permissive*, then by rule identifier.** FR-007 asks only for determinism.
  Last-declared-wins would also be deterministic and would mean an operator
  could grant autonomy by reordering a merged document, which is not a thing
  anybody should be able to do by accident.

- **`resolve` is pure and `evaluate_bounds` is pure; only the budget read is
  not.** The ledger is passed already-read into `evaluate_bounds`, which is what
  makes the whole ordering — stop, freeze, budget, rollback — exhaustively
  testable without storage, and what makes NFR-002 true of the resolver rather
  than nearly true.

- **The `why` command asks about a hypothetical rather than about a past
  decision.** An operator whose deployment did nothing wants to know why *this*
  action would be refused, which is a question about now. Past decisions are
  already in the audit trail with their full explanation, which is what SC-008
  is for.

- **`docs/capabilities.md` and the four `docs/site/capabilities/` pages
  changed.** Generated, not edited: the risk class is metadata the approval gate
  reads, so the reference shows it. `make check-docs` is green.

- **`docs/provenance-map.md` was not touched.** Gitignored per `CLAUDE.md`;
  editing the local copy changes nothing that ships. Same disposition as
  features 020 §6 and 021 §5.
