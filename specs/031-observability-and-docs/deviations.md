# Deviations — 031 Observability and Documentation

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

## 1. OTLP is encoded here rather than by the OpenTelemetry SDK

The plan's technical-context table says "OpenTelemetry SDK, OTLP export". What
shipped speaks OTLP — the same wire protocol, over HTTP with the JSON encoding
every collector accepts — encoded in `platform/observability/export.py` from the
standard library alone. No `opentelemetry-*` package is a dependency, optional
or otherwise.

**Why.** The alternative was an optional extra, and an optional extra is a code
path nobody in this repository ever executes: `uv sync` does not install extras,
so the only OTel code would be code no test covers and no `make verify` run
touches. Worse, it would put a library in the tree of a product whose central
promise is that nothing leaves the operator's host — a tree the operator has to
audit, and the first thing a security review reads. This repository has already
made this call once, in `platform/credentials/proxy/app.py`, which hand-rolls
ASGI rather than pull a framework in for two paths.

The encoder is ~130 lines of dictionaries and is fully tested: SC-002 reads the
exported documents back off the wire and asserts every declared instrument and
every declared span boundary is present, which an untested SDK path could not
have proven.
`tests/contract/observability/test_nothing_is_exported_by_default.py` parses
`export.py`'s AST and asserts it imports nothing outside the standard library
and `config`/`platform`, so "no dependency" is a property rather than a claim.

**What this costs.** OTLP/protobuf is not spoken (JSON is, and every collector
accepts it), and there is no OTel auto-instrumentation of third-party libraries.
Neither is in the specification.

## 2. The endpoint setting *is* the enable switch

FR-001 says telemetry must be disabled by default and FR-002 says it exports
only to an operator-configured endpoint. Rather than add
`NINJASRE_TELEMETRY_ENABLED` beside the existing `NINJASRE_OTEL_ENDPOINT` (which
feature 030 already declared), `TelemetryConfig.enabled` is `bool(endpoint)`.

Two settings would admit a state nobody wants — enabled with nowhere to go —
which fails once per export and reads to an operator as a broken collector
rather than as a missing setting. The spec's own clarification says "Enabling it
is one setting", and this is that literally. A malformed endpoint falls back to
disabled rather than refusing to start, for the same reason every failure in
this subsystem is swallowed: telemetry must never be why an investigation did
not happen.

Three settings *were* added — `NINJASRE_TELEMETRY_SERVICE_NAME`,
`NINJASRE_TELEMETRY_SAMPLE_RATIO`, `NINJASRE_LOG_MODULE_LEVELS` — each with a
row in `platform/startup/settings.py` and a regenerated `.env.example`, because
`tests/contract/deployment/` asserts every declared `*_ENV` constant is
documented.

## 3. Instrumentation is a library, not a set of call sites

Phase 2 (T010) says "spans for pipeline stages, loop iterations, capability
invocations, sub-agent dispatches, storage access". What shipped is the span
kind, the tracer, the propagation, and the contract test that drives all six
boundaries — not edits to `core/pipeline/stages/*`, `core/agent/loop.py`,
`capabilities/`, and `platform/persistence/` inserting `with tracer.span(...)`
at each one.

**Why.** Composing a tracer means deciding where the `Tracer` and `OtlpExporter`
instances live, which is the same composition-root question feature 030 owns and
feature 020's `InvestigationRunner` already deferred for the same reason
(see `specs/020-.../deviations.md` §1). Threading a tracer through four packages
as a constructor argument would be a wide change to tier-3 code driven by a
decision nobody has taken, and — since telemetry is off by default — one whose
effect no test in this repository would exercise.

What *is* proven, against real collaborators and read back off the wire: every
boundary has a kind; nesting produces parent/child; the correlation identifier
survives a sub-agent hop (the case that usually splits a trace in two); a
`traceparent` from outside is joined rather than replaced; outbound headers carry
both; an exception is recorded and re-raised. A deployment wiring this in gets
the behaviour the tests describe.

