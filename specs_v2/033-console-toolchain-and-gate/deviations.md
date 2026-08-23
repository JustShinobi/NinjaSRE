# Deviations — 033 Console Toolchain and Quality Gate

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

## 1. Phase 8 (retirement) is not done, and could not be

`tasks.md` marks Phase 8 *"gated on 034–037 reaching parity"*. Those features do
not exist yet — 034 is the design system, 035 the application shell, 036 the data
surfaces, 037 the live layer, and none of them has been implemented. The new
console at the end of this feature renders one screen: a run list, built so that
the gate has something real to lint, type-check, build, drive a browser against
and screenshot.

So T-026 (the parity checklist), T-027 (remove `surfaces/console/`), T-028
(update the image, chart, entry point and constants) and T-030 (assert the
compose bring-up serves the new build) are **not done**. Removing the Python
console now would delete every screen the first wave shipped and replace them
with one, which is the opposite of what FR-017 asks for: *"once the new console
reaches parity on every screen the first wave shipped"*.

FR-019's second half — the deployment stays a single-host compose bring-up — is
untouched and still holds, because nothing about the deployment changed.

**T-029 is done.** The import contract FR-020 asks for exists now rather than at
retirement: `tools/check_console_boundary.py`, run by `make verify` through
`make check-console-boundary`, enforcing both directions with violation fixtures
in `tests/unit/tools/test_check_console_boundary.py`. It is in place before the
console it polices grows, which is the same argument the plan makes for landing
the gate before the console.

Why a script rather than an `import-linter` contract: `import-linter` resolves
`root_packages` as importable Python packages. `console/` is not one, and giving
it an `__init__.py` so a contract could name it would create exactly the thing
the contract exists to forbid. The tier table's `console` row therefore declares
a script instead, and `tests/architecture/test_contract_coverage.py` was extended
to hold a script-enforced row to the same standard: the script must exist, and
`verify` must run it.

## 2. `make verify` skips the two infrastructure-dependent checks, by policy

FR-005 says `make verify` must run format, lint, type check, unit tests, build,
end-to-end and visual regression. FR-009 says the gate must run on all three
platforms the CI workflow covers. Those two are in tension, and this is how it
was resolved.

The end-to-end suite needs a browser binary and a Node toolchain; the visual
suite needs a Linux container image (FR-014 — *one* pinned image, because a
capture from anywhere else is meaningless). The hosted macOS runner has no
container runtime and the hosted Windows runner runs Windows containers, so
"visual regression on all three platforms" is not a thing that can be made true.

What ships:

- `make verify` runs **every** check, including both of those.
- On a machine that cannot run one, `tools/console_gate.py` prints a named skip
  and succeeds — the pattern the Makefile already documents for the chaos and
  cloud suites: *"a suite that went red on every laptop is a suite somebody
  deletes"*.
- **CI sets `NINJASRE_CONSOLE_TOOLCHAIN=required` on every `verify` job**, on all
  three platforms, which turns a skip into a failure. So the toolchain, the
  static checks, the unit suite, the build and the end-to-end suite are enforced
  on all three.
- The visual comparison gets its own Linux job (`console-visual`), also with
  `required` set, which publishes the diff images on failure.

Three things are never skipped, whatever the machine: a lockfile that has drifted
from its manifest, a committed API client that differs from a fresh generation,
and any check that ran and failed. Those are the three that would otherwise be
silently lost to a skip.

## 3. The gate's end-to-end backing is the mock data plane, not compose

FR-013 says the end-to-end tests must run against a real gateway with a real
database, provisioned by the deployment's own compose definition. NFR-003 says
the suite must be deterministic. Feature 032 — the other foundation this wave
stands on, landed in the commit immediately before this one — exists precisely to
make both true at once: the committed dataset shifts every timestamp to one fixed
instant, and the constants tier says why, verbatim: *"so that two runs of the
pipeline produce identical output and a visual-regression baseline compares code
against code rather than clock against clock."*

Both backings are implemented in `tools/console_e2e.py`:

- `--backing mock` serves the committed dataset through `tools.mockplane`. This
  is what `make verify` runs, and what `make console-e2e-sweep` runs twenty times
  (T-017).
- `--backing compose` brings up `deploy/compose/docker-compose.yml` unmodified —
  the same file an operator runs, with no test-only override — and drives the
  same suite against it. It has its own CI job, `console-e2e-compose`, because it
  builds four images and brings up a stack.

So FR-013 is satisfied and runs on every pull request; what changed is that it is
not the backing the gate itself uses, because a four-image build inside
`make verify` is the risk the plan's own risk table names first.

## 4. The design references were copied into the repository

T-021b and the definition of done both require the visual baselines to be checked
against the mockups in `../_design/`. `specs_v2/` is gitignored in its entirety,
and `CLAUDE.md`'s rule behind the rules is explicit: *"A committed file must not
depend on an uncommitted one... If a committed file needs a fact from a planning
document, state the fact in the committed file instead of pointing at where it is
written down."*

