# Deviations — 027 Synthetic Scenario Harness

What was built differently from `plan.md` and `tasks.md`, and what was not built
at all. Written at the point of the implementing commit so the next person
reading the plan does not have to diff it against the tree to find out where the
two disagree.

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

Three sections: things done differently and why, things found wrong during
implementation, and things not done.

---

## 1. Deviations from the plan

### Evidence-source vocabulary is the repository's, not the plan's example

**Plan says** (fixture-schema block): `available_evidence: [k8s_pods, k8s_events,
k8s_pod_logs, datadog_logs]` and `required_evidence_sources: [k8s_events,
k8s_pod_logs]`.

**Shipped**: `available_evidence: [kubernetes]`, `required_evidence_sources:
[kubernetes]`.

**Why**: FR-005 requires the evidence-source vocabulary to be *validated*, and
the only vocabulary this repository has to validate against is the one it
actually produces. A capability declares `evidence_source="kubernetes"` and an
`EvidenceEntry` is attributed to `"kubernetes"`; there is no `k8s_events`
anywhere in the system. Keeping the plan's finer-grained names would have meant
either an unvalidated free-text field — the exact silent-mismatch failure FR-005
exists to prevent — or a translation table between two vocabularies that would
drift the first time an integration was renamed.

**What replaces the granularity**: which fixtures a scenario ships. A scenario
that plants events and not logs has one recorded response for the events
endpoint and none for logs, and the log call gets the empty-but-valid answer.
The answer key's `required_queries` axis asserts against the vendor URLs the run
actually reached, which is finer-grained than the plan's list and is checked
against what happened rather than against a declaration.

### Confounders are declared on the recorded response, not only on the scenario

**Plan says**: `adversarial_signals` is a `scenario.yml` field.

**Shipped**: that field, *plus* an optional `adversarial_signals` on each
recorded response, and a load error when a scenario declares a confounder no
response claims to carry.

**Why**: acceptance scenario 4 says "the planted confounders are present in the
evidence the agent can see", and FR-022 says they are declared so resistance can
be reported separately from accuracy. Declared only on the scenario, both are
claims: a scenario could name a confounder that appears nowhere in its fixtures,
and the suite would report resistance to evidence nobody was shown — the most
flattering kind of wrong number a suite can produce. Six lines of schema make it
a fact. `tests/synthetic/test_scenario_corpus.py` asserts it across the corpus,
and the loader refuses a mislabelled scenario.

The same check also requires `ruling_out_keywords` on every level-2-and-above
scenario, for the same reason: a confounder nobody asserted was dismissed is a
confounder the suite cannot score.

### `backends/postgres.py` is `backends/rds_postgres.py`

**Tasks say** (T019): `backends/postgres.py`.

**Shipped**: `tests/harness/backends/rds_postgres.py`, owning `aws_rds`.

**Why**: this repository ships no integration called `postgres`. The managed
PostgreSQL it does ship is `aws_rds`, which is also what the plan's own
provenance table means by "the RDS PostgreSQL suite". A module named
`postgres.py` registering `aws_rds` would be a filename that disagreed with its
contents. It is a separate module from `aws.py` rather than a row in it because
that is the unit a contributor thinks in: somebody porting a slow-query scenario
is working on PostgreSQL, not on the eighth AWS service.

### Two files the plan's project structure does not list

| Module | Why |
|---|---|
| `tests/harness/__main__.py` | T027 asks for a CLI entry point sharing one loader and executor. `python -m tests.harness` is that, and it is what `make test-synthetic` runs. Putting it in `suite.py` would have mixed argument parsing and terminal formatting into the module the pytest path imports. |
| `config/constants/evaluation.py` | Article II puts every bound and every environment-variable name in `config/constants/`. `NINJASRE_SCENARIO_ARTIFACTS`, the difficulty ladder, the attempt ceiling, and the two time budgets are bounds. `tools/check_constants.py` does not scan `tests/`, so a literal there would have passed the gate — which is a reason to be careful rather than a licence. |

`backends/base.py` also grew two things the plan's one-line description does not
mention — `synthesise_credential` and `stand_up` — because "vendor-boundary
interception on the real client path" (T009) cannot be stood up without a
vault-valid credential, and hand-writing one per integration would have broken
SC-005 for every new vendor. The credential is generated from the integration's
own declared schema, including its regular-expression format, so a new
integration needs no secret written anywhere.

### Determinism is enforced in two halves, and says so

**Plan says**: "Temperature zero and fixed seeds where the provider supports
them".

**Shipped**: `DeterministicProfile` carrying temperature, top-p, seed, reasoning
effort, and prompt caching — of which this layer *enforces* the last two and
*declares* the first three.

**Why**: `core.llm.types.InvokeRequest` deliberately carries no temperature and
no seed. Sampling parameters are provider-level configuration in this codebase,
and adding fields for them to the neutral request type would have been this
feature changing the LLM abstraction to suit its own test harness. So the two
fields that *are* per-request and *do* affect reproducibility — `prompt_cache`
and `reasoning_effort` — are pinned on every request and asserted; temperature,
top-p, and seed travel in `InvokeRequest.metadata` for a provider that forwards
them, and are recorded on every verdict so a reader can see what a run was
configured with.

