# Deviations — 042 First Run, Seeding and Demo Mode

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 1. T-001 was made to fail for the right reason before it was made to pass

**Planned.** "Failing end-to-end test … Confirm it fails against the current
bootstrap before changing anything."

**Done.** Exactly that, in two steps, because the first form of the test proved
nothing.

Written against `platform.startup.bootstrap.bring_up`, which did not exist, it
failed on `ModuleNotFoundError`. That is not a demonstration of the bug — it is
a demonstration that a module is missing, and it would have failed identically
against a working deployment with a renamed function.

So a temporary `bring_up` was committed to the working tree first, reproducing
*today's* behaviour precisely: `secrets.token_urlsafe`, written to the host,
never issued through the identity system. Against that, the test failed the way
the live run did:

```
tests/contract/deployment/test_first_run_sign_in.py:160:
    assert response.status_code == 200
E   assert 401 == 200
E    +  where 401 = <Response [401 Unauthorized]>.status_code
    HTTP Request: GET http://gateway.test/auth/me "HTTP/1.1 401 Unauthorized"
```

That is the original defect, reproduced: the credential the deployment prints,
rejected by the running gateway. The real implementation then replaced the stub
and the same test passed unchanged. **The 401 is the whole feature**; everything
else in this document is detail around it.

---

## 2. Demonstration data is labelled by its tenant *and* by a field, not by a
new column on every table

**Planned.** "Demo data is labelled in the schema. A column, not a prefix on
names." (`plan.md`, architecture decisions; FR-017.)

**Done.** Two labels, both columns, neither new:

- **`org_id`.** The demonstration is seeded into an organisation of its own —
  the one feature 032's dataset already declares, read out of the root of its own
  configuration tree rather than written down a second time here. Every row of every
  table in this schema is tenant-scoped, so this labels every record — including
  the record kinds a later feature adds, which is the half a per-record stamp
  can never cover because it depends on whoever writes the next seeder
  remembering to stamp it.
- **The existing structured column.** Where a record has one — a resource's
  `attributes`, a run's `metadata`, an episode's `metadata`, an approval's
  `arguments`, a topology node's `properties`, a config node's `values`, an
  incident subject's `evidence` — `is_demonstration` is written into it, so a
  record exported out of its tenant still says what it is.

**Why not a new boolean column.** It would be a migration across roughly twenty
tables plus the domain dataclass, the Postgres repository and the in-memory fake
for each — about a thousand lines of churn through the most load-bearing layer
in the repository, to obtain a property the tenant column already has for free
and more completely. The plan's reason for wanting a column rather than a prefix
was that "a prefix is a convention that the first person to write a query
forgets; a column can be asserted on and swept". Both of these are columns, both
are asserted on, and the sweep is one predicate.

**Where the tenant's name lives.** Nowhere in this feature's code.
`tests/architecture/test_one_fictional_deployment.py` allows the fictional
deployment to be named only inside `tools/mockplane/`, `fixtures/` and `tests/`,
and a first pass here put it in `config/constants/fixtures.py` and was caught by
that test. `DemoDataset.organisation_id` now reads it from the dataset's own
config tree, which is a better answer than the one the check rejected: the
identifier of the fictional deployment is a property of the dataset that defines
it, and code that loads a dataset should not need to know it in advance.

**What is asserted.** `tests/unit/platform/startup/test_demo.py` walks every
seeded record of every kind that has a structured column and asserts the field
is present, and asserts separately that the only organisation in the store is
the demonstration one. `demonstration_residue` sweeps every organisation for
either label and is what SC-009 asserts comes back empty.

---

## 3. The demonstration seeds no audit events, and it cannot

**Planned.** FR-015: the scenario covers "… approvals, and an audit history".

**Done.** Everything else. The audit history is the one part of feature 032's
scenario that stays in the mock plane and is not loaded into the database.

**Why it is not a choice.** Three properties of this schema meet here:

1. Audit is append-only by constitutional design; `tests/security/
   test_audit_immutability.py` and a database trigger both enforce it.
2. Audit is the one data class marked exempt from retention deletion
   (`DEFAULT_RETENTION_DAYS[DataClass.AUDIT] is None`), so the sweeper cannot
   remove it either.
