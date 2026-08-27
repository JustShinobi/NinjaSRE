# Deviations — 021 Web Console

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

## 1. The console is Python and server-rendered, not a Next.js application

**This is the largest deviation in the feature and everything else follows from
it.** The plan's technical-context table names Next.js App Router, TypeScript,
pnpm, Tailwind, and a client generated from the OpenAPI document. What shipped
is `surfaces/console/` as a Python, tier-1, server-rendered console and
backend-for-frontend: an HTML element tree (`html.py`), a page builder per area
(`pages/`), and a REST client over an injectable transport (`client.py`).

Three things decided it, in order of weight.

**The repository's own architecture already says so.** The root `AGENTS.md`
describes `surfaces/` as "human clients: CLI, REPL, **console
backend-for-frontend**", and `surfaces/AGENTS.md` says "Console
backend-for-frontend → `console/`". `config/constants/surfaces.py` already
shipped `SURFACE_WEB_CONSOLE` and `DEFAULT_CONSOLE_PORT`. `platform/guardrails/
sinks.py` already declares `Sink.WEB_CONSOLE` and documents restoring masked
identifiers per authorised reader for it, and `platform/config_service/
catalogue.py`'s module docstring opens "What the console renders". Every one of
those is a committed file describing a console inside the Python tree. `CLAUDE.md`
requires following `AGENTS.md` exactly; the plan and `AGENTS.md` disagreed, and
`AGENTS.md` is the committed source of truth for the tier layout.

**`make verify` is the definition of done, and it is Python-only.** The gate runs
ruff, mypy, import-linter, five guard scripts, and pytest over the seven
first-party packages. A TypeScript surface would have been invisible to all of
it: `make verify` would have gone green while nothing in the console was linted,
type-checked, import-checked, or tested, and the three-platform CI workflow has
no Node job to add one to. The DoD's last line ("`make verify` green") would have
been satisfied *vacuously* — which is the outcome the instruction "the feature is
only done when every Definition of done item is genuinely satisfied" exists to
rule out. Every success criterion is now proven by a test inside the gate:

| Criterion | Where it is proven |
|---|---|
| SC-001 | `tests/benchmarks/test_console_rendering.py` — 10,000 events, plus a scaling assertion that the cost does not grow with the transcript, plus a structural assertion on the rendered element count |
| SC-002 | `tests/unit/surfaces/console/test_stream.py` — a source that raises a real `ConnectionError` mid-stream; asserts every sequence once, in order, that the reconnect presented the right cursor, and that a replaying proxy is de-duplicated |
| SC-003 | `tests/unit/surfaces/console/test_live.py` — a decision arriving as a run event closes the card, and the closed card offers no decision to anybody |
| SC-004 | `tests/unit/surfaces/console/test_role_matrix.py` — every page × every role from `ROLE_ORDER`, asserting *absence* of `data-action`; plus `tests/contract/console/` against a real issued viewer token |
| SC-005 | `tests/contract/console/test_console_is_an_api_client.py` — previews the patch through the real gateway, saves it, and asserts `preview["values"] == after["values"]` and the same for provenance |
| SC-006 | Same file — the generated credential form's `action` is the API origin, every secret field is `type=password autocomplete=off`, and a structural test asserts `ConsoleClient` has no method whose name could carry a credential |
| SC-007 | `tests/unit/surfaces/console/test_page_accessibility.py` — every page × every role through `accessibility.audit`, plus `test_accessibility.py` which shows each rule a page that breaks it |
| SC-008 | `tests/benchmarks/test_console_rendering.py` — a 500-node three-level tree within a named budget, plus an assertion that every node is actually present |

**Nothing was lost that the plan asked for.** The plan's information
architecture, its "one component for live and replay", its omission-rather-than-
disabling rule, its virtualisation, its server-computed configuration preview,
its light and dark themes, its i18n scaffolding, and its accessibility
requirement are all implemented. What changed is the rendering technology.

