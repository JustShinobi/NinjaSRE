# Deviations — 025 Integration Catalogue Parity

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

## 1. The catalogue lands at 82 integrations, with 7 recorded gaps

`spec.md` counts 86; `tasks.md` enumerates 88 (T001–T091 plus the three
already-built reference integrations), because T010 and T037 name Loki and
Tempo as their own integrations while the spec's observability count folds
them into Grafana. I built from `tasks.md`, which is the authoritative work
list.

Of those 88 names, **82 are installed and at full parity** and **7 are
recorded as unreachable** in `integrations/_catalogue/gaps.py` (FR-003). The
arithmetic: 88 names − 7 gaps = 81, plus `redis_server` — which is a gap
recorded for the self-hosted engine while `redis` (Redis Cloud's control
plane) *is* installed — gives 82 installed.

**Every gap has the same cause, and it is architectural rather than effort.**
Article IV puts the credential in an HTTP proxy: a client sends an
unauthenticated request and the proxy attaches the secret at the network edge.
A vendor that speaks a binary wire protocol has no request for the proxy to
attach anything to, and the only two ways to build such a client are both
refused — hold the credential in the agent process (forbidden outright), or
open the connection from something that holds it (the same thing with more
steps). This is exactly the reasoning feature 024's own deviations recorded
when it declined to measure a database integration for T049.

| Recorded gap | Why | What is reachable instead |
|---|---|---|
| `postgresql`, `mysql`, `mariadb` | Binary wire protocol | `aws_rds` (instance state, failovers, parameter changes), `supabase` |
| `mongodb` | Binary wire protocol | `mongodb_atlas` (process and cluster state) |
| `redis_server` | RESP | `redis` — Redis Cloud's HTTP control plane, which *is* installed |
| `smtp` | Stateful line protocol; authentication happens inside a conversation the proxy cannot join | `twilio`, `pushover` |
| `helm` | Helm 3 has no server component at all — a release is a Secret in the cluster | `kubernetes`, `argocd` |

The gaps are a declaration rather than an absence: `gaps.py` names each
vendor, the reason, and what would change it; the generated catalogue page
renders them; and
`tests/contract/integrations/test_catalogue_wide_guarantees.py` fails if a
recorded gap is ever also an installed package, so the record cannot go stale
in the direction that matters.

**What this costs.** PostgreSQL is a tier-1 name in `spec.md`, and the loss is
real: an investigation can learn that an RDS instance failed over but not what
was blocking inside it. Nothing in the current roadmap closes it — feature 026
is MCP/ACP/OpenClaw, not a database bridge — so this is an honest gap rather
than a deferral, and it is written down as one.

## 2. Two categories were assigned by what a vendor answers, not by its marketing

`IntegrationCategory` selects the methodology template, so the category has to
describe what the integration actually contributes to an investigation.

- **Grafana is `cloud_control_plane`, not `metrics`.** The series live in the
  datasources behind it — Prometheus, Loki, Mimir — and each of those is its
  own integration. What Grafana itself answers is what dashboards and folders
  exist, and the annotation timeline of deploys and alert state changes, which
  is the control-plane methodology exactly ("changes, state, quotas").
- **`flagd` is `cloud_control_plane`.** A flag change is a production change
  no deployment pipeline records, which is a change-history question.

Both are stated in the integration's own package docstring so a reader who
expected otherwise finds the reasoning where they look for it.

## 3. Framework additions the catalogue forced

Four, each because the alternative was the same code in eighty places.

- **`integrations/_base/payload.py`** — `dig`, `records`, `text`, `named`,
  `tabular`, `xml_records`, `xml_text`, `counted`. Every client parses a
  document somebody else's service produced, and written per vendor each of
  those is an index expression: a vendor's error body has the same content
  type as its success body, so `answer["data"]["results"]` raises a `KeyError`
  inside a capability, which ends the turn and takes the trace with it. Every
  reader here answers "nothing" instead. `xml_records`/`xml_text` exist
  because the AWS query-protocol services (EC2, RDS, ELB, S3) have no JSON
  dialect to ask for; `named` because AWS list operations answer with arrays
  of ARNs rather than objects; `tabular` because Snowflake answers with
  columns and rows separately.
- **`PaginationStyle.PAGE_NUMBER`** — a fourth style. FR-005 named three, and
  the catalogue turned out to contain a great many vendors that count pages
  rather than records (Grafana, GitLab, Jenkins, Jira's siblings, Trello,
  Twilio, MongoDB Atlas, FireHydrant). `OFFSET` cannot express it: sending a
  record count in a page parameter reads from a completely unrelated part of
  the result set and answers with data that looks plausible. It shares
  `OFFSET`'s termination rule (a short page) and its requirement to declare a
  page size, and `_COUNTED_STYLES` is what keeps the two in step.
  `test_base_pagination_styles.py` gained four assertions and its
  "all three styles" test became "every declared style".