3. The audit table's foreign key to `organisations` **restricts rather than
   cascades**, deliberately, and it is documented as doing so in
   `PostgresOrgDirectory.delete_organisation`.

Taken together: a demonstration that wrote audit events would make its own
tenant undeletable, and FR-019's "removable in one action, leaving nothing
behind" would become unsatisfiable — permanently, on a real deployment, for
anybody who ever ran `--demo`. Contaminating the audit trail with fictional
events that can never be removed is precisely the contamination FR-017 to FR-020
exist to prevent, so the stronger requirement wins.

**What the console still shows.** The demonstration's history is in its incident
timelines and its run traces, both of which are seeded, and both of which are
where a person actually reads what happened. The `/audit/events` screen against a
demonstration deployment is empty, which is honest: nothing has happened on it.

---

## 4. `OrgDirectory` gained `delete_organisation`

**Not in the plan.** The port grew a fourth method; `PostgresOrgDirectory`
already implemented it and `FakeOrgDirectory` did not.

**Why.** FR-019 is "removable in one action". Expressed through the existing
ports that would have been a sweep across thirteen repositories, of which six
have no delete at all — `estate`, `approvals`, `signals`, `remediation`,
`knowledge` chunks, and topology nodes. Adding six delete methods to satisfy a
removal is six new ways to delete production data, added for the benefit of a
demonstration.

Deleting the tenant is one method, is what the schema's cascade already does,
and is a thing an operator offboarding a customer needs anyway — the Postgres
implementation says so in its own docstring and was only ever kept off the port
because nothing above needed it. Now something does.

---

## 5. `TokenService.issue` learned a sub-day lifetime

**Not in the plan.** `issue(..., lifetime: timedelta | None = None)`.

**Why.** The bootstrap credential lives for an hour. `lifetime_days` refused
anything below one day — correctly, since a token measured in fractions of a day
is a token whose expiry nobody can read. The alternatives were to round the
bootstrap credential up to a day, which is twenty-four times the exposure for no
benefit, or to teach every caller that `lifetime_days` is sometimes not days.

The ceiling still applies to both spellings and the existing behaviour is
unchanged: `lifetime_days` below 1 still raises. This is the only place in the
platform that issues a credential shorter than a day, and it says so.

---

## 6. The support bundle extends the one that already existed

**Planned.** T-030: "Support bundle in one command: versions, configuration with
secrets removed, recent logs, self-check results, schema state."

**Done.** `platform/observability/diagnostics.build_bundle` already produced
three of the five, with a redaction that is better than what this feature would
have written: an *allow-list* by the settings catalogue, so a cloud credential
the operator exported into the same shell is absent rather than filtered, plus a
per-value scan through the guardrail engine.

A first pass here wrote a second bundle with its own name-marker redaction. That
was deleted before it was committed. `platform/startup/diagnostics.SupportBundle`
now composes the existing one and adds the two things it has no way to know
about — the self-check's findings and the schema revision. `REDACTED` and
`SECRET_SETTING_MARKERS` were removed from `config/constants/first_run.py` in the
same change, because two vocabularies for one redaction is the thing that
eventually disagrees.

---

## 7. T-007 was already implemented, and is not reimplemented here

**Planned.** "Migration version check that refuses an incompatible schema with a
named error rather than guessing."

**Done.** Nothing. Feature 013 shipped it: `platform.startup.migrations.
check_compatibility` and `apply_at_startup` refuse both directions with
`SchemaIncompatible`, naming the applied revision, the expected one, and a
different remedy for each direction. `tests/unit/platform/startup/
test_migrations.py` covers behind-the-code, ahead-of-the-code, an empty
database, and a failure part-way through.

What this feature adds is the *ordering*: `gateway/http/serve.py` now runs
bring-up after the boot sequence, so a deployment whose schema is refused never
issues a credential for a process that is about to exit.

---

## 8. T-019 — the console does not render the checklist, and this is a real gap

**Planned.** "Console checklist appearing when incomplete, disappearing on
completion, reachable afterwards." (FR-011, FR-013.)

**Done.** Everything behind it, and none of the rendering:

| Delivered | Where |
|---|---|
| The checklist state model, four steps, each verified against the real dependency | `platform/startup/checklist.py` |
| `GET /v1/setup/checklist`, permission-declared, returning every step with its state and next action | `gateway/http/routes/first_run.py` |
| The route driven through the real application and the real guard | `tests/unit/gateway/http/test_first_run_routes.py` |
| The completion signal the console would hide itself on | `SetupChecklist.complete` |

**Why not the rendering.** The console is a Next.js application with its own gate
(`make console-check`) whose last two stages are a Playwright end-to-end suite
and a visual-regression comparison against committed PNG baselines. A new screen
needs a baseline, a baseline is a browser screenshot, and a screenshot committed
from this environment is a screenshot nobody reviewed. It also needs the mock
data plane to serve `/v1/setup/checklist`, which means a fixture, an entry in
`fixtures/contract/projected.json`, and the two tests that keep that document
honest — a change to feature 032's committed dataset, made in the course of
feature 042.

The instruction for this run is explicit that `make verify` must be left green
and that a failure is mine to fix. Adding a screen whose baseline I cannot
legitimately produce risks exactly that, in exchange for rendering a payload
that is already served and already tested.

**What a deployment still has to wire.** One screen reading
`GET /v1/setup/checklist` and hiding itself when `complete` is true. There is
nothing to decide in it: every step arrives with a title, a state, what was found
and what to do next.

---

## 9. The demonstration seeder was added to the incident lifecycle's rehydrators

**Not in the plan.** `tests/architecture/test_one_incident_lifecycle.py` asserts
that exactly one module constructs an `Incident`, with a declared exemption for
"the storage backends, which rebuild a stored incident rather than raising a new
one". The demonstration seeder was added to that exemption.

**Why this is applying the rule rather than relaxing it.** The rule's subject is
*raising*: deciding that something is wrong. The seeder decides nothing — it
restores incidents that were recorded, with their own identifiers, correlation
keys and subjects, from the committed dataset.

Routing it through `IncidentLifecycle.raise_incident` was tried and is wrong on
its own terms: that method derives the incident identifier from the correlation
key and the current instant, so seeded incidents would get a new identifier on
every seed. `fixtures/scenarios/populated/incident-detail.json` refers to
`inc-0001`, the console's deep links refer to `inc-0001`, and feature 032's whole
value is that two runs of the same dataset produce the same deployment. A
lifecycle-raised demonstration would have broken all three.

The exemption's docstring now says which of the two acts the seeder performs and
why the other one was rejected, so the next person to read it does not have to
re-derive this.

---

## 10. The `--json` contract exempts the six `setup` commands, and pays for it

**Not in the plan.** `tests/contract/cli/test_json_output_contract.py` requires
every published schema to be exercised by an entry in its own `INVOCATIONS`
table, which drives the CLI against `FakeServices`. The six `setup` commands are
in a new `HOST_SIDE` set instead.

**Why.** They read the *host* — the credential file, the recorded bring-up
failure — or the store composed from the configured database URL. `FakeServices`
is a façade over a deployment (`investigate`, `runs`, `effective_config`, …) and
has no gateway to lend them, so the runner cannot drive them. Adding a gateway to
`LocalServices` to satisfy a test would put a raw persistence handle on a
protocol that deliberately does not have one.

**What the exemption costs, and how it is paid.** The guarantee that set exists
to protect is "a schema nothing exercises can drift from the payload without
anything noticing". So all six are driven through the same typer application in
`tests/unit/surfaces/cli/commands/test_setup.py`, and each one's emitted `data`
is validated against `COMMAND_SCHEMAS`. The exemption says where they are
exercised; it does not exempt them from being exercised.

---

## 11. `ninjasre setup load-demo` and `remove-demo`, not `setup demo load`

The nested sub-group was written first and flattened. The published-schema
contract names a command by its leaf beneath one group, so both halves of a
`demo` sub-group resolved to `setup.demo` — one name, two commands, and no schema
for either. Flat names are two commands with two schemas, which is what the
contract is for.

---

## 12. Structure — modules the plan's technical context does not name

The plan says "`platform/startup/` extended, plus `deploy/ops/` for the host-side
pieces". It is, and these are the extensions:

| Module | Why |
|---|---|
| `platform/startup/bootstrap.py` | The credential: issuing, delivering, reading back, spending. |
| `platform/startup/selfcheck.py` | The `Finding` type and the nine checks. |
| `platform/startup/checklist.py` | The four steps and the guided investigation's objective and transcript. |
| `platform/startup/diagnostics.py` | Bring-up failures that outlive the terminal, and the bundle. |
| `platform/startup/demo/` | Four modules: the dataset reader and its coherence check, the labels, the seeder, the fixture transport, and the scripted stream. One module would have been 1,200 lines covering five unrelated concerns. |
| `core/llm/verification.py` | The decision `preflight` deliberately does not make. See §10. |
| `config/constants/first_run.py` | Every literal, per Article II. |
| `gateway/http/routes/first_run.py`, `gateway/http/security/first_run_routes.py` | The routes and their declared permissions, beside each other, as `gateway/AGENTS.md` requires. |
| `surfaces/cli/commands/setup.py` | The CLI half of FR-010 and FR-022. |

---

## 13. Model verification is a new module, not a change to `preflight`

**Planned.** T-016: "Exercise tool calling and structured output against the
configured provider." `core/llm/preflight.py` already does exactly that.

**Done.** `preflight` is unchanged and `core/llm/verification.py` decides over
it.

**Why they are separate.** They answer different questions and only one of them
is allowed to say no. Preflight *describes*: five checks, each passed, degraded,
failed or skipped, and degraded tool calling is reported and survived — right for
a report. T-015 and SC-006 require that the same condition **fail**. Editing
preflight to fail on it would have changed the meaning of `preflight passed` for
its existing callers, including `make preflight`, which an operator runs
expecting a description.

The split also let the second judgement be made explicitly and differently:
degraded *structured output* is accepted, because a model reaching it through a
prompt-and-parse shim genuinely works, and refusing it would rule out most
self-hosted models — which is feature 043's entire subject.

---

## 14. Four checks are reported as absent rather than as passes

`credential-proxy`, `model-provider`, `scheduler` and `observer` take an injected
probe. With none supplied they produce a *finding* — "nothing is wired" — rather
than a pass or a skip.

**Why it is worth stating.** The alternative reading of FR-007 is that a check
with no collaborator has nothing to check and should be silent. That is how a
self-check becomes a wall of green ticks: the deployment with no credential proxy
is exactly the deployment that most needs telling, and "we did not look" and
"there is nothing there" have to be distinguishable. `observer` is the one of the
four that only *degrades*, because a deployment fed by webhooks alone is a
reasonable design.

---

## 15. The self-check's model check is not run by the console route by default

`GET /v1/setup/self-check` and `GET /v1/setup/checklist` do not pass a model
verifier, so the provider step reports "no provider has been verified against
this deployment" rather than verifying one.

**Why.** Verification makes four real calls against the operator's endpoint. A
console page that spent tokens every time somebody opened it is a page nobody
opens twice, and this repository already keeps that class of check in
`make preflight` rather than in anything that runs by itself. A deployment that
wants it supplies the verifier at composition; `ninjasre onboard` and
`core/llm/preflight` are the two paths that run it deliberately.

This is the same disposition feature 019 recorded for the provider-dependent leg
of SC-001, and for the same reason.

---

## 16. T-028 is satisfied by feature 032's drift check, not by new machinery

**Planned.** "Generate demo fixtures through the integrations' existing contract
tests, so an API change breaks both together."

**Done.** Nothing new, and the property holds. The demonstration loads feature
032's dataset, and that dataset is validated against
`fixtures/contract/openapi.json` — a document `tools/mockplane contract`
regenerates from the real `create_app`, with
`test_the_committed_document_is_what_the_application_generates` keeping the two
equal. A route that changes shape fails that test on the commit that changes it.

This feature paid that check twice while it was being written: adding the
`/v1/setup/*` routes made the committed document stale, and it was regenerated,
along with the console's generated API client. That is the mechanism T-028 asks
for, working.

The plan's phrasing — "through the integrations' existing contract tests" —
describes a second route to the same property that would have meant a *third*
generator for fixtures the dataset already holds. The risk it names, "the fixture
set rots as the API changes", is closed by the drift check.

---

## 17. Test-first, per module rather than per phase

