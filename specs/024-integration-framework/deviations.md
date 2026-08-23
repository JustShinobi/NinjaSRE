# Deviations — 024 Integration Framework

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

## 1. Phase 7 measures three shapes, and the third is not a database (T049)

The plan's Phase 7 asks for three integrations of different shapes, the third
being "a database integration (non-HTTP protocol)". That one was not built, and
the reason is in the spec's own text rather than in a judgement about effort.

**Protocol bridges are feature 026, by this spec's "Out of scope" section.** A
database's wire protocol cannot route through the credential proxy, which is
HTTP. There are exactly two ways to build a database client today: hold the
credential in-process (forbidden outright by Article IV, and there is no
in-process-credential exception — `SdkStrategy.NO_EXCEPTION_GRANTED` exists as a
name that raises at construction), or stub a bridge that feature 026 will
replace. The first is not available and the second measures the stub rather than
the framework, so SC-001's number would be about work that is going to be thrown
away.

The three shapes actually measured are the three the framework has to survive:

| Shape | Integration | What is different about it |
|---|---|---|
| REST observability vendor | `datadog` | Two header injections, six regional hosts, cursor pagination |
| Cloud vendor, different auth shape (T048) | `aws` | SigV4 signed proxy-side, page-token pagination, per-service and per-region hosts |
| Operator-declared egress | `kubernetes` | Bearer token, hosts NinjaSRE cannot know, continue-token pagination |

`aws` is what T048 asks for — "different auth shape" is the whole point of that
row, and proxy-side SigV4 is as different as an auth shape gets.

**Measurement (SC-001).** Each of the three was already at three of the seven
artefacts (schema, verifier, client) from feature 007. Bringing each to full
parity — the tools, the skill, the docs, the scenario, and the `PROFILE` — took
roughly 40–55 minutes per integration once the framework existed, the bulk of it
spent on the two things the scaffold deliberately refuses to write: the
permission list and the methodology. That is inside SC-001's two hours with
margin, and the margin is the part that is honest — a vendor whose permission
model is genuinely unfamiliar would spend more of it, which is what the
"typical REST vendor" qualifier in SC-001 is for. The Wave 6 estimate stands.

## 2. `<vendor>/config.py` renamed to `<vendor>/schema.py`

FR-001 names the first artefact `schema.py`; the three reference integrations
from feature 007 called it `config.py`, and `integrations/AGENTS.md` documented
that name. Renaming makes FR-001 literally checkable and makes the scaffold's
output match the reference integrations rather than diverge from them on the
first file a contributor opens.

Renamed with `git mv` in all three packages, imports updated (eight lines plus
one test import), `integrations/AGENTS.md` and `docs/integrations.md` updated.
The alternative — accepting either name in the parity check — would have put a
permanent wart in the one rule the whole feature rests on.

## 3. `capabilities/skills/_templates/cloud-control-plane/` renamed to `cloud_control_plane/`

The scaffold selects a template from a domain name, and the catalogue's
`IntegrationCategory` values are the same eleven domains. Making the template
directory name *equal* the category value means there is no mapping table to
keep in step with the enum — `template_for()` is the identity function, and
`test_there_is_a_template_for_every_domain_an_integration_can_declare` compares
the two sets directly. One directory renamed and its frontmatter updated;
nothing referenced the old name.

## 4. Two `_base` modules the plan's structure does not list

The plan's project structure lists `_base/{client,pagination,errors,regions,schema}.py`.
Two more were added, both because the alternative was per-vendor duplication of
exactly the kind this feature exists to prevent:

- **`_base/access.py`** — how a vendor's tools get a client. Every capability
  needs the proxy transport, the tenant, and its own name, none of which is
  knowable from inside the tool. One process binding, set by composition,
  following the precedent `capabilities/tools/remediation/control_plane.py`
  already sets for exactly this seam. Without it, every one of ~85 vendors'
  tools would construct its own client from ambient configuration, which is the
  failure that module's docstring already argues against.
- **`_base/capability.py`** — the two results every vendor capability returns
  without thinking about it: "this integration is not configured" and "the
  vendor refused". Both have a classification that is easy to get subtly wrong,
  and both wrong answers are invisible in review — an unconfigured integration
  reported as an empty result teaches an investigation something false about the
  estate.

## 5. `ErrorCategory` added alongside `IntegrationErrorReason` rather than replacing it

FR-006 names seven categories. `IntegrationErrorReason` already existed with ten
finer-grained members and seven callers. Collapsing it would have lost the
distinction between "the proxy has no credential for this team" (an operator
action) and "the vendor rejected the key" (a key problem), which is precisely
what makes a verification message actionable.

So `ErrorCategory` is the coarse taxonomy the framework contracts on, `.category`
maps every reason onto it, and `category_for(status)` is the one table. Both
vocabularies are exercised, and a test parametrised over every reason fails if
somebody adds an eleventh without mapping it.

## 6. T018's CI check already existed

T018 asks for a CI check that no integration module reads a credential-shaped
environment variable. `tools/check_direct_credentials.py` already does more than
that: its `credential-env-lookup` rule rejects *any* process-environment read
under `integrations/`, not only credential-shaped ones. Nothing was added; the
catalogue-wide contract test
(`tests/contract/integrations/test_no_integration_can_read_a_credential.py`)
runs the same checker over `integrations/` so SC-004 is asserted by the suite as
well as by the gate.

