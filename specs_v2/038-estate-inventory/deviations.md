# Deviations — 038 Estate Inventory and Health Model

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 0. Closed afterwards: the gate this record said had not been run

§17 below reported `make verify` green and, in the same breath, that
`make test-postgres` had **not** been run — on the grounds that it "needs Docker
and a database". That reason did not hold: Docker was available on the machine
the work was done on. A change under `platform/persistence/` was therefore
reported as finished against a rule this file quotes and did not meet, which is
worse than not knowing the rule.

`close-task` then failed for an unrelated reason (§0.2), so the branch never
merged, and the unmet gate would have gone in with it.

**0.1 — `make test-postgres` is green.** 386 passed, 12 skipped, no failures, in
6m22s, including 45 estate assertions against a real PostgreSQL. Migration
`0005_estate`, the partial unique index in §6, the JSONB round trip and the
tenant isolation in `test_tenant_isolation.py` all hold against the database
rather than against the fakes. Nothing was hiding; the point is that nobody knew
that when the task was reported done.

**0.2 — the estate summary at size was measured against nothing real.**
`tests/benchmarks/test_estate_scale.py` says of itself that it is "a floor rather
than a ceiling: the same shapes over PostgreSQL are what `make test-postgres`
measures". That was not true — no estate scale or budget test existed under
`tests/contract/persistence/`, so SC-006 and NFR-001 were proven only against a
dictionary walk. It matters for this summary in particular:
`PostgresEstateRepository.summarise` selects every row and hydrates each into a
`Resource` in Python, which is work that scales with the estate and does not
exist in the fake.

`tests/contract/persistence/test_scale.py` now measures it where it is real: ten
thousand rows seeded in bulk, the summary and a filtered query timed against
`ESTATE_SUMMARY_BUDGET_SECONDS`, with the counts asserted so a fast wrong answer
fails rather than passing as a performance result. **0.43s against a 1.0s
budget** — the hydration in Python dominates, so the real store costs about what
the fake does (0.39s), which is the design decision in `summarise` turning out to
be sound. The benchmark's docstring now points here instead of at a gate that did
not measure it.

It went into the existing `test_scale.py` rather than a file of its own, for the
reason §16 records and which caught this work too: a new
`tests/contract/persistence/test_estate_scale.py` collides on basename with
`tests/benchmarks/test_estate_scale.py`, and the tree has no `__init__.py`, so
pytest imports one and refuses to collect the other. `test_scale.py` is already
"the claims that are only true at size, against the real store", already carries
the `postgres_only` fixture, and gains the estate as a third claim rather than a
duplicate of its own scaffolding.

**0.3 — the flake that actually failed `close-task` was not this feature's.**
`console/tests/e2e/budgets.spec.ts` read `performance.getEntriesByType('paint')`
once, immediately after `page.goto` — which resolves on `load`, while a paint
entry is queued only after the frame is presented. On the runs that lost that
race the list was empty, `?? Number.NaN` turned "not measured yet" into a budget
breach, and the gate failed reporting `/audit painted in NaNms`. Roughly one run
in thirty, on whichever route lost; `/approvals` lost it during the
investigation, which is what ruled out the route being at fault.

The test was written in 035 (`b267e36`) and had been passing by luck since. The
paint entry is now waited for, both budget tests share one helper, and an
unreported paint fails with its own message rather than as a slow render. 50
consecutive runs of `tools.console_e2e run --repeat 50` are green.

---

## 1. The estate health enum is `ResourceHealth`, not `HealthState`

**Planned.** FR-012 names "a health state from a declared, closed set".

**Done.** The enum is `ResourceHealth`.

**Why.** `platform/persistence/ports/health.py` already exports `HealthState` —
the *store's* health, as in "is Postgres reachable and are the migrations
current" — and `platform.persistence.ports` re-exports it. A second
`HealthState` in the same namespace would have been an import-order accident
waiting to happen, and the two mean entirely different things.

`ResourceHealth` is also the better name on its own: `ResourceHealth.DEGRADED`
says what it is about, and a caller holding both enums cannot confuse them.

---

## 2. A thirteenth repository port, and the prose that counted twelve

The plan's technical context says "a new repository port beside the twelve that
exist". That is what shipped, and it made a documented number wrong in eleven
places — `AGENTS.md`'s non-negotiables table, `platform/AGENTS.md`,
`platform/persistence/__init__.py`, `ports/__init__.py`, `ports/transaction.py`,
`fakes/__init__.py`, `fakes/gateway.py`, `fakes/state.py`,
`postgres/repositories/common.py`, and two test files.

