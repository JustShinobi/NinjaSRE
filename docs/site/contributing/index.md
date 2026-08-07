# Contributing

What the architecture is, the conventions that hold it together, and the one
command that decides whether a change lands.

## The one command

```sh
make verify
```

Lint, format check, strict types, import contracts, constants, protocol bodies,
the telemetry deny-list, the vendor-SDK boundary, capability metadata literals,
the storage boundary, the credential boundary, integration parity, the generated
catalogues, the documentation drift check, and the test suite. It is what CI runs
on Linux, macOS, and Windows, and it takes seconds.

Two gates are separate because they need something:

```sh
make test-postgres   # needs Docker; a change under platform/persistence/ is not done without it
make preflight PROVIDER=anthropic   # spends real tokens against a configured provider
```

## The tier table

Dependencies point downward only, and CI proves it.

| Tier | Packages | May import | Must never import |
|---|---|---|---|
| 1 | `surfaces`, `gateway` | everything below | each other |
| 2 | `capabilities` | `integrations`, `core`, `platform`, `config` | `surfaces`, `gateway` |
| 2 | `integrations` | `core`, `platform`, `config` | `capabilities`, `surfaces`, `gateway` |
| 3 | `core`, `platform` | `config`, and each other | tiers 1 and 2 |
| 4 | `config` | — | everything |

Seven contracts in `.importlinter` enforce it, one per rule, so a failure names
the boundary you broke rather than reporting "layers". The table and the
contracts are one fact in two places, and a test asserts they agree — edit one
without the other and the build fails.

```
config/          env names, constants, prompts. Imports nothing first-party.
core/            agent runtime, investigation pipeline, LLM abstraction, domain rules.
platform/        persistence, credentials, guardrails, memory, knowledge, config, scheduler, observability.
integrations/    one package per vendor: config, credential schema, verifier, client.
capabilities/    the agent-callable surface: typed tools, skills, registry, selection.
gateway/         inbound transports: REST/SSE, webhooks, chat platforms.
surfaces/        human clients: CLI, REPL, console backend-for-frontend.

tools/           repository tooling. Not agent-callable, not packaged, not import-linted.
tests/           architecture/ unit/ contract/ synthetic/ chaos/ e2e/ benchmarks/
```

## Where things go

Get these wrong and a reviewer sends it back, because they are the ones that are
expensive to undo later.

- **Behaviour goes in its owning module**, not in the nearest shared file that
  already imports something similar. "It was convenient" is how a `utils.py`
  becomes 4,000 lines.
- **Every constant lives in `config/constants/`**, in the domain module that owns
  it. A magic number at a call site is a defect, not a style preference, and
  `make check-constants` fails on an environment-variable name written anywhere
  else.
- **Prompts live in `config/prompts/`** — tier 4, so any tier may read one.
- **No SQL and no Cypher outside `platform/persistence/`.** Storage is reached
  through the repository ports, and a caller holds a gateway rather than a
  connection.
- **No credential outside `platform/credentials/proxy/`.**
- **No vendor LLM SDK outside `core/llm/`.** Everything else calls
  `core.llm.get_llm(role)` and gets the same behaviour whichever provider is
  configured.
- **Root `tools/` is repository tooling.** Anything the agent can call is a
  capability and lives in `capabilities/tools/`.

## Code style

Python 3.12+, `ruff` at line length 100, `mypy --strict` over every first-party
package *and* `tools/`. No `type: ignore` in first-party code.

- `from __future__ import annotations` at the top of every module.
- Public functions carry a docstring saying what they **return**, not what they
  do step by step. Modules carry one saying what they own.
- Comments explain *why*, and are worth writing when the reason is not visible
  from the code — an ordering constraint, a bound that came from a measurement, a
  workaround for a library's behaviour. A comment restating the line above it is
  noise.
- Errors are raised, never swallowed. A pipeline stage records its exception and
  re-raises: a result that never entered the trace did not happen.
- English, everywhere: source, comments, identifiers, commit messages,
  documentation, prompts, and user-facing text.

## Test first

The test lands before the implementation, and it is confirmed failing before the
fix. A behaviour-preserving refactor gets a characterisation test first.

A test that asserts a mock was called asserts that you wrote a mock. Drive real
collaborators wherever the real one is cheap — and in a system whose expensive
dependency is a model provider, almost all of them are.

## Adding a package

```sh
uv run python tools/scaffold_package.py <name> --tier <1-4>
```

Writes the skeleton, the package `AGENTS.md`, and the test directory with the
tier's rules stated. It deliberately does not edit `.importlinter`: deciding
which boundaries a package sits behind is a judgement, and it prints the
follow-up steps that make the package actually enforced.

## Adding a capability

```sh
uv run python tools/scaffold_capability.py <tool_name> --domain <domain>
```

Three files, no edits: the tool module, a `SKILL.md`, and a contract test.
Discovery walks the package, so there is no registry to remember — which is the
property that keeps a catalogue of this size addable one package at a time.

The scaffold prints what it refuses to decide for you, starting with the
side-effect level, which has no default. A capability with none declared is
treated as a write and gated accordingly.

## Adding an integration: the seven artefacts

```sh
uv run python tools/scaffold_integration.py <vendor> --domain <domain>
```

Every integration ships the same seven, and `make verify` fails naming both the
integration and the artefact when one is missing:

| Artefact | Without it |
|---|---|
| Credential and connection schema | Nothing knows what to ask the operator for |
| Verifier | "Configured" and "working" become the same word |
| Client | Every call reinvents pagination, retries, and error shape |
| Typed tools | The agent cannot call the vendor at all |
| Methodology skill | The agent has the tools and no idea when to use them |
| Setup documentation | The operator guesses at scopes and grants the wrong ones |
| Synthetic scenario | Nothing notices when the integration breaks |

One contract suite is parameterised over the discovered catalogue, so adding a
vendor adds rows and never a file.

The scaffold writes all seven and edits nothing, then prints the two things it
refuses to decide: the side-effect level, and the permission list. A guessed
permission is worse than a missing one, because verification then reports success
for a credential that cannot do the job.

## Documentation

The reference sections of this site — capabilities, integrations, configuration —
are **generated** from the same declarations the runtime reads:

```sh
make docs          # regenerate
make check-docs    # fail on drift; part of make verify
```

Do not edit those pages. Edit the declaration and regenerate, or the two will
disagree and the page will be the one that is wrong.

The authored sections describe decisions and threats, which is what a person is
for. Every code example in them is extracted and checked, so a command that stops
working fails the build rather than an operator.

## Footguns

Things that have already cost time here.

- **`platform/` shadows the stdlib `platform` module.** Deliberate: the package
  re-exports the whole stdlib API, so `import platform; platform.system()` still
  works. It only wins the name when the repository root leads `sys.path`, which
  is how every NinjaSRE process runs — but pytest imports the stdlib module while
  bootstrapping, so `tests/conftest.py` rebinds it.
- **`lint_imports()` inserts `os.getcwd()` at the head of `sys.path`**, so the
  architecture fixtures must run with the fixture tree as the working directory.
- **`import-linter` layer delimiters are not commas.** `a | b` means the two are
  independent and must not import each other; `a : b` means they may. Swapping
  them silently inverts the rule.
- **A `Protocol` method body must be its docstring alone.** `...`, `pass`, and
  `raise NotImplementedError` all type-check, and all become the implementation
  the moment the protocol is used as a concrete base.

## Commits

Conventional commits, English, imperative. Say what changed and why the change is
the right one; a commit message that restates the diff has told the next reader
nothing they could not have got from `git show`.