The same applies to `CostLedger.record` and `record_integration_health`: both are
called by their tests, and the deployment decides where the ledger lives.

## 4. `metrics/cost.py` and the CLI's cost report are two different things

`platform/observability/metrics/cost.py` attributes **per model call** — which is
what FR-007 and SC-009 are about, and what makes a mid-run model switch produce
per-model records that sum to the run total.

The CLI's `ninjasre cost` and the console's spend page (FR-023, T022/T023) do
**not** read that ledger. They aggregate over what the deployment already
persists — `RunSummary` plus `RunDetail.cost`, through `PlatformClient` — giving
per team and per period, which is what FR-023 asks for. Per-model would have
needed a new persistence port and a new REST route, both of which belong to
features 016 and 020.

`_spend_of` is written once and used by both `LocalClient` and `RemoteClient`, so
a remote deployment pays one request per run for a report an operator asks for
occasionally. That is stated in the function's docstring rather than hidden.

## 5. The site is a tree beside the existing `docs/`, not a replacement for it

The plan's structure shows `docs/site/`. The repository already had a flat
`docs/*.md` of design notes, two of which (`capabilities.md`,
`integrations-catalogue.md`) are generated by existing tools.

`tools/generate_docs.py` **reuses** `tools/generate_capability_docs.py` and
`tools/generate_integration_docs.py`'s renderers rather than reimplementing them,
so the site's capability page and `docs/capabilities.md` cannot disagree — one
source, two destinations. The existing generators and their `make` targets are
untouched.

The authored site pages are operator-facing entry points; the older `docs/*.md`
remain the reasoning behind each decision and are reachable from the built site
under "Reference notes". Nothing was deleted or moved.

## 6. `tools/__init__.py` added

`tools/check_docs_drift.py` imports `tools.generate_docs`, and the tests import
`tools.build_docs`. Without a package marker, `mypy` sees each file under two
module names and refuses to check the tree. This is resolution (a) from mypy's
own documentation. `tools/` is still excluded from the wheel, still outside the
import contracts, and every existing `python tools/x.py` and `python -m tools.x`
invocation still works.

## 7. Removed capabilities: content drift *and* orphan detection

T032 says "generation drops the page and the drift check catches a stale
reference". Pages are per *domain* (16) and per *category* (11) rather than per
capability (272) and per integration (82) — 38 generated files rather than 357,
which is a tree somebody can review.

A removed capability therefore changes a domain page's content (caught as
`out of date`) rather than deleting a file. To keep T032's actual property, the
drift check reports **three** failures, not one: missing, out of date, and
*orphaned* — any file under a generated directory that the generator did not
produce. A whole domain disappearing does delete its page, and the orphan check
is what notices if the deletion did not reach the tree. Both are tested, each
with a negative test that fires.

## 8. Documented shell examples are checked, not executed

FR-020 says every code example must be tested. Python examples are executed.
Shell examples are **checked**: every `ninjasre` invocation is resolved against
the real typer application, every `make` target against the `Makefile`, and every
repository path against the tree.

Running `docker compose up -d` in CI would be absurd, and running nothing would
prove nothing. What is checked is the class of failure this exists to prevent —
a command renamed, a flag dropped, a target removed, a file moved. Three negative
tests assert the sweep fires on each.

Illustrative blocks (`ini`, `json`, `yaml`, `text`, untagged) are left alone. A
fence with no language is treated as prose deliberately: guessing at it is how a
diagram becomes a syntax error.

## 9. SC-006 is asserted structurally, not by a person

SC-006 asks that an operator who did not write the quickstart complete it using
only that page. Nobody can run that in CI. What is asserted instead:
`test_the_quickstart_sends_nobody_anywhere_before_the_end` fails if any internal
link appears before the closing "Where to go next" section, plus the page reaches
`docker compose up -d`, `ninjasre doctor`, and `ninjasre investigate`, and every
command in it is checked by the example sweep.

That is the strongest mechanical form of the criterion. The human half stays
human, and this is recorded rather than ticked off silently.