**What is genuinely different.** There is no client-side JavaScript framework, so
"without a manual refresh" (FR-010, SC-003) is implemented as the mapping from a
stream event to a change in what is on screen (`live.py`), tested at that seam,
rather than as a React re-render. The browser-side wiring that drives it — an
`EventSource` subscription feeding `live.apply_event` — is the piece a deployment
adds, and `stream.py` holds the whole of the recovery logic it needs. See §6.

## 2. `POST /v1/config/{node_id}/preview` was added to the API

SC-005 says the preview must match what the API computes, and the plan's own
risk table says the mitigation is "compares the preview against the server's
computed effective config rather than reimplementing merge in TypeScript".
Feature 020's surface had no route that would answer "what would this patch
resolve to", so a console could only have satisfied SC-005 by reimplementing
`deep_merge`, lock inheritance, and `gated_paths` — which is exactly the thing
FR-030 and the risk table forbid.

The merge itself went where it belongs: `platform/config_service/preview.py`,
reached through `ConfigService.preview_settings`. It substitutes the proposed
document into the same chain a write reads and calls the same `effective.build`
that `resolve` calls, so the preview is not a second calculation — it is the
first one, run without persisting. The gateway route is a thin view over it.

## 3. Other routes the console needs, added to the gateway

The spec lists "the REST API itself (feature 020)" as out of scope, and that is
respected in the sense that matters — no new *product surface* was designed
here. What was added is the set of thin reads a rendering client cannot work
without, each one a view over a port that already existed:

- `GET /v1/config` — the org tree, one document (FR-016, SC-008). A team-scoped
  caller gets its own subtree only, mirroring `authorisation.py`'s downward-only
  inheritance.
- `GET /v1/config/{node_id}/catalogue` — `CatalogueView`, whose docstring already
  said it was for the console (FR-021).
- `GET /v1/config/{node_id}/integration-schemas` — `integration_forms`, likewise
  (FR-020).
- `GET|POST /v1/approvals`, `GET /v1/approvals/{id}`, `POST .../rollback` —
  FR-009's six required fields and FR-011.
- `GET /v1/topology/{node_id}` — FR-014.
- `GET /v1/knowledge/documents[/{id}]` — FR-015.
- `GET /auth/me` — FR-023. The console cannot render by permission without being
  told which permissions the caller holds, and deriving them from a role name
  would be a second copy of the catalogue.
- `GET /identity/{principals,grants,tokens}`, `POST /identity/tokens`,
  `DELETE /identity/tokens/{id}`, `POST /identity/tokens/revoke` — FR-026.
- `GET /audit/events`, `GET /audit/export` — FR-025.

The `/auth`, `/identity`, and `/audit` paths were **already declared** in feature
014's `route_permissions.ROUTE_TABLE` with their permissions; this feature
supplies handlers for rows that existed and had none. The `/v1` rows are declared
in a new `gateway/http/security/console_routes.py`, composed into
`APPLICATION_ROUTE_TABLE` exactly as feature 020's own rows are — so every new
route is permission-checked by construction and `tests/security/
test_route_permissions.py` still passes.

## 4. Two real defects found and fixed while testing

- **`gateway/http/routes/identity.py::list_grants`** had `await` inside a
  generator expression, which makes it an *async* generator and not iterable.
  It raised `TypeError` on every unfiltered call. Caught by the contract test
  that walks every area against the real API; fixed with an explicit loop and a
  comment saying why.
- **The accessibility harness reported every correctly labelled `<textarea>` and
  `<select>` as unnamed**, because both the naming rule and the form-label rule
  claimed them and the naming rule cannot see a `<label for>` elsewhere in the
  tree. Fixed by splitting the two sets — `_INTERACTIVE_TAGS` is now links and
  buttons, `_FORM_TAGS` is what a label names. The console's own pages were
  correct; the checker was wrong, which is the failure mode a checker nobody has
  shown a failure to always has.

## 5. Task-by-task notes

