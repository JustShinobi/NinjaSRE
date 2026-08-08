# Working in this repository

NinjaSRE is a self-hosted AI SRE platform. It investigates production incidents,
produces evidence-backed root causes, learns from every investigation, and
proves — continuously and automatically — that it is getting better.

Read this before writing code. Per-package conventions live in that package's
own `AGENTS.md`, linked at the bottom.

## Non-negotiables

These are properties of the system, not preferences. Each one is enforced by
something in `make verify`, or it is not a rule.

| Principle | What it costs you if you forget |
|---|---|
| **Evidence over assertion** | A conclusion carries the observations that support it. An unbacked claim is a hypothesis, never a finding, and a tool result that never entered the trace did not happen. |
| **Bounded autonomy** | Every loop ceiling, context budget, and schema cap is a named constant in `config/constants/`. A magic number at a call site is a defect, not a style preference. |
| **Read-only by default** | A capability with no `side_effect_level` is treated as a write. Anything above read needs per-action human approval *and* a stored rollback plan. |
| **Secrets never reach the agent** | No credential in env, prompt, tool arguments, filesystem, or trace. Authenticated calls go through the credential proxy, which injects the secret at the network edge. `make check-credentials` fails on a `reveal` outside the proxy, or on an integration reading the process environment at all. |
| **One canonical runtime** | The first-party ReAct loop is the only runtime that produces an evaluation number. Alternative adapters are experimental and never the default. |
| **Provider neutrality** | `make check-vendor-sdks` fails on a vendor LLM SDK imported outside `core/llm/`, including the `importlib` way round it. Every SDK is an optional extra, so a deployment where nothing leaves the operator's infrastructure installs none of them and is still fully functional. |
| **Learning is measured or not claimed** | Every learning mechanism ships with an ablation that isolates its contribution. A scenario-score regression fails CI. |
| **Layered architecture** | `make check-imports` fails, naming the boundary. It is not advisory. |
| **Single datastore** | One Postgres, reached through the thirteen repository ports. `make check-raw-sql` fails on SQL, Cypher, or a database driver imported outside `platform/persistence/`. |
| **The operator owns their data** | No telemetry, analytics, crash reporting, or version check that transmits off-host. `make check-deps` enforces the dependency half. |
| **Test-first** | The test lands before the implementation. A behaviour-preserving refactor gets a characterisation test first. |
| **English** | All source, comments, identifiers, commit messages, documentation, prompts, and user-facing text — whatever language the conversation is happening in. |

## Repository map

```
config/          Tier 4 — env names, constants, prompts. Imports nothing first-party.
core/            Tier 3 — agent runtime, investigation pipeline, LLM abstraction, domain rules.
platform/        Tier 3 — persistence, credentials, guardrails, memory, knowledge, configuration, scheduler, observation, incidents, observability.
integrations/    Tier 2 — one package per vendor: config, credential schema, verifier, client.
capabilities/    Tier 2 — the agent-callable surface: typed tools, skills, registry, selection.
gateway/         Tier 1 — inbound transports: REST/SSE, webhooks, chat platforms.
surfaces/        Tier 1 — human clients: CLI, REPL, console backend-for-frontend.
console/         The web console. TypeScript, not a Python package, not a tier.

tools/           Repository tooling. NOT agent-callable, NOT packaged, NOT import-linted.
tests/           architecture/ unit/ contract/ synthetic/ chaos/ e2e/ benchmarks/
test-infra/      Cluster definitions and one-command setup/teardown for the expensive suites.
fixtures/        The mock data plane: one deterministic, anonymised deployment.
```

`fixtures/` belongs to none of the packages on purpose. It is read by the console,
by the demo seeder and by both test suites, so putting it under any one of them
would make the others reach across a boundary the import contracts exist to
police. [`fixtures/README.md`](fixtures/README.md) is the long form; the short
version is `python -m tools.mockplane console`, which serves the console against a
full deployment with no backend, no cluster and no database behind it.

## The tier table

Dependencies point downward only, and CI proves it.

| Tier | Packages | May import | Must never import |
|---|---|---|---|
| 1 | `surfaces`, `gateway` | everything below | each other |
| 2 | `capabilities` | `integrations`, `core`, `platform`, `config` | `surfaces`, `gateway` |
| 2 | `integrations` | `core`, `platform`, `config` | `capabilities`, `surfaces`, `gateway` |
| 3 | `core`, `platform` | `config`, and each other | tiers 1 and 2 |
| 4 | `config` | — | everything |
| — | `console` | the REST API, over HTTP | every Python package |