So the eight design references were copied to `console/visual/mockups/` (2.1 MB)
and are committed. `console/visual/screens.json` is the registry, and
`tests/contract/console/test_console_visual_coverage.py` is the enforcement.

## 5. The coverage claim T-021b asks for cannot be true yet, and says so

T-021b asks that every screen with a mockup have a committed baseline, failing by
name otherwise. Taken literally that is unsatisfiable today: the screens those
mockups describe are built by features 034 to 037, and a test demanding baselines
for screens nobody has written would be red from the moment it landed — which is
the one thing the task instructions rule out.

What is implemented is the mechanism, with the gap made explicit rather than
hidden:

- a reference in `console/visual/mockups/` that appears nowhere in the registry
  **fails the suite by name** — so a design cannot arrive and be forgotten, which
  is the failure T-021b exists to prevent;
- a reference marked `pending` must name the surface that will implement it, so
  each of the seven outstanding ones is a plan with an owner rather than a
  silence;
- a screen marked `baselined` must have a committed baseline **and** an
  acceptance record naming the reference it was first reviewed against (T-021a) —
  or, where there is no reference, a sentence of prose saying why, which a
  reviewer can argue with;
- a baseline with no registered screen fails too.

The one screen this feature ships, `runs`, is baselined with an acceptance record
whose `against` is `null` and whose `reason` says it is not one of the designed
screens and is expected to be replaced rather than restyled. That is honest: it
would have been trivial and false to point it at `03-screen-dashboard.png`.

When 034 to 037 land, each moves its references from `pending` to a screen with
an acceptance record, and the same tests then hold the literal claim T-021b
makes.

## 6. Node is used from `PATH` when it is already exactly the pinned version

FR-002 pins Node, pnpm and the browser; FR-003 asks for provisioning that needs
no pre-existing Node. Both hold. `ensure_node` prefers a `node` already on `PATH`
**only when it reports exactly the pinned version** — not "at least", because a
machine one patch ahead is a machine whose failures nobody else can reproduce.
Otherwise it downloads the official archive and refuses it unless it hashes to
the digest committed in `console/toolchain.lock.json`.

This was a deliberate addition rather than a shortcut: it is the air-gapped case.
An operator who installed the pinned Node themselves gets to keep it, and
`NINJASRE_NODE_MIRROR` moves the download without moving the digest it has to
match.

## 7. `platform.system()` could not be used, and the reason is the repository's

`tools/console_toolchain.py` needs this machine's operating system and
architecture. `import platform` in this repository resolves to the first-party
tier, not the standard library — the footgun `AGENTS.md` documents — and no
amount of aliasing changes which module it is. `mypy` caught it immediately.

The platform key is therefore derived from `sysconfig.get_platform()`, which
needs no import that collides, and six parametrised cases in
`tests/unit/tools/test_console_toolchain.py` pin the mapping from what Python
calls a platform to what Node calls one.

## 8. The lint rule against type assertions was relaxed once, deliberately

The console's lint configuration was first written with
`consistent-type-assertions: { assertionStyle: 'never' }`. That is unworkable
against `Response.json()`, which is typed `Promise<any>`: every typed fetch
wrapper needs exactly one assertion at the seam where an untyped wire format
becomes a typed one.

The rule is now `assertionStyle: 'as'` with `objectLiteralTypeAssertions: 'never'`
— the two kinds that hide a mistake rather than narrow a value — and there is
exactly one assertion in `console/src/`, at that seam, with a comment saying what
makes it safe (the client is generated from the gateway's own document and the
gate compares it against a fresh generation). `typescript-eslint`'s
`strictTypeChecked` set still forbids `any` and every unsafe operation on one.

## 9. Framework choice, and why it was decided here rather than in 035

`plan.md` for this feature names only "a fast in-process runner with a DOM
environment" and "a browser driver". Feature 035's plan names Next.js App Router,
and 034's names Tailwind with a token-only theme. Since this feature exists to
give those features a toolchain, the toolchain is theirs: Next.js 16 with the App
Router, React 19, Tailwind 4, TypeScript 5.9 strict, Vitest with jsdom,
Playwright, and `openapi-typescript` for the client.

Two consequences worth stating plainly. The build is `output: 'standalone'`, so
what the browser tests drive is the artefact a deployment runs rather than a
development server. And `basePath` is read from `NINJASRE_CONSOLE_BASE_PATH` at
build time, which is FR-022.

## 10. Task-by-task notes

- **T-002 (browser binaries pinned).** Pinned by `@playwright/test`'s exact
  version in the manifest and by the capture image's digest in
  `toolchain.lock.json`; a test asserts the two name the same browser version.
  The binary itself is fetched by `playwright install`, which is version-locked
  by the package — there is no published digest per browser build to commit.
- **T-011 (commit a copy of the OpenAPI document, and a target that refreshes it
  from a running gateway).** Both already existed, from feature 032:
  `fixtures/contract/openapi.json` and `python -m tools.mockplane contract`, with
  a drift check that compares the committed copy against what `create_app`
  generates. Adding a second copy under `console/` would have been two documents
  and one of them stale. The console generates from the existing one.