- **T001/T002 (generate a typed client, check regeneration in CI).** No
  generated client and no regeneration check. There is no OpenAPI-to-Python
  generator in the toolchain, and adding one plus a CI step would add a
  code-generation dependency to a tree the operator has to audit for the sake of
  a client that is ~200 lines. Instead the client is written, and drift is caught
  by something stronger than a regeneration diff: `tests/contract/console/`
  drives the real application over ASGI, so a route that changed shape fails
  there rather than producing a client that compiles and 404s.
- **T014 (i18n scaffolding).** `i18n.py` is a keyed catalogue with English as the
  source locale and an `UnknownMessage` that raises rather than falling back to
  the key. No second locale exists; the scaffolding is what makes adding one a
  catalogue rather than a rewrite.
- **T021 ("take over").** The control is rendered and permission-gated. What
  taking over *does* — detaching the model and handing the session to a person —
  is the REPL's mechanism (feature 019) and has no API route; the console posts
  to `/runs/{id}/take-over`, which a deployment wires.
- **T032 (strategy editing preserved through regeneration).** The strategy card,
  its source episodes, its "edited by a person" marker, and the edit control are
  rendered. There is no strategies route in the API and no `StrategyStore` port,
  so the page renders from the contract and the persistence half belongs to
  whichever feature adds it. Flagged rather than faked.
- **T035 (agent proposal review).** Same shape: rendered with the originating
  investigation visible, no API route behind it yet.
- **T044 (template application with diff preview).** `ConfigService.
  preview_template` exists and the page renders a diff from it; the route that
  exposes it was not added, because the same screen's more important half (§2)
  was, and a second preview route with no test driving it end to end would have
  been worse than an honest gap.
- **T051 (responsive).** Implemented in the stylesheet: tables stack below 40rem
  with `data-label` on every cell, which is why `shell.table` sets that
  attribute rather than each page doing it.
- **T055 (`docs/provenance-map.md`, `make check-provenance`).** Not done, and
  cannot be. That file is gitignored per `CLAUDE.md` and editing the local copy
  changes nothing that ships; `make check-provenance` is not a target in the
  `Makefile` and never has been. Same disposition as feature 020's §6.

## 6. What a deployment still has to wire

Stated plainly rather than left implied, and none of it is logic — all of it is
composition, which `gateway/http/services.py` and `surfaces/cli/client.py` both
already treat as feature 030's concern.

- **Serving.** `Console.render(path, session)` returns a `Rendered` carrying a
  document, a status, and the session as it stands afterwards. What writes that
  to a socket, and what stores the session, is a deployment decision.
- **The browser-side stream.** `stream.py` holds the cursor arithmetic and the
  reconnection loop; the `EventSource` subscription that feeds it, and the DOM
  patch that applies `live.apply_event`, are the browser's half.
- **Interaction-closure events.** SC-003's console half is implemented and
  tested. The other half is the runtime emitting an `attention_changed` event
  with `waiting: false` when an interaction is answered — `gateway/http/routes/
  interactions.py` closes the interaction but does not publish to the broker,
  because what publishes is the `InvestigationRunner` a deployment supplies.

## 7. Test-first sequencing

Followed per module rather than per phase, for the reason feature 020's §7 gives:
a suite of integration tests written against modules that do not exist yet can
only fail on `ImportError`, which proves nothing. Each module's tests were
written first, run, and confirmed failing for the right reason — the gateway
console-support tests were red against 404s and a missing `preview_settings`
before either existed; the accessibility harness was red against pages that
break each rule; the role matrix was red on two declared actions no page
rendered (`schedule.manage`, `impersonation.begin`), and both were fixed by
adding the missing controls rather than by deleting the declarations.

## 8. Gate

`make verify` green: lint, format-check, mypy strict over 669 files, all seven
import contracts kept, all five guard scripts, **4711 passed, 15 skipped**
(4223 → 4711; +488 tests, no pre-existing failures before or after).
