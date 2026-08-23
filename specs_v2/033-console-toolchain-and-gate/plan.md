# Plan — 036 Console Toolchain and Quality Gate

## Technical context

| Concern | Choice |
|---|---|
| Location | `console/` at the repository root — a peer of the Python tiers, not inside `surfaces/`, because it is not a Python package and must not appear to be one |
| Package manager | pnpm, version-pinned, lockfile committed |
| Node | Pinned in a version file the provisioning target reads; installed reproducibly by that target |
| Unit tests | A fast in-process runner with a DOM environment |
| End-to-end | A browser driver against the compose stack |
| Visual | Screenshots captured in one pinned container image, baselines committed |
| Client generation | An OpenAPI generator run against a committed copy of the document |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| VIII — Layered architecture, enforced | A new top-level directory changes the layout the import contracts police. | `console/` is outside the Python import graph entirely. A contract asserts no Python package imports it and that it imports no Python. The tier table in `AGENTS.md` gains a row describing it. |
| X — Operator owns their data | A front end is where third-party assets creep in. | FR-021 bundles everything; the end-to-end suite audits the network and fails on any external request. |
| XII — Test-first, trace-backed | The gate is the mechanism that makes test-first meaningful for the console. | This feature exists to make the console visible to the gate before any console code is written. |
| XIII — Language and attribution | New files, new headers. | British English, no attribution, no upstream names in any committed file. |

## Architecture decisions

**`console/` sits at the root, not under `surfaces/`.** `surfaces/` is a Python
tier with an `AGENTS.md`, an `__init__.py` and import contracts pointed at it. A
TypeScript application inside it would be a directory the linters walk into and
the import graph half-understands. Keeping it a peer makes the boundary obvious
and makes "no Python imports the console" a contract rather than a convention.

**The gate lands before the console.** The whole justification for reversing the
first wave's decision is that the premise — a TypeScript surface would be
invisible to `make verify` — can be removed. Removing it after writing the
console would mean writing the console under exactly the conditions that made the
original decision correct.

**Retirement is one change, at parity.** Two consoles serving the same screens is
two places every future change lands and one place it gets forgotten. The Python
console stays untouched and working until the new one covers every screen, and
then it goes in a single commit that also updates the image, the chart, the
constants and the entry point.

**Visual baselines come from one image.** Font rendering differs across
platforms, so baselines captured anywhere but a single pinned container produce
diffs that mean nothing. The comparison runs in the same image that captured
them; a contributor's local run compares against the same image.

**Determinism over coverage in the end-to-end suite.** Browser tests that flake
get disabled, and a disabled test is worse than an absent one. The suite runs
against the compose stack with seeded data and a controlled clock, and anything
that cannot be made deterministic is a unit test on the reducer instead.

## Phases

1. **Layout and provisioning.** `console/` created; Node, pnpm and browser
   binaries pinned; the provisioning make target; lockfile freshness check.
2. **Static checks.** Format, lint, type check, each individually runnable and
   each wired into `make verify`, proven by seeded failure fixtures.
3. **Unit tests and coverage.** Runner, DOM environment, coverage threshold.
4. **Client generation.** Committed OpenAPI copy, generation target, drift check.
5. **End-to-end.** Compose-backed stack, seeded data, browser driver, network
   audit for third-party requests.
6. **Visual regression.** Pinned capture image, baseline storage, diff artefacts,
   explicit acceptance as a reviewable change.
7. **CI.** Three-platform workflow extension, caching, parallelism, budgets.
8. **Retirement.** Remove `surfaces/console/` at parity; update image, chart,
   entry point, constants; add the import contract.

## Risks

- **`make verify` becomes slow enough that people stop running it.** Mitigated by
  NFR-001's budgets, by caching provisioning, and by making every check
  individually runnable so iteration does not require the whole gate.
- **Visual regression becomes noise and gets ignored.** Mitigated by the single
  pinned image and by requiring baseline acceptance to be a reviewed change,
  which keeps the diff in front of a human rather than behind a flag.
- **The retirement commit is enormous.** Accepted: it is enormous once, or it is a
  second implementation for ever.