SC-002 is therefore asserted twice: once on a `DeterministicClient` over a
scripted provider, and once on the transcript player, which is deterministic by
construction because there is nothing left to sample. That second assertion is
the one the corpus gate runs.

### Task ordering within Phase 3 and Phase 4

T027 (the CLI) is written after T031 rather than before T028. The CLI's default
provider is the offline transcript player, so writing it before `offline.py`
existed would have meant a CLI that could not run anything. Everything else
follows the plan's order.

Test-first held for phases 1, 2, 4, and 5: the tests landed first and were
confirmed failing (`ModuleNotFoundError`, then real assertion failures) before
the implementation. For **phase 3** the order slipped — `runner.py` and
`suite.py` were written before `test_runner.py`, and the tests passed on the
first run. They exercise real collaborators throughout (the real pipeline, the
real loop, the real proxy, the real capabilities), and two of them found real
gaps later in the session, but the red step was skipped and that is worth
recording rather than glossing.

---

## 2. Things found during implementation

### The AWS query protocol is a GET with a query string, not a POST with a body

The first version of the AWS fixtures matched on `body_contains: "Action=..."`,
which is what the signer's own protocol detection suggests. In practice
`aws_ec2_resource_inventory` and `aws_rds_resource_inventory` issue
`GET https://<host>/?Action=DescribeInstanceStatus&Version=...` with no body at
all, so both fixtures fell through to the empty-but-valid fallback and both
scenarios "passed" while finding nothing.

That is exactly the failure the corpus test
`test_every_recorded_fixture_is_actually_reached_by_its_scenario` now exists to
catch: a scenario whose fixtures never match is measuring the empty fallback, and
it looks identical to a scenario that works. The matchers are
`query_contains` now, and the assertion is permanent.

The backend's own protocol detection was already right — it checks the URL as
well as the body — so the empty answers were correctly shaped XML throughout.

### `OutboundResponse` is `status_code`, not `status`

A two-minute fix, recorded only because it is the kind of thing that reads as a
scenario failure: the boundary raised inside `send`, the proxy reported the
vendor as unavailable, the client retried twice with backoff, and the capability
returned a failure. Nothing in that chain says "the harness has an attribute
error".

### A test-module basename collision

`tests/unit/harness/test_backends.py` collided with
`tests/contract/persistence/test_backends.py` — neither directory has an
`__init__.py`, so pytest imports both as `test_backends` and refuses. Renamed to
`test_mock_backends.py`. (The repository has two other same-basename pairs;
both live in directories that *do* carry an `__init__.py`, which is why they are
fine.)

---

## 3. Things not done

### T051 — `docs/provenance-map.md` not touched

Per `CLAUDE.md` that file is gitignored and never linked from a committed file,
so editing the local copy would have no effect on what ships. There is no
`make check-provenance` target in this repository's `Makefile`. The
general-audience documentation this feature does ship is
`docs/synthetic-scenarios.md`, which covers the fixture format, the curriculum,
the recording procedure (T044), and the contribution path — with no reference to
any prior-art project, per the naming rule.

### The corpus is seven scenarios, not a port of an upstream corpus

T036–T040 ask for a port of several upstream suites. What is shipped is a seed
corpus of seven scenarios across five suites — `kubernetes` (3), `aws`,
`observability`, `database`, `delivery` — spanning all four difficulty levels
and eight integrations (`kubernetes`, `aws_ec2`, `aws_rds`, `prometheus`,
`loki`, `github`, plus `sentry` in the SC-005 test).

Every one of them:

- loads against the validated schemas,
- runs end to end through the real pipeline, the canonical loop, the real
  clients and the real credential proxy,
- reaches every fixture it ships (nothing falls through to the fallback),
- and runs offline, for zero tokens, on every pull request.

Growing the corpus is now a fixtures-only exercise, which is the property the
feature exists to establish and which SC-005 asserts against an integration the
harness has no backend module for. The spec's own "out of scope" section says
the corpus beyond the seed is feature 025's contribution.

### Live-provider recording is implemented but not exercised against a real vendor

`RecordingSender` (fixtures) and `TranscriptRecorder` (model transcripts) are
both implemented, tested, and documented, and both are wrappers on the live path
rather than second implementations. Neither has been run against a real vendor
or a real provider in this session, because doing so needs credentials and token
spend that the constitution keeps out of the gate. The procedure is documented
in `docs/synthetic-scenarios.md`; the first real recording will be the first
time it is exercised end to end.

### SC-004 verified by construction, not by a contributor

T035 asks for "a contributor to diagnose three induced failures from records
alone". No second person was available. What is shipped instead is three tests
that induce exactly those failures — a wrong category, a missing keyword, an
investigation that never reached the evidence — and assert that the record names
which one happened, what the agent did instead, and which specific keyword or
source was missing. That is the property the exercise was meant to establish; it
is not the same as somebody having done it.