All of them now say thirteen. The alternative — leaving them — would have made
the first contributor to count the ports distrust every other number in those
documents.

---

## 3. Estate history is a new `DataClass`, which is an extension of the existing
retention policy rather than a second one

**Planned.** FR-021: "History MUST be retained under the deployment's existing
retention policy, not a new one." T-031: "test nothing introduces a second
retention path."

**Done.** `DataClass.ESTATE_HISTORY` was added to the existing enumeration, with
a default window in `config/constants/estate.py`, swept by the existing
`RetentionSweeper.purge` in both backends.

**Why this is the requirement rather than a deviation from it.** The thing
FR-021 rules out is a *second mechanism* — an estate-specific cleaner with its
own schedule, its own configuration, and its own idea of how long is long
enough. What shipped is a row in the one enumeration the one sweeper iterates,
reached through the one system unit of work. `test_every_data_class_is_swept_by
_the_same_sweeper` asserts exactly that: every non-exempt class has a default
window, and `RetentionSweeper`'s entire public surface is still `purge` and
`purge_all`, so a class-specific delete would show up as a new method.

**Why the resources themselves are not swept.** An absent resource *is* the
record that something was removed. Deleting it would make the estate forget the
thing it was asked to remember, and "what used to be here" is a question asked
months after the deletion. What ages out is the history hanging off it —
transitions and the links to runs and incidents.

---

## 4. `mark_absent` gained a `since` boundary, and it is not cosmetic

**Not in the plan.** The port method is
`mark_absent(*, source, seen_ids, at, since=None)`.

**Why.** T-012 asks a sweep that exceeds its bound to suspend and resume. The
first implementation did, and the resumed pass then marked absent everything its
*own first pass* had ingested — because a resumption only holds the identifiers
of the pages it read. That is the exact failure the whole component exists to
prevent, arrived at from a direction neither the spec nor the task list names.

`since` is the instant the sweep *chain* began. A resource seen at or after it
is not gone, whichever pass saw it. It defaults to `None`, meaning `seen_ids`
alone decides, because that is the stricter reading and a caller that has not
thought about resumption should get the behaviour that cannot silently keep a
deleted resource.

The sweep record's `started_at` is likewise the chain's start rather than the
pass's, so one logical sweep is one row however many passes it takes.

`test_exceeding_the_resource_bound_suspends_and_resumes_at_the_cursor` is the
test that found this, and it is the one that holds it.

**And a second half, found by the ten-thousand-resource benchmark.** `since` is
measured against `last_seen_at`, and `last_seen_at` was originally taking the
*provider's* `observed_at`. A source whose clock runs even slightly behind the
deployment therefore had every resource it reported land before the chain began
— so the pass that completed decommissioned all five thousand the first pass had
ingested, at scale, in exactly the case the spec's "clock skew between the
deployment and the source" edge case names.

`last_seen_at` is now the sweep's own instant. It means "when this deployment
last saw it reported", which is a fact about us; the provider's reading time is
kept on the source contribution, where it belongs.
`test_a_source_whose_clock_runs_slow_is_not_decommissioned` holds both halves.

---

## 5. Reconciliation needs a correlation key, which nothing declared

**Planned.** FR-004 and SC-004: two sources describing one thing reconcile to one
resource with both attributed.

**Done.** `DiscoveredResource.correlation_key` and `Resource.correlation_key`,
with `EstateRepository.by_correlation_key`, an index, and reconciliation that
looks it up *before* deriving an identity of its own.

**Why it had to exist.** Identity is derived from the source plus that source's
own identifier — which is the right rule and which makes two sources of one
machine derive two different identities by construction. Something has to say
"these are the same thing", and the only honest something is a value both
sources report: a machine UUID, a serial number, a fully-qualified hostname.
Inferring it from a matching display name would reconcile two guests somebody
named `web` on different nodes, which is worse than not reconciling at all.

An empty correlation key never matches another empty one. The absence of a
correlator is not a correlator, and treating it as one would collapse every
uncorrelatable resource in the estate into a single record.

---

## 6. A reused provider identifier gets a generation suffix, and the unique index
is partial

**Planned.** The spec's edge cases name "a resource whose provider identity is
reused after deletion", and T-019 asks for "a new resource, not a resurrection
of the old one".

**Done.** `identity_for` walks generations: the derived key, then
`<key>~2`, `<key>~3`, up to `MAX_IDENTIFIER_GENERATIONS`, taking the first that
is free or not absent. `(org_id, source, native_id)` is unique **only among
present resources** — a partial index — so the retired row and its successor can
coexist.