Followed the way features 020 and 021 record: T-001 first and confirmed red for
the right reason (§1), then each module's tests written, run, and confirmed
failing before its implementation. The failures were behavioural rather than
import errors in every case where that was achievable — the bootstrap suite was
red on a rejected token and a world-readable file, the self-check suite on a
`Finding` that could be constructed without an action, the demo suite on an
estate that resolved five subjects to nothing.

Two suites were written after the module they cover, and both are noted here
rather than claimed otherwise: `tests/unit/gateway/http/test_first_run_routes.py`
and `tests/unit/surfaces/cli/commands/test_setup.py` are views over logic that
was already tested at the seam below them, and a route test written first could
only have failed on a 404.

---

## Where each success criterion is proven

| Criterion | Test |
|---|---|
| SC-001 | `tests/contract/deployment/test_first_run_sign_in.py::test_the_credential_bring_up_prints_signs_in_and_reaches_an_authenticated_page` |
| SC-002 | `tests/unit/platform/startup/test_bootstrap.py::test_establishing_a_durable_credential_expires_the_bootstrap_one` |
| SC-003 | `tests/security/test_bootstrap_credential_never_leaks.py` — five tests over the log, the audit trail and an exception's message, across the credential's whole life |
| SC-004 | `tests/unit/platform/startup/test_bootstrap.py::test_bringing_up_twice_changes_nothing`, plus `…_does_not_duplicate_the_organisation_or_the_grant` |
| SC-005 | `tests/unit/platform/startup/test_selfcheck.py::test_every_finding_the_check_can_produce_names_a_problem_and_an_action` — every check driven into its failing path, not a sample |
| SC-006 | `tests/unit/core/llm/test_verification.py::test_an_endpoint_that_answers_but_cannot_tool_call_fails_verification` and `…_names_the_actual_limitation_rather_than_a_bare_failure` |
| SC-007 | `tests/unit/platform/startup/test_demo.py::test_every_reference_in_the_dataset_resolves` |
| SC-008 | `tests/security/test_demo_mode_makes_no_external_call.py` — a socket guard over the whole demonstration, plus the transport's own refusal, plus a test that the guard fires |
| SC-009 | `tests/unit/platform/startup/test_demo.py::test_removal_leaves_nothing`, with `…_the_sweep_would_notice_a_record_that_survived` proving the sweep can see |
| SC-010 | `tests/benchmarks/test_first_run_budgets.py` — six tests over the three budgets |

---

## Not deviations, recorded because they look like they might be

- **The bootstrap token holds two permissions, not one.** FR-003 says
  "single-purpose". `token.manage` is the purpose; `investigation.read` is what
  `GET /auth/me` costs, and a credential that cannot ask who it is cannot
  complete a sign-in. The principal behind it is an owner — it has to be, or the
  durable credential it establishes could not be granted anything — and the
  token's own ceiling is what keeps a leaked bootstrap credential from changing a
  configuration.
- **The demonstration estate includes a `cluster` resource no fixture lists.**
  Incidents, observations and episodes in feature 032's capture all refer to
  `cluster`, and no estate read returns one. It is derived from the hosts' own
  quorum arithmetic — the votes, the expected votes, the member names, all read
  off rows the capture recorded — rather than invented, and its health follows
  from the arithmetic rather than from a flag.
- **Episode components resolve against display names and failed units, not only
  resource identifiers.** A component key is what a person calls the thing that
  went wrong. In this capture that is a guest's display name, a host's short
  name, or the systemd unit that failed on it, and all three are values the
  capture recorded. A component naming something the capture never saw still
  fails the coherence check.
- **`platform/startup/demo/` reads `fixtures/` directly rather than importing
  `tools.mockplane`.** `tools/` is repository tooling, not a packaged runtime; a
  shipped product importing it would depend on a directory the package does not
  include. The root `AGENTS.md` already names the demo seeder as one of the
  fixture tree's three readers. What is shared is the vocabulary — the label
  field and the label value moved to `config/constants/fixtures.py` and
  `tools/mockplane/seed.py` now imports them from there. The organisation did
  not — see §2.
- **`deploy/ops/preflight.py` runs only two of the nine checks.** Preflight runs
  before the deployment does, so the store, the proxy and the provider are
  legitimately absent and reporting them would make every clean preflight red.
  The two that are about the *host* — disk and clock — are exactly what preflight
  is for, and they come from the same `run_checks` the console and the CLI call
  rather than from a third checker.