- **T-016 (network audit).** `console/tests/e2e/network.spec.ts` watches every
  request a production build issues and fails on any host that is not loopback.
  It runs in the gate, not only in CI.
- **T-021 (acceptance as a reviewable change).** `make console-visual-accept`
  rewrites committed PNGs; there is no flag on the comparison that accepts them.
  The acceptance is the commit.
- **T-024 (parallelise console and Python checks).** Not done as parallelism
  *inside* `make verify`, and deliberately: GNU Make's `-j` over a recipe list
  interleaves output, and a gate whose failure message is shredded across two
  streams is a gate people re-run serially to read. The parallelism is at the
  job level instead — `console-visual`, `console-e2e-compose` and `verify` are
  separate CI jobs that run at the same time, which is where the wall-clock
  saving actually is.
- **T-025 (assert the budgets).** `tools/measure_verify.py`, run by the
  `console-budget` job for both profiles. It distinguishes three outcomes, which
  matters: the gate failed (1), the gate passed but was slow (2), and fine (0) —
  "the gate is red" and "the gate is slow" are different problems for different
  people.

## 11. Test-first sequencing

Followed per module, for the reason features 020 and 021 both give: a suite
written against modules that do not exist yet can only fail on `ImportError`,
which proves nothing.

`tests/unit/tools/test_console_toolchain.py` was written and confirmed red
against a missing `tools.console_toolchain` before the module existed, then red
on a missing lockfile before `pnpm install` produced one. The boundary check's
violation fixtures were written before the check. Every seeded gate failure in
`console/fixtures/` was watched failing its check before the test asserting it
was believed — including the two that initially did not fail for the right
reason: the lint fixture's third-party origin was also present in three unit
tests (fixed by using a loopback address there, which keeps the rule sharp), and
the format fixture passed until the console tree itself was formatted.

Two real defects were found this way rather than by reading:

- `next.config.ts` declared an `eslint` key that Next 16 removed, which only
  `tsc` caught;
- the unit suite passed one file at a time and failed together, because
  `@testing-library/react`'s auto-cleanup only fires when the runner exposes
  globals and this one deliberately does not. Fixed in `tests/unit/setup.ts`
  with a comment saying why, rather than by turning globals on.

## 12. Where each criterion is proven

`tests/contract/console/test_console_success_criteria.py` is the map, and it
fails when a proof is renamed or deleted rather than quietly ceasing to cover
anything.

| Criterion | Where it is proven |
|---|---|
| SC-001 | `make verify` runs the console half; `test_the_gate_runs_every_console_check` asserts nothing sits outside it, and `test_every_check_is_individually_runnable_from_the_makefile` covers FR-006 |
| SC-002 | `test_console_gate.py` — five seeded failures, each spliced in, run for real, required to fail *and* to name the file; plus the paired test that each check passes once the fixture is gone, so none of them is simply always red. The pixel half is `test_a_seeded_pixel_change_fails_the_run_and_emits_a_diff`, which also asserts a diff image exists |
| SC-003 | `test_a_stale_committed_client_fails_the_build`, which additionally asserts the check did not rewrite the committed client on its way past |
| SC-004 | `test_the_gate_runs_on_every_platform_the_workflow_covers` — the three-platform matrix, with `NINJASRE_CONSOLE_TOOLCHAIN=required` so none of them can skip the console half; plus `test_provisioning_is_cached_on_the_files_that_decide_what_it_is` for NFR-004 |
| SC-005 | Half done. The contract exists and is enforced (`test_the_repository_keeps_the_boundary`, with a violation fixture in each direction). The retirement it will police is blocked — §1 |
| SC-006 | `console/tests/e2e/network.spec.ts`, run by the gate against the standalone build; `test_a_production_build_is_audited_for_third_party_requests` asserts the audit still watches requests |
| SC-007 | `tools/measure_verify.py` and the `console-budget` job, with `test_the_declared_budgets_are_the_ones_the_measurement_uses` and `test_a_slow_gate_and_a_failed_gate_are_different_verdicts` |

## 13. Gate

`make verify` green: 9,688 passed, 20 skipped, in 2m57s for the Python suite —
plus the console half, which ran format, lint, type check, unit tests at 94%
statement coverage against a floor of 90, the API client drift check, the
standalone production build, three browser tests against the committed dataset,
and the visual comparison inside the pinned image. The working tree is clean
afterwards: the gate writes nothing that is not ignored.

`make console-e2e-sweep` (T-017): twenty consecutive runs, sixty browser tests,
no flake, exit 0.

109 of those 9,688 are this feature's own, across seven modules; the rest of the
suite is unchanged and nothing in it was touched except
`tests/architecture/test_contract_coverage.py`, which had to learn about a tier
table row a guard script enforces (§1). The console's own suite adds 16 more,
run by `make console-test` rather than by pytest.