**This table is the source of truth.** Seven contracts in
[`.importlinter`](.importlinter) enforce the seven Python rows, one per rule, so
a failure names the boundary you broke rather than reporting "layers". The
`console` row is enforced by `make check-console-boundary` instead, because
`import-linter` reasons about importable Python packages and the console is not
one — giving it an `__init__.py` so a contract could name it would create the
very thing the row forbids.
`tests/architecture/test_contract_coverage.py` asserts that the table and its
enforcement stay in agreement: edit the table without revisiting them and the
build fails.

## File placement

Get these wrong and the reviewer will send it back, because they are the ones
that are expensive to undo later.

- **Behaviour goes in its owning module.** Not in the nearest shared file that
  already imports something similar. "It was convenient" is how a `utils.py`
  becomes 4,000 lines.
- **Root `tools/` is repository tooling** — check scripts, scaffolding. Anything
  the agent can call is a capability and lives in `capabilities/tools/`. The two
  senses of the word cost more in confusion than the rename costs in typing.
- **Every constant lives in `config/constants/`**, in the domain module that owns
  it, re-exported from `__init__.py`. `make check-constants` fails on an
  environment-variable name written anywhere else.
- **Prompts live in `config/prompts/`.** Tier 4, so any tier may read one without
  creating a cycle.
- **No SQL and no Cypher outside `platform/persistence/`.** Storage is reached
  through the repository ports in `platform.persistence.ports`, and a caller
  holds a `PersistenceGateway` rather than a connection. `make check-raw-sql`
  fails on a query, an `execute` call, or a driver import anywhere else.
- **No credential outside `platform/credentials/proxy/`.** An integration client
  carries a tenant-and-team-scoped handle and the proxy injects the secret at
  the network edge; `integrations/_base/client.py` is the only sanctioned path
  for an authenticated external call, and it has no constructor parameter that
  could accept a credential. Signing schemes that need the key at
  request-construction time — SigV4 and its relatives — run proxy-side, in
  `platform/credentials/proxy/signing/`.
- **No vendor LLM SDK outside `core/llm/`.** Everything else calls
  `core.llm.get_llm(role)` and receives the same behaviour whichever provider is
  configured. Adding a provider is one adapter under `core/llm/providers/` plus
  a registry row — nothing above that layer changes, and a contract test proves
  it by adding a tenth provider and driving the whole stack with it.
- **Compatibility-forwarding modules are deleted in the change that migrates
  their callers.** Not in a follow-up. The follow-up does not happen.

## Code style

- Python 3.12+, `ruff` at line length 100, `mypy --strict` over every first-party
  package *and* `tools/`. No `type: ignore` in first-party code.
- `from __future__ import annotations` at the top of every module.
- Public functions carry a docstring saying what they return, not what they do
  step by step. Modules carry one saying what they own.
- Comments explain *why*, and are worth writing when the reason is not visible
  from the code — an ordering constraint, a bound that came from a measurement,
  a workaround for a library's behaviour. A comment restating the line above it
  is noise.
- Type annotations are complete, including `-> None`.
- Errors are raised, never swallowed. A pipeline stage records its exception and
  re-raises: a result that never entered the trace did not happen.

## Footguns

Things that have already cost time here.

- **`platform/` shadows the stdlib `platform` module.** This is deliberate. The
  package re-exports the whole stdlib API so `import platform;
  platform.system()` still works for any third-party caller. It only wins the
  name when the repository root leads `sys.path`, which is how every NinjaSRE
  process runs — but pytest imports the stdlib module while bootstrapping, so
  `tests/conftest.py` rebinds it. If you ever see `platform.observability` fail
  to import, that is why.
- **`lint_imports()` inserts `os.getcwd()` at the head of `sys.path`.** The
  architecture fixtures must therefore run with the fixture tree as the working
  directory, or the real packages get graphed instead.
- **`import-linter` layer delimiters are not commas.** `a | b` means the two are
  independent and must not import each other; `a : b` means they may. Tier 1 uses
  `|` and tier 3 uses `:`, and swapping them silently inverts the rule.
- **A `Protocol` method body must be its docstring alone.** `...`, `pass`, and
  `raise NotImplementedError` all type-check, and all become the implementation
  the moment the protocol is used as a concrete base. `make check-protocols`
  rejects them.
- **The import contracts and the tier table above are one fact in two places.**
  Change one and you change the other, in the same commit.

## Adding a package

```bash
uv run python tools/scaffold_package.py <name> --tier <1-4>
```

