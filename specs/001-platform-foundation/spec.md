# Feature 001 — Platform Foundation

- **Wave:** 0 — Foundation
- **Branch:** `feat/001-platform-foundation`
- **Status:** Implemented
- **Depends on:** —
- **Blocks:** every other feature

## Summary

Establish the repository skeleton, the four-tier package architecture with
CI-enforced import boundaries, the Python toolchain, the configuration tier, and
the guard checks that keep all of it enforced. Nothing in this feature is
user-facing; everything in the project compiles against it.

## User scenarios

### Primary story

A contributor clones the repository, runs one command, and has a working
development environment. They add a module in the wrong tier, and CI rejects the
change with a message naming the violated boundary — before review.

### Acceptance scenarios

1. **Given** a fresh clone on Linux, macOS, or Windows, **when** the contributor
   runs `make install`, **then** the environment is provisioned and `make verify`
   passes.
2. **Given** a module in `integrations/` that imports from `capabilities/`,
   **when** CI runs, **then** `make check-imports` fails naming both packages and
   the rule violated.
3. **Given** a module in `config/` that imports any other first-party package,
   **when** CI runs, **then** the build fails.
4. **Given** a runtime dependency that transitively pulls in a telemetry package,
   **when** CI runs, **then** `make check-deps` fails naming the package.
5. **Given** a change touching a package with a local `AGENTS.md`, **when** a
   contributor reads it, **then** the package-specific conventions are documented
   there rather than only in the root file.
6. **Given** an env-var name defined outside `config/constants/`, **when** CI runs,
   **then** the constants check fails.

### Edge cases

- A cyclic import between `core/` and `platform/` (permitted as siblings) must not
  trip the layer checker, but a cycle through a *higher* tier must.
- `platform/` deliberately shadows the stdlib `platform` module; `import platform`
  from third-party code must still resolve to the stdlib.
- Windows path handling in the toolchain must not require WSL.
- A check that reads a file absent from a clean checkout must fail, not skip.
  Skipping reports success for work that never ran.

## Requirements

### Functional

- **FR-001** The repository MUST implement the four-tier package layout defined in
  `docs/architecture.md` §1: `config` (tier 4), `core` + `platform` (tier 3),
  `integrations` + `capabilities` (tier 2), `gateway` + `surfaces` (tier 1).
- **FR-002** Import boundaries MUST be enforced by `import-linter` with one
  contract per rule in the tier table, run by `make check-imports` in CI.
- **FR-003** `config/` MUST NOT import any first-party package. This MUST be a
  distinct, independently-failing contract.
- **FR-004** `integrations/` MUST NOT import `capabilities/`, `surfaces/`, or
  `gateway/`. This MUST be a distinct contract.
- **FR-005** `surfaces/` and `gateway/` MUST NOT import each other.
- **FR-006** `core/` and `platform/` MAY cross-import; the checker MUST allow this
  pair and only this pair.
- **FR-007** The toolchain MUST be `uv` (environment and locking), `ruff` (lint
  and format), `mypy` (strict type checking), and `pytest` (tests).
- **FR-008** `make verify` MUST run lint, format check, type check, import check,
  constants check, protocol-body check, dependency check, and the test suite, and
  MUST be the single command CI executes for the quality gate.
- **FR-009** All shared constants and environment-variable names MUST live under
  `config/constants/`, organised by domain, and re-exported from
  `config/constants/__init__.py`.
- **FR-010** A CI check MUST fail if an environment-variable name literal appears
  outside `config/constants/`.
- **FR-011** Attribution for the prior work NinjaSRE draws on MUST be complete in
  `README.md` and `NOTICE`, and MUST NOT be repeated anywhere else in the
  repository — no per-file headers, no map, no asides naming a prior project.
- **FR-012** A committed file MUST NOT depend on an uncommitted one: no link, no
  import, and no test that reads it. Where a committed artefact needs a rule
  written down in planning material, the rule MUST be restated in a committed
  file, and that copy is the source of truth. The tier table in the root
  `AGENTS.md` is the worked example.
- **FR-013** `NOTICE` MUST carry the copyright lines and licence reference the
  Apache 2.0 attribution obligation requires. `LICENSE` MUST be Apache 2.0.
- **FR-014** The runtime dependency set MUST NOT contain any telemetry, analytics,
  or crash-reporting package. A CI check MUST enforce this against a deny-list.
- **FR-015** Structured logging MUST be configured once at the platform level with
  no per-module logging configuration.
- **FR-016** A package MAY carry a local `AGENTS.md` documenting conventions
  specific to that tree; the root `AGENTS.md` MUST link to each.
- **FR-017** The project MUST target Python 3.12+ and MUST run on Linux, macOS,
  and Windows without a compatibility layer.
- **FR-018** Protocol method bodies MUST be docstring-only. A CI check MUST fail on
  `...`, `pass`, or `raise NotImplementedError` in a `Protocol` method body.
- **FR-019** A scaffold command MUST generate a new package in a given tier with
  its `AGENTS.md`, test directory, and provenance header template.

### Key entities

| Entity | Description |
|---|---|
| **Tier** | One of four architectural layers with a declared set of permitted downward imports |
| **Package** | A first-party top-level Python package assigned to exactly one tier |
| **Import contract** | An `import-linter` rule expressing a permitted or forbidden edge between packages |
| **Guard check** | A repository-tooling script wired into `make verify` that fails the build on a named violation |
| **Constant module** | A domain-scoped leaf under `config/constants/` holding env names and shared literals |

## Success criteria

- **SC-001** `make install` completes in under 3 minutes on a cold cache on all
  three platforms.
- **SC-002** `make verify` completes in under 90 seconds on the empty skeleton.
- **SC-003** Every rule in the `docs/architecture.md` tier table has exactly one
  corresponding `import-linter` contract; a test asserts the count matches.
- **SC-004** Deliberately introducing each of the six boundary violations causes a
  distinct, named CI failure. A test fixture proves each.
- **SC-005** Zero runtime dependencies match the telemetry deny-list.
- **SC-006** `mypy --strict` passes with no `type: ignore` in the skeleton.

## Out of scope

- Any agent, LLM, or investigation logic (features 002–005)
- Persistence and migrations (feature 006)
- Deployment artefacts (feature 030)
- CI workflows beyond the quality gate (feature 031)

## Clarifications

| Question | Resolution |
|---|---|
| Does `platform/` shadowing the stdlib cause problems? | It is deliberate and precedented in prior art. The package re-exposes the stdlib module so `import platform` from third-party code resolves normally. A regression test asserts this. The package only wins the name while the repository root leads `sys.path`; pytest imports the stdlib module while bootstrapping, so `tests/conftest.py` rebinds it. |
| Strict or permissive import contracts initially? | Strict from the first commit. Retrofitting boundaries onto an existing tree is the failure mode this feature exists to prevent. |
| Where do prompt strings live? | `config/prompts/` — tier 4, so any tier may read them without a cycle. |
| Why did per-file provenance headers go? | They restated one fact in a hundred drifting places, and the check that validated them read a file outside the committed tree — so on a clean checkout it skipped rather than failed. Recorded in ADR 0011; Constitution Article XIII amended to 2.0.0. |
| What is the source of truth for the tier table? | The root `AGENTS.md`, because it ships with the code that must obey it. `docs/architecture.md` §1 carries the same table with the fuller narrative; the test reads the committed one. |