**Why partial rather than total.** A total unique constraint would have made the
successor unwritable, and the only ways out are worse: delete the retired
resource (losing the history the spec says to retain), or reuse its row (giving
a brand-new machine somebody else's outage history, which is worse than a
duplicate because it looks correct).

---

## 7. The parent relationship carries no foreign key

**Not in the plan.** `estate_resources.parent_id` is an indexed column.

**Why.** A sweep enumerates a provider's inventory in whatever order the
provider returns it, so a guest routinely arrives before the node it runs on;
and a resource whose parent comes from a *different* integration has a parent
that will never exist from this source's point of view. A foreign key makes both
cases unwritable, and both are ordinary. The relationship is also an edge in the
knowledge graph, which is where "what does this affect" is answered.

---

## 8. Three new edge kinds and one new node kind in the topology graph

`NodeKind.RESOURCE`, and `EdgeKind.HOSTED_ON`, `BACKS_UP`, `REPLICATES_TO`.
FR-005 names depends-on, backs-up, replicates-to and hosted-on and says the
knowledge graph must be reused rather than a second graph introduced; three of
the four did not exist.

One `RESOURCE` node kind rather than one per resource kind, because resource
kinds are extensible by an integration and `NodeKind` is not — a traversal has to
keep working when a deployment connects a hypervisor nobody here has heard of.

`HOSTED_ON` is distinct from the existing `DEPLOYED_ON`: the latter is a service
on infrastructure a human declared, the former is what a sweep observed.

---

## 9. Discovery's protocol is defined in `platform/`, and `integrations/_base/`
is a doorway onto it

**Planned.** T-007: "Discovery protocol in `integrations/_base/`, with rate
limits and a read side-effect level declared."

**Done.** The protocol and its records are `platform/estate/discovery/port.py`.
`integrations/_base/discovery.py` re-exports every name and adds `declare`,
which fills in the side-effect level once instead of at eighty call sites.

**Why.** Tier 3 cannot import tier 2 and the sweep is tier 3, so a protocol
defined under `integrations/` could never be named by the thing that calls it.
The plan's own Constitution Check anticipates this — "on integrations only
through a protocol a composition root satisfies" — and this is that protocol.
An integration author still reads the contract at
`integrations/_base/discovery.py`, which is what the task was asking for.

---

## 10. The masking requirement applies to attributes and to nothing else

**Planned.** NFR-005: "A provider attribute that would carry a secret or a
personal identifier MUST pass through the existing masking rules before storage."

**Done.** `platform/estate/attributes.screened` runs every *string attribute
value* through the guardrail ruleset (which is where secret shapes are declared)
and then through the masking policy's detectors (which is where identifier
shapes are). Neither gains an estate-specific rule.

**What is deliberately not screened.** A resource's kind, source, native
identifier, display name and parent. Those are the estate's own structure: an
operator looking for `pve1` has to be able to find `pve1`, and a display name
replaced by a token is a resource nobody can search for. Attributes are the
free-form half — the half where a hypervisor cheerfully returns a guest's
cloud-init user data — and the requirement says "a provider *attribute*".

The mask mapping is thrown away rather than stored. It is the table that turns a
token back into the identifier, and keeping it beside the masked value in the
same database would make the masking decorative.

---

## 11. Two new permissions, and `estate.manage` sits with the responder

`Permission.ESTATE_READ` (viewer and up) and `Permission.ESTATE_MANAGE`
(responder and up). Neither was named by the plan; both are required by T-032's
"maintenance set and clear", because `gateway/http/security/route_permissions.py`
refuses a route with no permission and no written reason.

`estate.manage` is a responder's rather than an operator's on purpose. Putting a
machine into maintenance is what somebody does *while working on it during an
incident*, and waiting for an operator to do it is how an estate stays noisy
through every planned change.

---

## 12. The estate's mock-plane endpoints moved from projected to served, which
meant reshaping the fixtures

**Planned.** T-034: "Console estate panels from feature 036, against the real
endpoints."

**Done.** Rather more than the task's wording implies, because feature 032's
`tools/mockplane/endpoints.py` says what has to happen when this work lands:
"When that work lands, the projection is deleted rather than kept as a fallback:
a fallback is how two sources of truth start."

So:

- `/v1/estate/summary`, `/v1/estate/resources` and
  `/v1/estate/resources/{resource_id}` are `EndpointSource.GATEWAY` now. The
  three that arrive with Proxmox — `nodes`, `storage`, `backups` — stay
  projected, because feature 044 owns them.
- They came out of the console's `PROJECTED_PATHS`, which is a closed enumerated
  seam whose docstring says "the list shrinks".
