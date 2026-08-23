# Tasks — 001 Platform Foundation

`[P]` marks tasks with no dependency on another unfinished task in the same phase.

## Phase 1 — Skeleton and toolchain

- **T001** Create the package tree: `config/`, `core/`, `platform/`,
  `integrations/`, `capabilities/`, `gateway/`, `surfaces/`, each with
  `__init__.py`.
- **T002** [P] Author `pyproject.toml`: project metadata, Python `>=3.12`,
  `uv` configuration, package discovery excluding root `tools/` and `tests/`.
- **T003** [P] Author `ruff.toml`: line length 100, rule selection, per-file
  ignores for `__init__.py` re-exports.
- **T004** [P] Author `mypy.ini`: strict mode over the seven first-party packages;
  `tests/` excluded from the CI gate but runnable on demand.
- **T005** [P] Author `pytest.ini`: test paths, markers (`unit`, `architecture`,
  `contract`, `integration`, `synthetic`, `e2e`), `asyncio_mode`.
- **T006** Author `Makefile` with targets `install`, `lint`, `format`,
  `format-check`, `typecheck`, `test`, `check-imports`, `check-provenance`,
  `check-constants`, `check-protocols`, `check-deps`, `verify`, `clean`, `help`.
- **T007** `platform/__init__.py` re-exposing the stdlib `platform` module.
- **T008** Regression test asserting `import platform` from a third-party context
  resolves to the stdlib (`platform.system()` returns a value).
- **T009** Verify `make install` and `make verify` on Linux, macOS, and Windows
  (Git Bash). Record timings against SC-001 and SC-002.

## Phase 2 — Architecture enforcement (test-first)

- **T010** Create `tests/architecture/fixtures/` containing six deliberately
  violating module trees, one per contract, each isolated so it is never imported
  by the real package graph.
- **T011** Write `tests/architecture/test_import_contracts.py` asserting each
  fixture produces a **distinct named** `import-linter` failure. Confirm all six
  fail before any contract exists.
- **T012** Author `.importlinter` with the `layers` contract.
- **T013** Add the `config-is-a-leaf` forbidden contract.
- **T014** Add `integrations-below-capabilities` and `integrations-below-tier1`.
- **T015** Add `capabilities-below-tier1`.
- **T016** Add `tier1-peers-independent`.
- **T017** Add `tier3-below-tier2` (blocks `core`/`platform` importing tier 2).
- **T018** Wire `make check-imports`; confirm T011 now passes with six distinct
  named failures.
- **T019** Test asserting the contract count in `.importlinter` matches the rule
  count in the `docs/architecture.md` tier table (SC-003).
- **T020** Test asserting a `core ↔ platform` cross-import passes all contracts.

## Phase 3 — Configuration tier

- **T021** `config/constants/paths.py`: `NINJASRE_HOME_DIR`, config, cache, and
  data directory resolution, XDG-aware with a Windows fallback.
- **T022** [P] `config/constants/llm.py`: provider env-var names, default model
  identifiers, timeout and retry defaults.
- **T023** [P] `config/constants/investigation.py`: placeholders for the guardrail
  constants feature 004 will populate (`MAX_INVESTIGATION_LOOPS`,
  `MAX_AGENT_TOOL_SCHEMAS`, `MAX_STAGNANT_ITERATIONS`,
  `MAX_SECONDARY_FALLBACK_TOOLS`, `MAX_SUBAGENT_DEPTH`,
  `MAX_PARALLEL_TOOL_CALLS`).
- **T024** [P] `config/constants/persistence.py`: database URL env name, pool
  sizing, migration table name.
- **T025** [P] `config/constants/security.py`: vault, proxy, and masking env names.
- **T026** [P] `config/constants/surfaces.py`: port defaults and surface identifiers.
- **T027** `config/constants/__init__.py` re-exporting every domain module with an
  explicit `__all__`.
- **T028** `config/prompts/__init__.py` with the prompt-constant convention
  documented in a module docstring.
