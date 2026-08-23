# Deviations — 019 CLI and Interactive REPL

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## 1. T054 — `make check-provenance` does not exist and was not created

**Planned.** "Update `docs/provenance-map.md`; confirm `make check-provenance`."

**Done.** The provenance map was updated — feature 019's rows in section 8,
plus a "written fresh, not adapted" table. `make check-provenance` was *not*
created.

**Why.** ADR 0011 amended Constitution Article XIII to 2.0.0: attribution lives
in `README.md` and `NOTICE` only, and **a committed file must not depend on an
uncommitted one**. `docs/provenance-map.md` is gitignored. A `check-provenance`
target in the committed `Makefile` would be a committed file that fails on any
clone without the map — which is every clone. The map is a local record, and a
check over it belongs in the same local scope or nowhere.

The provenance-header half of the task is superseded by the same ADR and was
already marked so in the map before this feature started.

---

## 2. T053 — SC-001 is measured in two parts, not one

**Planned.** "Measure installation to first successful investigation on all
three platforms (SC-001)."

**Done.** `tools/measure_first_investigation.py` measures the deterministic
path — empty environment, build, install, and the four things an operator does
before they can investigate anything — and reports the budget *remaining* for
the rest. A `first-run` CI job runs it on Linux, macOS, and Windows.

**Why.** The final leg is entering a provider credential and running an
investigation that comes back. That spends real tokens against an operator's
own endpoint, which is exactly why this repository already keeps that class of
check in `make preflight` rather than in the gate. Measuring it in CI would
require a credential in CI and would bill somebody per pull request.

Reporting a "total" that silently excluded the slow leg would be worse than
reporting two numbers, so the script reports two: 19s measured on the
development machine, 581s left for the provider-dependent leg.

**What this means for the definition of done.** SC-001's first checkbox is
satisfiable in CI for the measured part and requires one `make preflight` run
per platform for the rest. That is a real gap and it is deliberate.

---

## 3. Structure — five modules the plan's tree does not name

**Planned.** The `## Project structure` block lists `app.py`, `commands/`,
`output/`, `wizard/`, `client.py` under `surfaces/cli/`.

**Done.** Those, plus:

| Module | Why |
|---|---|
| `surfaces/cli/models.py` | The payload shapes every command reports. Putting them in `client.py` beside the protocol would have made one 1,100-line file out of two concerns — what a deployment is asked, and what comes back. |
| `surfaces/cli/errors.py` | The exit-code contract and the one exception that carries it. FR-008 needs a home, and it is neither the app root nor a command. |
| `surfaces/cli/invocation.py` | What one run of the CLI decided before a command body started, and the `run_command` wrapper every command ends with. In `app.py` it would be a circular import: `app.py` imports the command modules, and the command modules need this. |
| `surfaces/cli/output/schemas.py` | The published JSON Schema per command, plus a validator over the subset they use. `json_.py` is the envelope; this is the contract. |
| `surfaces/entrypoint.py` | See deviation 5. |

`surfaces/repl/routing.py` is likewise not in the plan's tree. FR-015 is the
feature's most load-bearing prohibition and it deserved a module with nothing
else in it, so that "where is the decision made" has one answer.

None of these changes what is built; they are where it lives.

---

## 4. `execute` was renamed `run_command`

**Why.** `tools/check_raw_sql.py` rejects an `execute(...)` call outside
`platform/persistence/`, and every command body ended with one. The check is
right — a surface sharing a name with a database cursor either trips it or
teaches somebody to weaken it — so the function was renamed rather than the
check relaxed. The reason is recorded in the function's own docstring, because
the next person to prefer the shorter name will read that before this file.

---

## 5. A console-script entry point was needed

**Not in the plan at all.** `pyproject.toml` gained
`ninjasre = "surfaces.entrypoint:main"`, and `surfaces/entrypoint.py` exists to
back it.

**Why.** `platform/` deliberately shadows the stdlib module and only wins the
name when the package root leads `sys.path`. Python starts a console script
with the stdlib ahead of site-packages, so an entry point that imported the
application directly found the *stdlib* `platform` and died on
`platform.observability` — the first thing a freshly installed CLI did was
crash. The entry point fixes the path before its first first-party import,
which is why it is a separate module rather than a function in `app.py`: a
module that imported the app at the top would already have lost.

`tests/conftest.py` solves the same problem for pytest, the same way, and says
so. The root `AGENTS.md` already named this footgun; this is the third place it
has been paid for.

---

## 6. Three runtime dependencies were added

`typer`, `rich`, and `prompt-toolkit`, all named by the plan's technical
context, all added as runtime dependencies rather than extras.

**Why not extras.** The CLI is how the platform is operated, debugged, and
demonstrated. A deployment that installed the platform and could not run the
command would have installed a library. All three pass
`tools/check_dependencies.py`; none transmits anything.

---

## 7. Two constants the plan implied but nothing declared

- `REASONING_EFFORT_LEVELS` and friends in `config/constants/investigation.py`,
  because `/effort` needs a bounded set and Article II says a bound is a named
  constant.
- `COLUMNS_ENV` in `config/constants/surfaces.py`, because
  `make check-constants` rejects an environment-variable name written anywhere
  else — correctly.

Both are additions the plan's own constitution check required and its task list
did not enumerate.

---

## 8. `tests/support/` was added

**Why.** A `conftest.py` reaches one directory tree, and the surfaces are
exercised from `tests/unit`, `tests/contract`, and `tests/security`. The
in-memory deployment lives in `tests/support/deployment.py` and each suite
declares its own fixtures over it. The alternative was three copies of the same
fake, which is three chances for them to disagree about what the platform does.

---

## 9. Requirement identifiers were written, then removed

**What happened.** The first pass cited `FR-0xx` and `SC-00x` throughout —
about seventy occurrences across source, tests, and the installers — because
that is what the surrounding codebase does: eighty-nine committed files under
`core/`, `platform/`, and `config/` cite them today.

**Why they went.** The writing-style rule is explicit that they must not be,
and the reason holds: they point at `specs/`, which is gitignored, so a
contributor cloning the repository cannot follow one. Repository consistency
was the weaker argument. Each citation was replaced with the substance it stood
for — `SC-004` became "a resumed session matches its pre-suspension state
exactly", `FR-015` became "the whole rule is the absence of any branch that
inspects the content of a line".

**Constitution article references were kept.** `.specify/memory/constitution.md`
*is* committed, so "Article X" points at something a contributor has. The rule
lists article numbers alongside the others; the reason it gives does not apply
to them, and every existing file cites them this way.

**The existing eighty-nine files were not touched.** That is a separate change,
it is not this feature's, and folding it in would have buried a surface behind
a repository-wide edit.

---

## Not deviations, recorded because they look like they might be

- **`rich` is used through our own degradation layer rather than directly.**
  The plan says "rich for tables, streaming, and progress". It is — `Terminal`
  decides what the destination can render and configures `rich.Console`
  accordingly. The decision is ours; the drawing is rich's.
- **The REPL's slash commands live in three modules, not sixteen.** The plan's
  tree shows `commands/` with a `registry.py`; T036–T041 group them exactly as
  they are grouped here. Sixteen files with one function each was not implied.
- **`RemoteClient` speaks to a REST API that feature 020 has not built yet.**
  FR-009 is in this feature's scope and feature 020 is listed as out of scope.
  The client is written against the documented shape and is fully tested
  against a stubbed opener; it will meet the real API when 020 lands.