- **`integrations/_catalogue/gaps.py`** — §1.
- **`tools/scaffold_integration.py` emits only `DESCRIPTOR`**, not a
  vendor-named alias beside it. This was a latent defect in feature 024 that
  this feature was the first to hit: `AWS_EKS` is SCREAMING_SNAKE with a
  vendor prefix, so `make check-constants` reads the name in `__all__` as an
  environment variable and fails the build. Any two-word vendor scaffolded
  before this fix would have failed the same way. The alias added nothing —
  discovery reads `DESCRIPTOR` — so it is gone rather than renamed. The three
  reference integrations keep theirs (`DATADOG`, `AWS`, `KUBERNETES`; single
  words, not env-shaped).

## 4. `check_raw_sql.py`: the literal rules stop applying under `integrations/`

ClickHouse, Snowflake, and OpenObserve take a SQL statement as the body of an
HTTP request. That statement is the vendor's request grammar — the same kind
of thing as a LogQL selector, a JQL expression, or a PromQL query elsewhere in
the same tree — and there is no repository port to bypass, because the data is
not this system's.

The change extends the seam the module already had for `tests/`, and it
extends it to exactly one of the three rules. `scans_literals()` now returns
false under `integrations/` as well; `query-execution` and
`database-driver-import` — the two the module's own docstring calls "the rule
that does the work" — still apply there, so a module under `integrations/`
still cannot import `asyncpg` or call `execute`, and a client that reached
this repository's own datastore would fail exactly as it does anywhere else.
Four new assertions in `test_check_raw_sql.py` pin all of that, including that
a statement outside both trees still fails.

This is a refinement of the rule's scope rather than a loosening of it, and it
is the alternative to writing three integrations that cannot talk to their
vendors.

## 5. Statistics are computed client-side for most vendors, and every one says so

FR-006 requires a statistics-first variant wherever a capability could return a
large payload. Datadog's, written in feature 024, aggregates server-side; most
vendors have no aggregation endpoint at all.

