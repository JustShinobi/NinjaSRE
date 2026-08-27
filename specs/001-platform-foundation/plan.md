# Plan — 001 Platform Foundation

## Summary

Create the repository skeleton with four tiers, wire `import-linter` contracts
that fail CI on any boundary violation, establish the `uv`/`ruff`/`mypy`/`pytest`
toolchain behind a single `make verify` gate, seed the `config/` tier, and add the
constants, protocol-body, and telemetry-deny checks.

## Technical context

| Aspect | Choice |
|---|---|
| Language | Python 3.12+ |
| Environment / packaging | `uv` with `pyproject.toml` and `uv.lock` |
| Lint + format | `ruff` (line length 100, `ruff format`) |
| Type checking | `mypy` strict over all first-party packages |
| Tests | `pytest` with `pytest-cov`; async via `pytest-asyncio` |
| Architecture enforcement | `import-linter` |
| Logging | `structlog`, configured once in `platform/observability/logging.py` |
| Task runner | `make` (GNU Make; Windows via the bundled Git Bash or `mise`) |
| Pre-commit | `pre-commit` running the fast subset of `make verify` |

## Constitution check

| Article | How this plan satisfies it |
|---|---|
| I — Evidence over assertion | N/A at this layer; the logging foundation carries structured context for later evidence trails |
| II — Bounded autonomy | Establishes `config/constants/` as the single home for every bound introduced later (FR-009) |
| III — Read-only by default | N/A |
| IV — Secrets never reach the agent | Telemetry deny-list (FR-014) and the constants rule prevent secret names leaking into arbitrary modules |
| V — One canonical runtime | N/A |
| VI — Provider neutrality | No vendor SDK enters the base dependency set |
| VII — Learning is measured | N/A |
| VIII — Layered architecture | **This is the feature.** FR-001 to FR-006 |
| IX — Capabilities declared | Scaffold command (FR-019) makes the compliant path the default path |
| X — Operator owns their data | FR-014 deny-list enforced from the first commit |
| XI — Single datastore | No storage in this feature; the tier layout reserves `platform/persistence/` |
| XII — Test-first | Boundary-violation fixtures (SC-004) are written before the contracts |
| XIII — Language and attribution | FR-011 to FR-013. The article was amended to 2.0.0 during this feature — see Complexity Tracking |

**Violations:** none outstanding. One amendment, recorded in ADR 0011.

## Project structure

```
ninjasre/
├── config/
│   ├── __init__.py
│   ├── constants/
│   │   ├── __init__.py          # re-exports every domain module
│   │   ├── paths.py             # NINJASRE_HOME_DIR and friends
│   │   ├── llm.py
│   │   ├── investigation.py
│   │   ├── persistence.py
│   │   ├── security.py
│   │   └── surfaces.py
│   └── prompts/
│       └── __init__.py
├── core/
│   ├── __init__.py
│   └── AGENTS.md
├── platform/
│   ├── __init__.py              # re-exposes stdlib platform
│   ├── observability/
│   │   └── logging.py
│   └── AGENTS.md
├── integrations/
│   ├── __init__.py
│   └── AGENTS.md
├── capabilities/
│   ├── __init__.py
│   └── AGENTS.md
├── gateway/
│   ├── __init__.py
│   └── AGENTS.md
├── surfaces/
│   ├── __init__.py
│   └── AGENTS.md
├── tools/                       # repo tooling, NOT a runtime package
│   ├── check_constants.py
│   ├── check_protocol_bodies.py
│   ├── check_dependencies.py
│   └── scaffold_package.py
├── tests/
│   ├── architecture/            # boundary-violation fixtures
│   ├── unit/
│   └── conftest.py
├── .importlinter
├── pyproject.toml
├── ruff.toml
├── mypy.ini
├── pytest.ini
├── Makefile
├── .pre-commit-config.yaml
├── AGENTS.md
├── NOTICE
└── LICENSE
```

Note: `tools/` at the root holds **repository tooling** and is excluded from
`import-linter` and from the distributed package. Agent-callable capabilities live
in `capabilities/`, never here — this differs from the upstream layout, where
`tools/` was the agent-callable package, and the rename is deliberate to remove
the ambiguity.

## Import contracts

`.importlinter` defines seven contracts, each independently failing:

| Contract | Type | Rule |
|---|---|---|
| `layers` | `layers` | `surfaces,gateway` > `capabilities` > `integrations` > `core,platform` > `config` |
| `config-is-a-leaf` | `forbidden` | `config` may not import any first-party package |
| `integrations-below-capabilities` | `forbidden` | `integrations` may not import `capabilities` |
| `integrations-below-tier1` | `forbidden` | `integrations` may not import `surfaces` or `gateway` |
| `capabilities-below-tier1` | `forbidden` | `capabilities` may not import `surfaces` or `gateway` |
| `tier1-peers-independent` | `forbidden` | `surfaces` and `gateway` may not import each other |
| `tier3-below-tier2` | `forbidden` | `core` and `platform` may not import `capabilities` or `integrations` |

The `layers` contract alone would permit `core → platform` and forbid the reverse.
Because they are siblings, they are declared as a single layer
(`core,platform`) and the explicit `tier3-below-tier2` contract carries the real
restriction.

## Implementation phases

### Phase 1 — Skeleton and toolchain
Package tree, `pyproject.toml` with `uv`, `ruff.toml`, `mypy.ini`, `pytest.ini`,
`Makefile` with `install` / `lint` / `format` / `typecheck` / `test` / `verify`.

### Phase 2 — Architecture enforcement (test-first)
Write the six violation fixtures under `tests/architecture/` first and confirm they
fail. Then author `.importlinter`, wire `make check-imports`, and confirm each
fixture produces a distinct named failure.

### Phase 3 — Configuration tier
`config/constants/` domain modules with the re-export pattern, `config/prompts/`,
and the `check_constants.py` tool that fails on env-var literals outside the tier.

### Phase 4 — Licence and attribution
`LICENSE`, `NOTICE`, and the README section that together carry the whole
attribution. Then the audit that nothing else does, and the repointing of the
contract-coverage test onto a committed file.

### Phase 5 — Guard checks
`check_dependencies.py` (telemetry deny-list), `check_protocol_bodies.py` (AST scan
for non-docstring Protocol bodies), and wiring both into `make verify`.

### Phase 6 — Developer experience
`platform/observability/logging.py`, root and per-package `AGENTS.md`,
`scaffold_package.py`, `.pre-commit-config.yaml`, and cross-platform verification
of the whole gate.

## Complexity tracking

| Item | Justification |
|---|---|
| `platform/` shadowing the stdlib name | Precedented in prior art and already proven to work; the alternative (`platform_services/`) reads worse in every import. A regression test pins stdlib resolution, and `tests/conftest.py` rebinds the name because pytest imports the stdlib module while bootstrapping. |
| Root `tools/` reserved for repo tooling | Prevents the recurring confusion between agent-callable tools and build scripts. Excluded from packaging and from import contracts. |
| Six separate contracts instead of one `layers` contract | A single contract produces one opaque failure. Separate contracts name the specific rule broken, which is the difference between a five-minute and a fifty-minute fix. |
| `tier1-peers-independent` is an `independence` contract, not `forbidden` | A `forbidden` contract cannot express a mutual rule in one named contract, and naming one rule per failure is the point of splitting them. |
| `tools/` added to the mypy gate | Not in the original scope. It caught a real narrowing bug in the AST helper on the first run, and costs nothing. |
| `config/constants/observability.py` added | A seventh domain module. Without it the logging module would have to write `NINJASRE_LOG_LEVEL` inline, which `check-constants` rejects — the rule working as intended. |
| Constitution Article XIII amended, 1.0.0 → 2.0.0 | The article required per-file provenance headers and an enforced map. Both were built, and both proved to restate one fact in many drifting places while the validating check read a file outside the committed tree — so it skipped rather than failed on a clean checkout. Recorded in ADR 0011. |

## Provenance

| Adopted from | Upstream path | Disposition |
|---|---|---|
| Tracer | `.importlinter`, `.importlinter.strict` | ADAPT — contracts rewritten for the NinjaSRE package names |
| Tracer | `ruff.toml`, `mypy.ini`, `pytest.ini`, `Makefile` | ADAPT — toolchain configuration |
| Tracer | `AGENTS.md` code-style and file-placement sections | ADAPT — repo-specific content rewritten |
| Tracer | `config/constants/` organisation pattern | ADOPT |
| Tracer | CodeQL footgun documentation | ADAPT — informs `check_protocol_bodies.py` |
| Swapnil | `ruff.toml` | REFERENCE |

## Risks

| Risk | Mitigation |
|---|---|
| Strict contracts slow early development | The tier assignment is decided in `docs/architecture.md`; contributors consult a table, not their judgement. Scaffold command places code correctly by default. |
| Windows `make` friction | `Makefile` targets are POSIX-shell only and verified under Git Bash in CI; a `mise` task alias is provided as an alternative entry point. |
| Provenance check produces false positives | The map is the source of truth and the allow-list is explicit. The check reports both directions (missing header, orphan header) so drift is visible immediately. |