- **T029** Write `tools/check_constants.py`: AST scan failing on an env-var name
  string literal (matching `NINJASRE_*` or a known vendor pattern) outside
  `config/constants/`. Write its test first.
- **T030** Wire `make check-constants`.

## Phase 4 — Licence and attribution

- **T031** `LICENSE` — Apache 2.0 full text carrying NinjaSRE's own copyright.
- **T032** `NOTICE` — copyright lines and licence reference for the prior work,
  paired with the `README.md` "Built on" section. These two are the only places
  attribution appears (FR-011).
- **T033** Audit every committed file: none may name a prior project, and none
  may link to `specs/`, `docs/provenance-map.md`, or any other uncommitted path
  (FR-012).
- **T034** Point `tests/architecture/test_contract_coverage.py` at the tier table
  in the root `AGENTS.md` instead of `docs/architecture.md`, so the check cannot
  skip on a clean checkout. This is what FR-012 exists to prevent.
- **T035** Gitignore the planning material: `specs/`, `docs/provenance-map.md`,
  and `CLAUDE.md`.
- **T036** Record the decision in `docs/adr/0011-attribution-in-readme-only.md`
  and amend Constitution Article XIII to 2.0.0, per the constitution's own
  Governance section.

## Phase 5 — Guard checks

- **T037** Write `tools/check_dependencies.py`: resolve the runtime dependency tree
  and fail on a deny-list match (`posthog`, `sentry-sdk`, `analytics-python`,
  `mixpanel`, `segment-analytics-python`, `amplitude-analytics`). Optional extras
  are exempt. Test first.
- **T038** Wire `make check-deps` (SC-005).
- **T039** Write `tools/check_protocol_bodies.py`: AST scan failing on `...`,
  `pass`, or `raise NotImplementedError` in a `Protocol` method body, and on a
  docstring followed by a trailing `...`/`pass`. Test first.
- **T040** Wire `make check-protocols`.
- **T041** Compose `make verify` from all checks plus lint, format-check,
  typecheck, and unit tests. Confirm SC-002 timing.

## Phase 6 — Developer experience

- **T042** `platform/observability/logging.py`: `structlog` configured once with
  JSON and console renderers selected by environment; a `get_logger(__name__)`
  helper. No module configures logging itself.
- **T043** Test asserting no module besides `logging.py` calls
  `structlog.configure` or `logging.basicConfig`.
- **T044** Root `AGENTS.md`: repo map, tier table, code style, file-placement rules,
  footguns, links to per-package files.
- **T045** [P] Per-package `AGENTS.md` stubs for `core`, `platform`,
  `integrations`, `capabilities`, `gateway`, `surfaces`.
- **T046** Write `tools/scaffold_package.py`: generate a package in a named tier
  with `__init__.py`, `AGENTS.md`, test directory, and a provenance header
  template. Test first.
- **T047** `.pre-commit-config.yaml` running `ruff`, `ruff format`, and
  `check-imports` on changed files.
- **T048** [P] `.editorconfig`, `.gitattributes`, `.gitignore`.
- **T049** `.github/workflows/verify.yml` running `make verify` on the three
  platforms.
- **T050** Re-run the T033 audit over the final tree, and confirm the commit
  history carries nothing the audit rejects — commit messages included.

## Definition of done

- [x] `make verify` green on Windows; the three-platform workflow covers Linux
      and macOS on the first push
- [x] All six boundary-violation fixtures produce distinct named failures (SC-004)
- [x] Contract count matches the tier table in `AGENTS.md` (SC-003)
- [x] `mypy --strict` clean with no `type: ignore` (SC-006)
- [x] Telemetry deny-list check green (SC-005)
- [x] `make install` 4.8 s, `make verify` 11.0 s (SC-001, SC-002)
- [x] `LICENSE` and `NOTICE` in place
- [x] No committed file names a prior project or links to an uncommitted path