So the generated `*_statistics` capabilities read one bounded page and group it
with `counted()`. That is genuinely cheaper in the place that matters — the
result carries buckets rather than record bodies, so the context budget is
spent on a distribution instead of on prose — and it is *not* cheaper on the
wire. Every affected integration's `docs.md` and `SKILL.md` say so in those
words: "a distribution over a capped sample and one over everything are
different claims, and only one of them is what this returns". Where a vendor
does aggregate server-side (Datadog, and OpenObserve's SQL `GROUP BY`), the
skill says to push the counting down.

Recording it here rather than treating it as satisfied silently, because a
statistic quoted as if it covered everything is worse than no statistic.

## 6. Test-first, and what that meant for eighty-two integrations

The contract suite is parameterised over the discovered catalogue, which is
the property feature 024 built it for: **adding an integration adds test rows
rather than a test file.** So for each integration the tests genuinely landed
first — thirty-four assertions per vendor were already written and already
failing for it the moment its package existed, and the synthetic scenario
(artefact seven) is itself a test that ships with the integration.

Everything that was not covered that way was written test-first in the usual
sense, red confirmed before the implementation:

| Test | Implementation |
|---|---|
| `test_base_payload.py` | `integrations/_base/payload.py` |
| `test_base_pagination_styles.py` (4 new) | `PaginationStyle.PAGE_NUMBER` |
| `test_catalogue_gaps.py` | `integrations/_catalogue/gaps.py` |
| `test_check_raw_sql.py` (4 new) | the `scans_literals` seam |
| `test_catalogue_wide_guarantees.py` | the catalogue-wide properties themselves |
| `test_tier_one_investigation.py` | SC-006 |

## 7. Two shared test fixtures now derive rather than duplicate

`tests/contract/integrations/conftest.py` held a hand-written credential per
integration, and `test_credential_verification.py` held a second copy of three
of them. At eighty-two integrations a hand-written mapping is a second thing to
update whenever a schema gains a field, and the copy nobody updates turns a
real contract failure into a fixture failure somewhere else in the suite.

Both now read each integration's synthetic scenario, which already declares a
credential in the schema's shape. One source of truth, and
`test_verifying_every_integration_reports_one_result_each` consequently means
*every* integration rather than the three somebody remembered to seed.

## 8. `_authenticated` in the parity suite now understands a path injection

Telegram's credential is a path segment — `/bot{token}/getMe` — which is
Telegram's own design. The parity suite's proxy-routing assertion checked for
an injected header or a query parameter and read a path injection as "nothing
was injected", so the one vendor whose credential travels in the URL would have
passed the test for the wrong reason.

It now takes the catalogue entry and asserts the right thing for that shape:
no `PathSegmentInjection` placeholder survives into the URL the vendor
received. Strictly more is checked than before.

## 9. `docs/provenance-map.md` (T102) not touched

Per `CLAUDE.md`, that file is gitignored and is never linked from a committed
file. Editing the local, uncommitted copy would have no effect on what ships.
There is no `make check-provenance` target in this repository — the same
finding feature 024 recorded.

## 10. T022's measurement, against feature 024's SC-001

T022 asks for the actual per-integration effort measured against the estimate.
Feature 024 measured 40–55 minutes per integration for the three reference
vendors, and predicted the framework would make the eighty-fifth cost what the
third did.

**It did not, and the reason is the interesting part.** Bringing a vendor to
parity by hand is not 40 minutes of framework work and 10 of vendor knowledge;
it is the reverse. The seven artefacts are the same shape every time — that is
what feature 024 delivered and it held — but the *content* is per vendor and
irreducible: which host, which auth header, which path, which response key,
which permission is named what in whose console, and which three things
surprise somebody at 03:00.

So the per-integration cost split cleanly in two, and only one half compressed:

- **Shape** — schema, client, verifier, tools, docs skeleton, skill frontmatter,
  scenario wiring. Compressed to near zero: it is emitted from an archetype and
  a vendor record.
- **Vendor knowledge** — roughly 30 lines of specification per integration, and
  no framework makes that smaller because it *is* the integration.

The practical consequence, and the thing worth carrying into feature 026: the
eleven domain archetypes turned out to be the reusable unit rather than the
per-vendor scaffold. A twelfth kind of system is a twelfth archetype; the
eighty-third vendor of an existing kind is a data change. That is a stronger
version of SC-001's claim than the scaffold alone delivers, and it is only
visible once there are enough vendors per domain to see the pattern repeat.

## 11. T023's framework adjustment, made rather than deferred

T023 asks for framework adjustments before committing the remaining ~68
integrations. Four were made and are in §3 — `payload.py`, `PAGE_NUMBER`, the
`DESCRIPTOR` fix, and the SQL seam — each after a vendor demonstrated the need
rather than in anticipation of one. Tier 1 was green before tier 2 was started,
and the whole catalogue was green before this was written.

## 12. Definition of done

| Item | Where it is satisfied |
|---|---|
| SC-001 — all pass the parameterised contract suite | `tests/contract/integrations/` — 82 rows × 17 parameterised assertions, all green |
| SC-002 — all have a solvable synthetic scenario | `tests/synthetic/test_integration_scenarios.py` — 164 scenarios, 3 assertions each, through the real proxy |
| SC-003 — no client reads a credential | `test_no_integration_can_read_a_credential.py` + per-integration post-call slot inspection + per-scenario result inspection |
| SC-004 — every write declares its level and has a rollback | `test_catalogue_wide_guarantees.py::test_every_write_capability_is_gated_and_carries_a_way_back`, and the planner is *invoked* rather than merely asserted present |
| SC-005 — every skill passes binding and anti-pattern validation | `test_catalogue_wide_guarantees.py::test_the_whole_capability_catalogue_validates_including_every_skill_body` |
| SC-006 — tier-1-only end-to-end investigation | `tests/synthetic/test_tier_one_investigation.py` — real tools, real clients, real proxy, three integrations bound at once |
| SC-007 — documentation generated without drift | `make check-integration-docs`, inside `make verify`; the gaps render there too |
| SC-008 — live verification done or explicitly marked unverified | See below |
| `make verify` green | 8,285 passed, 15 skipped, 0 failed |

**SC-008, stated plainly.** No integration in this catalogue has been verified
against a live vendor, because this repository holds no credentials for any of
them. Every integration therefore reports `HealthStatus.UNKNOWN`, which is the
enum member feature 024 added for exactly this and whose docstring says it is
"not the same as healthy". The generated catalogue page renders `health:
unknown` for all 82. That is the "explicitly marked unverified" half of SC-008
satisfied; the "live verification where the maintainers hold credentials" half
is satisfied vacuously, because they hold none. The mechanism is built and
tested (`ninjasre integrations verify --all`, the health ledger, and
`test_a_vendor_break_degrades_rather_than_fails.py`); what is missing is
credentials, and inventing a claim about a vendor nobody called would be the
one failure this whole feature is shaped to prevent.

**Test count.** 5,538 → 8,285 passed. Almost all of the increase is
parametrisation: 79 new integrations adding rows to suites that already walked
the catalogue, which is the property feature 024 was built for and the reason
this feature was affordable at all.