- `tools/mockplane/capture/projection.py` gained `estate(reading)` beside
  `project(reading)`, and the three estate endpoints moved into it. That split
  is the point rather than a tidy-up: `project` is *only* for endpoints nothing
  serves, and `test_every_projection_answers_an_endpoint_the_gateway_does_not_serve`
  fails the moment it is not. Their records are `Provenance.GATEWAY` now, and
  they are built in the route's own shape field for field — a rendering of the
  cluster reading rather than a projection of it into something nothing answers.
  `tools/mockplane/dataset/scale.py` does the same for the ten-thousand-resource
  scenario. The fixtures were rebuilt and `python -m tools.mockplane verify`
  validates them against the regenerated OpenAPI document.
- `tools/mockplane/verify/coherence.py` reads `parent_name`, `health`, and
  `attributes.backed_up` — the endpoint's names — where it read the projection's.
- `fixtures/contract/openapi.json` and `console/src/api/schema.ts` were
  regenerated, so the console reads the estate through the *typed* client rather
  than through the untyped projected seam.
- Three screens changed field names accordingly: `resources`, `dashboard`, and
  `incident-detail`.

**One field was added to the API for the console's sake.**
`ResourceSummaryView.parent_name`, resolved by `EstateService.query` from the
page it just returned. The listing's parent column would otherwise show an
opaque identifier. It is resolved from within the page rather than by a lookup
per row, because a hundred-row page would otherwise be a hundred queries; a
parent outside the page shows nothing rather than an identifier.

**The per-guest utilisation columns now read `attributes`.** The core kinds
declare no fill percentage — a hypervisor integration declares a kind that does —
so the meter is present when an integration supplies one and absent otherwise.
That is the honest rendering: a deployment with nothing connected shows no
meter rather than a meter reading nought.

---

## 13. Structure — modules the plan's phases do not name

The plan lists seven phases and no file tree. What shipped:

| Module | Why |
|---|---|
| `platform/estate/kinds.py` | FR-002's registry. Not a module-level singleton: a test that registered a kind would otherwise change what every later test in the session sees, and the failure lands on whichever test ran next. |
| `platform/estate/identity.py` | FR-003's derivation. A rule rather than storage, so it is not in the port. |
| `platform/estate/attributes.py` | Typing and screening. Two jobs in one module because both are "what a provider sent, reduced to what may be stored". |
| `platform/estate/errors.py` | Five refusals, each a case where the wrong answer is worse than an error. |
| `platform/estate/health/{mapping,derive,rollup}.py` | FR-013 through FR-015. Split because a provider's vocabulary, a derivation, and an aggregation rule are three decisions with three different reviewers. |
| `platform/estate/discovery/{port,reconcile,sweep,schedule}.py` | The contract, what "is this the same thing" means, one pass, and how a pass becomes claimable work. |
| `platform/estate/service.py` | The one place freshness, rollup and maintenance are applied. A console that applied freshness itself and a CLI that did not would show two estates and both would be defensible. |

`platform/estate/` has no `AGENTS.md`: no sub-package of `platform/` has one,
and `platform/AGENTS.md` gained an "The estate, in one page" section instead.

---

## 14. Test-first sequencing, per module

Followed per module rather than per phase, for the reason features 020 and 021
give in their own records: a suite written against modules that do not exist can
only fail on `ImportError`, which proves nothing.

Each module's tests were written first and confirmed failing for the right
reason — the repository contract suite was red on a missing `EstateQuery` export
before the port existed, the kind and identity suite was red on
`No module named 'platform.estate'`, and the sweep suite was red on a missing
`sweep` module. Two of them then failed *again* for a real reason after the
implementation landed, which is the part that made them worth writing: the
resumed-sweep absence bug in §4, and a maintenance assertion that was measuring
freshness rather than the window.

---

## 15. The definition of done, item by item

Recorded here because "each proven by a named test" is only checkable if the
names are written down.

