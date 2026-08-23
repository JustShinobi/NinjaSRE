# Tasks — 036 Console Toolchain and Quality Gate

## Phase 1 — Layout and provisioning

- **T-001** Create `console/` at the repository root with its manifest and
  committed lockfile.
- **T-002** Pin the Node version, the package manager version and the browser
  binaries; record them where both the make target and CI read them.
- **T-003** Idempotent `make console-setup` that provisions the toolchain without
  a pre-existing Node installation.
- **T-004** Failing test: a lockfile out of date with the manifest fails the
  build rather than being updated silently.
- **T-005** Add the `console/` row to the tier table in `AGENTS.md`.

## Phase 2 — Static checks

- **T-006** Seed fixtures: a type error, a lint violation, a format violation.
- **T-007** Format check, lint and type check targets; each fails on its fixture
  and names file and line.
- **T-008** Wire all three into `make verify`; assert `make verify` fails on each
  fixture and passes with them removed.

## Phase 3 — Unit tests and coverage

- **T-009** Unit test runner with a DOM environment; a seeded failing test fails
  `make verify`.
- **T-010** Coverage reporting against a declared threshold, enforced.

## Phase 4 — Client generation

- **T-011** Commit a copy of the gateway's OpenAPI document and a target that
  refreshes it from a running gateway.
- **T-012** Generation target producing the committed client, runnable offline.
- **T-013** Failing test: a stale committed client fails the build.

## Phase 5 — End-to-end

- **T-014** Compose-backed stack for tests, reusing the deployment's own compose
  definition, with seeded data and a controlled clock.
- **T-015** Browser driver wired to the stack; a seeded failing end-to-end test
  fails `make verify`.
- **T-016** Network audit asserting a production build issues no third-party
  request.
- **T-017** Determinism sweep: run the suite twenty times; any flake is fixed or
  demoted to a unit test, never disabled.

## Phase 6 — Visual regression

- **T-018** Pinned capture container image; baseline storage layout.
- **T-019** Capture and compare targets running only inside that image.
- **T-020** Failing test: a seeded pixel change fails the run and emits a diff
  image artefact.
- **T-021** Baseline acceptance as a reviewable committed change, not a flag.
- **T-021a** Add a **fidelity review** step to the baseline-acceptance workflow:
  the first baseline captured for any screen covered by `../_design/` is accepted
  only against the corresponding mockup, and the acceptance change records which
  mockup it was compared to. This is what turns "the design must match the
  mockups" from an intention into a gate — after the first acceptance, ordinary
  visual regression keeps it matched.
- **T-021b** Coverage test: every screen with a mockup in `../_design/` has a
  committed visual baseline. A mockup with no baseline fails the suite, naming
  the screen.

## Phase 7 — CI

- **T-022** Extend the three-platform workflow with the console gate.
- **T-023** Cache provisioning so a run that changes no dependency does not
  reinstall.
- **T-024** Parallelise console and Python checks where they do not contend.
- **T-025** Assert the cold and warm `make verify` budgets in CI.

## Phase 8 — Retirement *(gated on 034–037 reaching parity)*

- **T-026** Parity checklist: every screen the first-wave console shipped, present
  in the new one, verified against the first wave's own acceptance scenarios.
- **T-027** Remove `surfaces/console/` and its tests in one change.
- **T-028** Update the console Docker image, the Helm template, the entry point
  and the surface constants to serve the new build.
- **T-029** Import contract: no Python package imports the console, and the
  console imports no Python. Prove it with a violation fixture.
- **T-030** Assert the single-host compose bring-up still serves the console on
  the configured path behind the existing proxy.

## Definition of done

- SC-001 through SC-007 each proven by a named test.
- Every seeded failure fixture demonstrated to fail `make verify`.
- **Every screen with a mockup in `../_design/` has a committed visual baseline,
  and each baseline's first acceptance records the mockup it was reviewed
  against.** This is the mechanism the fidelity clauses in features 034 to 037
  depend on; without it those clauses are unenforceable.
- Retirement complete, with the import contract enforcing it.