## 7. `_catalogue/validation.py` takes its roots as parameters

Two of the seven artefacts live outside `integrations/` — the skill in
`capabilities/skills/` and the scenario in the synthetic harness. `parity_of`
takes all three roots as required arguments rather than defaulting them, because
a default computed from one checkout's layout would silently check a directory
that is not there in another, and a parity check that silently checks nothing is
worse than none: it reports success. `_catalogue/discovery.py` computes the real
roots once, from the package's own filesystem location — a path computation, not
an import, so `integrations/` still never imports `capabilities/` and
`make check-imports` stays green.

## 8. Scenario package named `integration_scenarios`, not `integrations`

`tests/synthetic/integrations/` shadowed the top-level `integrations` package:
pytest puts `tests/synthetic/` on `sys.path` (no `__init__.py` in the test
directories), so `from integrations._base...` inside that package resolved to
itself. Renamed to `tests/synthetic/integration_scenarios/`, which is what
`SCENARIO_ROOT_PARTS` points at. Adding `__init__.py` files to the test tree
would have fixed it too and would have changed collection behaviour repo-wide,
which is a bigger change than the name.

`tests/unit/integrations/test_catalogue.py` was likewise renamed to
`test_integration_catalogue.py` — pytest refuses two test modules with the same
basename when the directories are not packages, and
`tests/unit/platform/config_service/test_catalogue.py` already existed.

## 9. `--live` verification runs from the CLI, not from the CI script

FR-012 says verification is invocable from the CLI, the console, and CI, and the
three want different things.

- **CLI** — `ninjasre integrations verify <name>` already existed and reaches
  each vendor's verifier through `CredentialVerification`. Its connectivity
  answer is unchanged; the permission-aware report is reached through
  `VerificationRunner`.
- **Console** — `GET /v1/integrations` now returns the catalogue (category,
  capabilities, credentials, permissions, regions, health, parity) rather than a
  name and a host list, which is FR-022. The console client already reads that
  route, so the richer fields flow through without a console change.
- **CI** — `make check-integrations` (new) runs the half that needs no
  credentials: parity, verifier completeness, and that every declared permission
  is probed and names capabilities that exist. `--live` prints why a live run
  needs a composed deployment rather than a script, and points at the CLI.

The CI script does *not* make live vendor calls, and that is the design rather
than a gap: FR-016 requires a live failure to mark the integration degraded
rather than fail the build, and a check inside `make verify` that could not fail
the build would be a check with no effect. The degrade-rather-than-fail loop is
exercised end to end in
`tests/contract/integrations/test_a_vendor_break_degrades_rather_than_fails.py`,
and the ledger it writes to is what `GET /v1/integrations` renders.

## 10. Test-first sequencing

Phase 1's parameterised contract suite and the catalogue-wide no-credential test
landed first and were confirmed red (`ModuleNotFoundError: integrations._catalogue`),
which is the intended failure for a suite written against a catalogue that does
not exist yet. Every subsequent module's tests were written before the module —
`test_verification_framework.py` before `_verification/`,
`test_integration_catalogue.py` before `_catalogue/`,
`test_scaffold_integration.py` before `tools/scaffold_integration.py`.

Two exceptions, both stated plainly: `_base/pagination.py`'s three styles,
`_base/regions.py`, and `_base/schema.py` were written before their unit tests,
because the Phase 1 contract suite already covered the properties FR-005 and
FR-007 assert and the unit tests are the finer-grained second pass. The two
scaffold assertions that failed on first run
(`TOOL_NAME = "..."` versus `name="..."`, and the exact wording of the
side-effect comment) were wrong in the *test*, not in the scaffold, and were
corrected there.

## 11. `docs/provenance-map.md` (T054) not touched

Per `CLAUDE.md`, that file is gitignored and never linked from a committed file.
Editing the local, uncommitted copy would have no effect on what ships, so it
was left alone. There is no `make check-provenance` target in this repository.

## 12. Definition of done

| Item | Where it is satisfied |
|---|---|
| SC-001 — scaffold-to-passing-suite measured on three shapes | §1 above; three shapes, 40–55 minutes each |
| SC-002 — adding an integration edits zero existing files | `test_scaffolding_edits_no_existing_file` compares every pre-existing file's bytes |
| SC-003 — every catalogued integration passes the suite | `tests/contract/integrations/` — 132 passing rows over the catalogue |
| SC-004 — no integration client can read a credential | `test_no_integration_can_read_a_credential.py` + per-integration post-call slot inspection |
| SC-005 — verifiers name specific missing permissions | `test_verification_names_what_is_missing.py`, per integration, through the real proxy |
| SC-006 — a vendor break degrades rather than failing silently | `test_a_vendor_break_degrades_rather_than_fails.py` |
| SC-007 — all eleven templates produce valid skills | `test_domain_templates.py`, run through the real capability validator |
| `make verify` green | 5,538 passed, 15 skipped, 0 failed |

`make verify` was green with no pre-existing failures before this feature's
commit and is green after it. Test count: 4,223 → 5,538 passed. Most of the
increase is parametrisation: six new capabilities and three new skills add rows
to suites that already walked the catalogue, which is the property the whole
feature is about.