## 10. T046 uploads the site rather than deploying it

"Documentation site published from the repository build" is a CI job that runs
`make docs-build` and uploads the tree as an artefact. It is not deployed to
GitHub Pages: this repository has no Pages configuration, the site builds and
serves offline from a checkout by design, and where an operator hosts it is
their decision. The property T046 is about — the site comes from the repository
build rather than from somebody's laptop — holds.

## 11. T047 not done: `docs/provenance-map.md` and `make check-provenance`

Per `CLAUDE.md`, `docs/provenance-map.md` is gitignored and never linked from a
committed file. Editing the local, uncommitted copy would have no effect on what
ships, so it was left alone — the same disposition as
`specs/020-.../deviations.md` §6.

`make check-provenance` does not exist in this repository and was not added:
creating a `make verify` step that reads a gitignored file would make a committed
file depend on an uncommitted one, which Article XIII (as amended by ADR 0011)
forbids.

Relatedly, `tools/build_docs.py` excludes documents the repository *ignores*
from the built site — determined with `git ls-files --others --ignored`, so no
filename appears in committed code. Without git it builds only `docs/site/`.
That is how the provenance map stays out of a published site by construction
rather than by an exclusion list somebody has to maintain.

## 12. Test-first sequencing, adapted where a red test would have proved nothing

Every module landed with its tests, and every negative case has a test that was
confirmed to fire. Two honest notes on ordering:

- `platform/observability/config.py` was written before its test file, because
  the Phase-1 tests as tasks.md sequences them (T001–T003) all import from
  modules that did not exist and would only ever have failed on `ImportError`.
  The SC-001, SC-003, and SC-008 contract tests were written before `export.py`
  and confirmed red for that reason, then made green — same adaptation, and the
  same reasoning, as `specs/020-.../deviations.md` §7.
- Three tests were red for a *real* reason during this work and are worth
  naming, because each found something:
  `test_a_setting_the_catalogue_does_not_name_is_absent_entirely` (my premise was
  wrong — the settings catalogue *does* document `AWS_SECRET_ACCESS_KEY`, and it
  is correctly redacted, so the test was rewritten and a second one added for the
  case it had actually been testing);
  `test_the_sweep_would_catch_a_command_that_no_longer_exists` (the example
  checker matched every unknown command against the bare `ninjasre` invocation
  and reported nothing — a real hole in the check, fixed);
  `test_nothing_in_the_built_site_is_fetched_from_anywhere` (asserted on the
  string `http://`, which a page legitimately quotes; rewritten to assert on
  fetching *tags*, which is the actual property).

## 13. Definition-of-done coverage

| Item | Where it is proven |
|---|---|
| SC-001 default exports nothing | `test_nothing_is_exported_by_default.py` — every socket call intercepted, full instrumented workload run, ledger empty; plus a negative test that catches an export |
| SC-002 all families and spans appear | `test_everything_appears_when_enabled.py` — read back off the wire, asserted against `DEFINITIONS` and `SpanKind` rather than a list |
| SC-003 collector outage is isolated | `test_export.py` — four real outage modes parametrised, drop counter, recovery without restart, bounded queue |
| SC-004 cardinality bounded under load | `test_cardinality_under_load.py` — 5,000 synthetic runs, series count bounded, totals still sum |
| SC-005 drift check fails on stale docs | `test_generated_documentation.py` — missing, changed, and orphaned each with its own failing case |
| SC-006 new operator succeeds on the quickstart alone | structurally; see §9 |
| SC-007 every documented example passes | `test_documentation_site.py` + `make check-doc-examples`, with three negative tests |
| SC-008 no telemetry package | `test_nothing_is_exported_by_default.py` walks `uv.lock`; plus the AST check in §1 |
| SC-009 cost across a model switch | `test_cost.py` — per-model records for one run sum to that run's total |
| `make verify` green | 9,277 passed, 20 skipped (all pre-existing infrastructure gates) |