| Criterion | The test that proves it |
|---|---|
| SC-001 — twice against an unchanged source: no duplicates, no spurious transitions | `test_sweeping_twice_against_an_unchanged_source_changes_nothing`, and `test_recording_the_same_state_twice_appends_one_transition` in the repository contract suite |
| SC-002 — a renamed resource updates rather than duplicating | `test_a_rename_updates_rather_than_duplicating` |
| SC-003 — a failed sweep marks nothing absent; a successful one marks the gone resource absent and retains its history | `test_a_failed_sweep_marks_stale_and_nothing_absent`, `test_a_complete_full_sweep_marks_the_gone_resource_absent`, and `test_a_successful_sweep_marks_the_gone_resource_absent_and_keeps_its_history` |
| SC-004 — two sources describing one thing reconcile to one resource with both attributed | `test_two_sources_describing_one_machine_reconcile_to_one_resource` |
| SC-005 — every health state on every kind is explainable | `test_every_state_on_every_kind_is_explainable`, which walks the whole closed set against every declared kind |
| SC-006 — a ten-thousand-resource summary answers within budget | `test_a_ten_thousand_resource_summary_answers_within_budget`, with `test_the_estate_really_holds_ten_thousand_resources` beside it so the budget is not met by an empty store |
| SC-007 — two replicas running discovery concurrently converge to one result | `test_two_replicas_sweeping_concurrently_converge_to_one_result` and `test_two_replicas_both_concluding_an_absence_record_it_once` for the convergence, `test_one_due_sweep_is_claimed_by_exactly_one_of_two_replicas` for the claiming |
| SC-008 — a resource in maintenance is excluded from problem counts and included in the estate | `test_maintenance_is_in_the_estate_and_out_of_the_problem_count`, and `test_maintenance_can_be_opened_and_closed` over HTTP |
| Ten thousand resources **discovered**, summarised and queried within budget | `test_ten_thousand_resources_arriving_at_once_are_discovered_and_summarised` (a real sweep, suspending and resuming), plus the summary and query budgets above |
| `make verify` green | See §16 |

---

## 16. Two test modules were renamed after a collision the collision itself hid

`tests/unit/platform/estate/test_health.py` and `test_reconciliation.py` share
their basenames with `tests/unit/platform/persistence/test_health.py` and
`tests/unit/platform/knowledge/topology/test_reconciliation.py`. The test tree
has no `__init__.py`, so pytest imports by basename and two files with one name
are one module — collection failed on both pairs.

They are `test_estate_health.py` and `test_estate_reconciliation.py` now.

Worth recording because of what the collision was concealing:
`test_the_specification_names_exactly_twelve_ports` had been *uncollected* since
the estate suite landed, so the assertion that the port count is a deliberate
decision was silently not running. It is now
`test_the_specification_names_exactly_thirteen_ports`, and its docstring says
why the number moved.

---

## 17. Gate

`make verify` green: lint, format-check, mypy strict over 1,173 first-party
files, all seven import contracts, all eight guard scripts, integration parity
over 82 integrations, the generated integration catalogue, the environment
example, the documentation drift check, 28 documented examples, the whole
console gate (lockfile, format, lint, types, unit tests, production build,
generated client, budgets, end-to-end, visual), and the Python suite —
**9,992 passed, 20 skipped**, no failures.

Seven visual baselines were re-captured with `make console-visual-accept`:
`resources` at two widths, `incident` and the four `shell` shots, all of which
render estate figures that changed shape when the endpoint became real. The
mechanism that would catch an *unintended* pixel change is unaffected and is
still proven by `test_a_seeded_pixel_change_fails_the_run_and_emits_a_diff`.

One thing worth knowing for the next person: **the console gate and the Python
console-contract suite cannot run at the same time.**
`tests/contract/console/test_console_gate.py` proves each lint rule fires by
writing a deliberately-offending file into `console/src/` and deleting it again,
so a concurrent `eslint .` sees it and fails on a file nobody wrote. `make
verify` runs them in sequence and is unaffected; running them in two terminals
produces a failure that does not reproduce.

---

## Not deviations, recorded because they look like they might be

- **`EstateService.apply_rollups` stores what the read computes.** Reads compute
  the rollup so an operator never sees a stale aggregate; this materialises it so
  a *query by health* can find a degraded node without loading the estate. The
  stored value carries the derivation that names the rule, so the two cannot
  disagree about why.
- **`SweepReport.concluded_absence` is one expression.** Every path that must not
  mark anything absent — a failure, a suspension, an incremental pass — is ruled
  out by that one property rather than by three checks in three branches.
- **The ten-thousand-resource benchmark discovers as well as summarises.** The
  definition of done says "discovered, summarised and queried within budget", and
  a benchmark that seeded rows directly would have proved two of the three.
  `test_ten_thousand_resources_arriving_at_once_are_discovered_and_summarised`
  runs a real sweep through the real suspension-and-resumption path, which is
  what found §4's second half.
- **Discovery holds no credential, and three tests say so.** The protocol's
  signature has no parameter one fits in, the sweeper's constructor and method
  have none either, and `test_the_sweep_module_imports_nothing_from_the_credential_layer`
  reads the module's own source. `make check-credentials` covers the same ground
  from the other direction.
