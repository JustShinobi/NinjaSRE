# The console

The web console: a TypeScript application, served by a process of its own, that
talks to the deployment over the REST API and to nothing else.

Read the root [`AGENTS.md`](../AGENTS.md) first. What follows is what is
different here.

## It is not a Python package, and that is load-bearing

`console/` is a peer of the seven Python tiers rather than a member of one. It
has no `__init__.py`, no module in it is importable, and the tier table's
`console` row says so:

| Tier | Packages | May import | Must never import |
|---|---|---|---|
| — | `console` | the REST API, over HTTP | every Python package |

`make check-console-boundary` enforces both directions: no Python module imports
`console`, and no console file reaches into `capabilities/`, `config/`, `core/`,
`gateway/`, `integrations/`, `platform/`, `surfaces/`, `tests/` or `tools/`. It
is a guard script rather than an `import-linter` contract because `import-linter`
reasons about importable Python packages — giving this directory an `__init__.py`
so a contract could name it would create the very thing the row forbids.

The one exception is `fixtures/`, which the console may read. It is data, it is
generated from the application by checks that already exist, and reading it is
how the console stays a client rather than becoming a second implementation.

## The toolchain is pinned, and provisioned by the gate

Nothing here assumes Node is installed.

| Concern | Where it is pinned |
|---|---|
| Node | `.node-version`, with a SHA-256 per platform in `toolchain.lock.json` |
| pnpm | `packageManager` in `package.json`, and `toolchain.lock.json` |
| Browser | `@playwright/test` in `package.json` |
| Capture image | `toolchain.lock.json`, by digest |

`make console-setup` provisions all of it. It looks for a Node already on `PATH`
at exactly the pinned version, and otherwise downloads the official archive and
refuses it unless it hashes to the committed digest. Set `NINJASRE_NODE_MIRROR`
to fetch from somewhere else; the digest it has to match is the same one, so a
mirror is a different address rather than a lower standard.

The archive is unpacked into `.toolchain/`, which is ignored by git and safe to
delete — the next run provisions it again.

## Every check, and how to run one

`make verify` runs all of these. Each is also a target of its own, because a
contributor fixing a type error should not have to sit through a browser suite
to find out whether they fixed it.

| Target | What fails it |
|---|---|
| `make console-lockfile` | `pnpm-lock.yaml` no longer describes `package.json` |
| `make console-format-check` | a file the formatter would rewrite |
| `make console-lint` | a lint rule, including the type-aware ones |
| `make console-typecheck` | a type error anywhere in the tree, tests included |
| `make console-test` | a failing unit test, or coverage below the declared floor |
| `make console-client-check` | the committed API client is not what the document generates |
| `make console-build` | the production build |
| `make console-e2e` | a browser test against the built console |
| `make console-visual` | a screen that differs from its committed baseline |

On a machine with no toolchain and no container runtime, the checks that need
them report a named skip and succeed — the same way the chaos and cloud suites
already do, because a gate that goes red for a reason the contributor cannot act
on is a gate they learn to bypass. CI sets `NINJASRE_CONSOLE_TOOLCHAIN=required`,
and then a skip is a failure. Three things are never skipped, whatever the
machine: a drifted lockfile, a stale committed client, and a check that ran and
failed.

## The API client is generated, never written

`src/api/schema.ts` is generated from `fixtures/contract/openapi.json` — the
committed copy of the gateway's own document — by `make console-client`. It is
committed, and `make console-client-check` fails when it differs from a fresh
generation.

Two consequences worth stating. The generation needs no network and no running
gateway, so an air-gapped build works. And the console cannot hold a second
opinion about what the API returns: a route that changed shape reaches it as a
failing type check rather than as a client that compiles and 404s.

`src/lib/api.ts` is the only module that makes a request. Everything else goes
through it.

## Nothing may leave the deployment

No font host, no icon CDN, no analytics, no error reporter. Every asset is
bundled and served by the deployment.

Two things hold this. A lint rule rejects a literal external origin in console
source. And `tests/e2e/network.spec.ts` watches every request a production build
issues and fails on any host the operator does not run — which is the half that
catches a bundled stylesheet that turns out to point at a font host.

## Visual baselines, and what accepting one means

Baselines live in `visual/baselines/` and are compared against captures from one
container image, pinned by digest. Font rasterisation differs between operating
systems and between font packages on the same one, so a baseline captured
anywhere else produces differences that mean nothing — and a visual gate
reporting differences that mean nothing is one people stop reading.

`make console-visual` compares. `make console-visual-accept` recaptures, which
rewrites committed PNGs: **the acceptance is the commit somebody reviews**, not
a flag on a command.

`visual/screens.json` is the registry, and it is what makes design fidelity
checkable rather than merely intended:

- a design reference in `visual/mockups/` that appears in neither list fails the
  suite by name, so a design cannot arrive and be forgotten;
- a reference marked `pending` must name the surface that will implement it;
- a screen marked `baselined` must have a committed baseline **and** an
  acceptance record naming the reference it was first reviewed against — or, if
  there is no reference, a sentence saying why. After that first acceptance,
  ordinary visual regression keeps the screen matched.

## The browser suites

`tests/e2e/` drives a browser against the built console and a real gateway.
`tools/console_e2e.py` starts both and takes them down; the suite is handed an
address and owns no process, because a browser test that also owns process
lifecycle is a browser test that hangs.

Two backings. `mock` is the committed dataset served by `tools.mockplane` — every
timestamp in it is shifted to one fixed instant, which is what makes
`make console-e2e-sweep` (twenty consecutive runs, any flake is a defect) worth
running. `compose` is the deployment's own compose definition: a real gateway
against a real database, run by its own CI job.

There are no retries. A retry hides a flake, and a hidden flake is why suites get
disabled. Anything that cannot be made deterministic becomes a unit test instead
— never a disabled test.

## Seeded failures

`fixtures/` holds files that are broken on purpose: a type error, a lint
violation, a format violation, a failing unit test, a failing browser test.
`tests/contract/console/test_console_gate.py` splices each one into the tree,
runs the check it belongs to, and requires it to fail and to name the file.

A check nobody has watched fail is a check that might be walking an empty file
list, and the repository would look exactly as clean either way. That is the
whole reason the directory exists, and it is why the lint, format and type
configurations all exclude it.