It writes the skeleton, the package `AGENTS.md`, and the test directory with the
tier's rules already stated. It deliberately does not edit `.importlinter` —
deciding which boundaries a package sits behind is a judgement — and prints the
follow-up steps that make the package actually enforced.

## Adding a capability

```bash
uv run python tools/scaffold_capability.py <tool_name> --domain <domain> [--vendor <vendor>]
```

Three files, no edits: the tool module, a `SKILL.md`, and a contract test.
Discovery walks the package, so there is no registry to register with — which
is the property that keeps a catalogue of eighty-five integrations addable one
package at a time. The scaffold prints what it deliberately cannot decide for
you, starting with the side-effect level, which has no default.

## Adding an integration

```bash
uv run python tools/scaffold_integration.py <vendor> --domain <domain>
```

Every integration ships the same seven artefacts — credential and connection
schema, verifier, client, typed tools, methodology skill, setup documentation,
and a synthetic scenario — and `make verify` fails naming both the integration
and the artefact when one is missing. One contract suite is parameterised over
the discovered catalogue, so adding a vendor adds rows and never a file.

The scaffold writes all seven and edits nothing, then prints the two things it
refuses to decide: the side-effect level, and the permission list. A guessed
permission is worse than a missing one, because verification then reports
success for a credential that cannot do the job.

[`docs/integration-framework.md`](docs/integration-framework.md) is the long
form. [`docs/integrations-catalogue.md`](docs/integrations-catalogue.md) is
generated from the declarations and is what the console reads.

## Before you push

```bash
make verify
```

One gate: lint, format check, strict types, import contracts, constants,
protocol bodies, the telemetry deny-list, the vendor-SDK boundary, capability
metadata literals, the storage boundary, the credential boundary, integration
parity, the generated catalogues, the documentation drift check, the documented
examples, and the test suite. It is what CI runs on Linux, macOS, and Windows,
and it takes seconds.

The storage layer has a second gate, because it needs a database:

```bash
make test-postgres
```

It builds a PostgreSQL image carrying `pgvector` and Apache AGE, and runs the
persistence contract suite against it as well as against the in-memory fakes.
CI runs it as its own job. A change under `platform/persistence/` is not
finished until it passes — `make verify` alone only proves the fakes agree with
themselves.

The chaos and end-to-end suites are separate too, because they need a cluster
and one of them spends money:

```bash
make chaos-setup && make chaos-run INVESTIGATOR=your.deployment:build
```

They run before a release and on a schedule, never as a pull-request gate — a
gate that creates a cluster is one people learn to skip. Without infrastructure
every one of them **skips with a message naming what is missing**, so
`make verify` is green on a laptop with no cluster on it. Their value is finding
failure modes the synthetic corpus does not know to contain, and every one they
find is captured into a synthetic scenario that then runs on every change.
[`docs/chaos-and-e2e-suites.md`](docs/chaos-and-e2e-suites.md) is the long form.

Verifying a *configured provider* is separate, because it spends real tokens:

```bash
make preflight PROVIDER=anthropic
```

Run it once per deployment, before anyone depends on that provider. It checks
authentication, a tool call, a structured output, and a stream against the
operator's own endpoint — the things a recorded fixture cannot.

## Documentation

The operator-facing site lives under [`docs/site/`](docs/site/index.md) and
builds offline:

```bash
make docs          # regenerate the capability, integration, and configuration references
make check-docs    # fail on drift — part of `make verify`
make docs-build    # render the whole site into docs/site/build
make docs-serve    # build it and serve it on localhost, fetching nothing
```

Three sections are **generated** from the declarations the runtime reads —
capabilities, integrations, configuration — and are not edited by hand. Edit the
declaration and regenerate, or the two disagree and the page is the one that is
wrong. `make check-docs` fails on drift, including on a page left behind by
something that was deleted.

Everything else is authored, and every code example in an authored page is
extracted and checked by `make check-doc-examples`: a documented command,
`make` target, or repository path that no longer exists fails the build rather
than an operator.

## Per-package conventions

- [`capabilities/AGENTS.md`](capabilities/AGENTS.md)
- [`config/AGENTS.md`](config/AGENTS.md)
- [`core/AGENTS.md`](core/AGENTS.md)
- [`gateway/AGENTS.md`](gateway/AGENTS.md)
- [`integrations/AGENTS.md`](integrations/AGENTS.md)
- [`platform/AGENTS.md`](platform/AGENTS.md)
- [`console/AGENTS.md`](console/AGENTS.md)
- [`surfaces/AGENTS.md`](surfaces/AGENTS.md)
