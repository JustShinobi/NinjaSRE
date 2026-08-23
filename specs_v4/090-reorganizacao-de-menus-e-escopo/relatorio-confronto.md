# Confrontation report — 090 Reorganização de menus e escopo

## Conclusion

`controle.md` drifted in exactly one direction before this audit: everything
past the first row was marked **NÃO INICIADO**, and — with one real,
material exception found and fixed during this audit — that was accurate at
the moment it was written and is no longer accurate now. This spec had not
been executed at all when this confrontation began: `console/src/shell/routes.ts`
still declared the eighteen-area manifest, `/approvals` and `/proposals` were
still two menu entries, Detectors and Data were still split across two
zones, Catalogue still mixed a read surface with a write surface, and Audit
was still its own top-level entry. Every fusion and extraction spec.md asks
for has now been built, verified against the platform's real nested
permission model so no viewer gains or loses reach, covered by tests that
were run and watched fail before the implementation existed, and cross-checked
against the Python side that restates the console's own route manifest for
places TypeScript cannot reach.

One gap survived a first pass and was caught only by reading spec.md's
prose to its final clause rather than trusting the fusion list: **Integrations**
names "credencial, teste ('Check it'), e filtro" as what the extracted screen
should carry, and neither the extraction nor the screen it was extracted from
had ever built a filter for the 85 integration cards — a distinct control from
the tools/skills search Catalogue already had. That is now built, tested
red-then-green, and wired through the console's ordinary URL-state filter
idiom rather than a one-off.

One discovery came from running the gates themselves, not from reading code:
`tests/contract/console/test_console_gate.py`'s real, subprocess-driven checks
(`python -m tools.console_gate e2e`, invoked identically by `make console-e2e`)
have the undocumented side effect of writing a placeholder PNG into
`console/visual/baselines/` for any screen `screens.json` declares with no
committed baseline — and the eleven files it wrote for this spec's new
screens were byte-identical to each other across seven unrelated routes,
proof they are not real, distinct captures. Both times this fired during
this audit, the files were deleted before they could be mistaken for
reviewed baselines; the details and the evidence are in Verification, item 12.

The two things this audit declines to do, both named rather than dropped:
capturing the eleven missing visual baselines for real (`make
console-visual-accept`, explicitly out of bounds in this environment and,
per the discovery above, unsafe to reach even indirectly through the gate
tests) and running `make console-e2e` for the same reason. Everything else
spec.md asks for is done, evidenced below with the file and line a reader can
open to confirm it independently.

## Verdict table

| Item | What `controle.md` claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| Sidebar 18 → 13 areas | FEITO (partially, per "onda 1") | `routes.ts` still declared 18 areas; none of the fusions existed | **DONE** |
| Decisions ⇐ Approvals + Proposed changes | NÃO INICIADO | Two separate areas, two menu entries, no mutual reference | **DONE** |
| Knowledge ⇐ Memory + Knowledge + Topology | NÃO INICIADO | Three separate areas, three empty states pointing at each other | **DONE** |
| The agent ⇐ + Catalogue (read) + Team context | NÃO INICIADO | Catalogue and Team context were separate top-level areas | **DONE** |
| Integrations ⇐ extraída do Catalogue | NÃO INICIADO ("a tela nova mais importante") | No such address existed; the write surface was a panel inside Catalogue | **DONE, with one gap fixed: the filter** |
| Signals ⇐ Detectors + Data | NÃO INICIADO | Detectors was in "Environment", Data was in "Settings" | **DONE** |
| Administration + Audit | NÃO INICIADO | Audit was its own top-level area | **DONE** |
| O que NÃO fundir (Incidents/Investigations, Autonomy/Configuration, Resources/Knowledge) | not tracked as its own row | N/A — these were never merged | **DONE (confirmed still separate)** |
| Transversal 1: camada de tradução de erros | NÃO INICIADO ("onda 2") | Established by earlier specs; this spec's own new/changed code adds no raw error text | **DONE (inherited; unaffected by this pass)** |
| Transversal 2: vocabulário único | NÃO INICIADO ("onda 4") | Established by earlier specs; this spec's own new i18n keys hold no internal enum literal | **DONE (inherited; unaffected by this pass)** |
| Transversal 3: empty states com causa local | NÃO INICIADO ("onda 3") | Established by earlier specs; every donor tab's `emptyBecause`/`setupCause` survived the merge intact | **DONE (inherited; unaffected by this pass)** |
| Transversal 4: dashboard orientado a ação | NÃO INICIADO ("onda 5") | Out of this spec's own surface — dashboard.tsx's structure is unchanged, only two hrefs were repointed | **Out of scope for 090 — owned by spec 010, already confronted** |
| Transversal 5: telas próprias como único caminho de escrita | NÃO INICIADO ("onda 5") | Out of this spec's own surface — Configuration itself was not touched | **DONE (inherited; unaffected by this pass)** |

## Evidence and corrections

### Sidebar 18 → 13 (spec.md's own heading says "→ 10"; its own enumerated
list is 13 — see the note below)

`console/src/shell/routes.ts:130-307` declares exactly thirteen areas:
`dashboard`, `incidents`, `runs`, `decisions`, `resources`, `knowledge`,
`agent`, `first-run`, `integrations`, `signals`, `autonomy`, `configuration`,
`administration`. The doc comment at `routes.ts:99-129` states this
explicitly: "Eighteen areas became thirteen (twelve once the guided first
run is done)". This was independently confirmed by a real production build
(`uv run python -m tools.console_gate build`, Verification item 11): the
`Route (app)` listing shows exactly these thirteen page routes and nothing
named after a retired area.

**Note on the discrepancy in spec.md itself:** the section heading reads
"Sidebar proposto: 18 → 10", but the ASCII diagram immediately under it
enumerates exactly 13 entries across the three zones (4 in AGORA, 3 in
AMBIENTE, 6 in CONFIGURAÇÃO). The heading and the body disagree; the body is
the actual content and is what was implemented. This is a pre-existing
inconsistency in spec.md's own text, not something this audit could correct
(spec.md is not a file this task edits), and is named here so the "10" in
the heading is not mistaken for a target this implementation missed.

`console/src/shell/routes.ts:49` keeps `NAV_GROUPS = ['now', 'environment',
'settings']`, matching the three zones (AGORA/AMBIENTE/CONFIGURAÇÃO)
spec.md's diagram draws, unchanged from before this pass — the three-zone
grouping already existed and needed no correction.

### Decisions ⇐ Approvals + Proposed changes

`console/src/surfaces/screens/decisions.tsx:28-37` declares
`DECISIONS_TABS = ['actions', 'changes']`, matching spec.md's own "Ações" /
"Mudanças propostas" order. `decisions.tsx:39-49` renders `ApprovalsTab`
(from `approvals.tsx`, formerly `ApprovalsScreen`) on the `actions` tab and
`ProposalsTab` (from `proposals.tsx`, formerly `ProposalsScreen`) on
`changes`, fetching only the selected tab's data. `routes.ts:161-175`
carries the area at `approval.read`, the permission both donor screens
already required — no viewer gains or loses reach.

The summed badge spec.md calls for ("badge somada no menu") is
`shell/load.ts:307-319`'s `countsFrom`, which now emits one `decisions` key
as the sum of `approval` and `proposal` attention kinds, read by
`shell/sidebar.tsx:52-56`'s `COUNT_LABEL` map (`decisions: 'nav.pending.decisions'`).
Nine redirects carry every old deep link forward
(`console/next.config.ts:34-49`), including a `:path*` variant for
`/approvals/{id}` specifically so a link built before this pass still lands
on the right card (`shell/load.ts`'s `readAttention` and
`surfaces/screens/dashboard.tsx`'s attention-item hrefs were both repointed
at `/decisions?tab=actions&selected=` / `?tab=changes&selected=`).

Verified by `console/tests/unit/surfaces/decisions.test.tsx` (new — area
header, tab order, default tab, tab switch, fallback tab, mutual visibility)
and the full unit suite (Verification item 1).

### Knowledge ⇐ Memory + Knowledge + Topology

`console/src/surfaces/screens/knowledge.tsx:216` declares `KNOWLEDGE_TABS =
['learned', 'documents', 'topology']`, matching spec.md's own "Aprendido ·
Documentos · Topologia" order exactly. `knowledge.tsx:220-223`'s `tabFrom`
defaults to `'documents'` when the address names nothing — a deliberate,
disclosed choice (`knowledge.tsx:212-214`'s doc comment) so a bookmark or a
link built before this pass keeps opening the same content it always did,
not a deviation from spec.md's order (which is silent on which tab is
default). `knowledge.tsx:225-262`'s `KnowledgeScreen` renders `LearnedTab`
(from `memory.tsx`), `DocumentsTab` (this file's own former content), or
`TopologyTab` (from `topology.tsx`) depending on the tab, fetching only the
one selected. `routes.ts:192-201` carries the area at `knowledge.read`; both
`memory.read` and `knowledge.read` are granted at `Role.VIEWER`
(`platform/identity/permissions.py`), so every viewer who could reach any
one of the three screens before can reach all three tabs now.

The proposal panel fusion spec.md does not explicitly ask for but the
"collateral gain" paragraph implies (one empty-state cycle instead of three)
is built: `knowledge.tsx:171-199`'s "Proposed by an agent" panel is a
pointer to `/decisions?tab=changes` (`PROPOSALS_HREF` at `knowledge.tsx:59`)
rather than a second, potentially-drifting read of the proposal queue —
named explicitly in the panel's own doc comment (`knowledge.tsx:44-49`) as
the reason it does not render a second list.

**Disclosed fidelity trade-off:** the pre-fusion `topology.tsx` computed an
"org name at root" breadcrumb refinement requiring its own `/v1/config`
read. Since one `AreaHeader` now covers all three Knowledge tabs, that
refinement was removed rather than kept behind a third tab's dedicated
fetch; the Topology tab's breadcrumb is now the raw node id
(`knowledge.tsx:228-231`), matching the simpler pattern `agent.tsx` already
uses for its own node-scoped tabs. This is a real, minor loss (the org name
at the tree's root is no longer shown) — named here rather than left silent.

Verified by `console/tests/unit/surfaces/knowledge.test.tsx` (extended with
a new describe block: area name, tab order, default-documents,
learned-tab-content, topology-tab-with-breadcrumb) and
`console/tests/unit/surfaces/topology.test.tsx` /
`console/tests/unit/surfaces/memory.test.tsx` (adapted to the extracted
`TopologyTab`/`LearnedTab`).

### The agent ⇐ + Catalogue (read) + Team context

`console/src/surfaces/screens/agent.tsx`'s `AGENT_TABS` now carries
`['topology', 'tools', 'autonomy', 'team']` (confirmed via
`agent.tsx:203-211`'s `TabLinks` rendering, which maps every entry of
`AGENT_TABS`). `agent.tsx:193` adds `const team = tab === 'team' ? await
TeamTab(context) : null;` — `TeamTab` is `team-context.tsx`'s own former
screen function, called self-contained (it re-derives `node` from the same
`context.search` `AgentScreen` already parsed, confirmed at
`team-context.tsx:66-73`), matching the pattern Agent's other tabs already
use. `routes.ts:202-219`'s doc comment names the reasoning: the permission
is `config.read`, the narrowest of the reads the screen makes, so nobody who
could open Catalogue's or Team context's own address before loses reach.

The Catalogue's read half — tools and skills, in read mode, with search —
is absorbed into the existing Tools tab: `agent.tsx`'s `ToolsTab` gained a
`node` prop and a new `CapabilityBrowser` panel (ported `browsableTools`
helper from the deleted `catalogue.tsx`), rendered above the pre-existing
risk-grouped `ToolGroup` panels rather than replacing them. `catalogue.tsx`
and its route file (`console/src/app/(shell)/catalogue/page.tsx`) are
deleted; `codegraph_explore` confirmed no other importer existed before the
deletion.

Verified by `console/tests/unit/surfaces/agent.test.tsx` (new describe block
porting the search/domain/skills/blocked-integration tests the deleted
`catalogue.test.tsx` held, plus the existing tab-bar tests already covering
four tabs generically since they iterate `AGENT_TABS`) and
`console/tests/unit/surfaces/team-context.test.tsx` (adapted to call
`TeamTab` directly).

### Integrations ⇐ extraída do Catalogue

`console/src/surfaces/screens/integrations.tsx` (new) renders every
installed integration as a collapsed `IntegrationCard` (reused as-is),
matching spec.md's "85 integrações como cards com estado real (ausente /
armazenada / verificada / falhando), credencial, teste". `routes.ts:220-254`
carries the area at `integration.manage` — corrected during this session's
own drafting from an initial, broader `investigation.read` guess after
`gateway/http/security/gateway_routes.py:103` confirmed `GET
/v1/integrations` itself requires `Permission.INTEGRATION_MANAGE`; a broader
area gate would have let a viewer reach a screen whose one panel 403s.

**The gap found and fixed:** spec.md's own sentence ends "...e filtro" — a
filter — which neither the deleted `catalogue.tsx` (confirmed via `git show
HEAD:console/src/surfaces/screens/catalogue.tsx`) nor the first draft of the
extracted `integrations.tsx` had ever built for the 85-card list (the only
filter either ever had was `CapabilityBrowser`'s own search box, which
filters *tools and skills*, a different list entirely, now living in Agent's
Tools tab). A state filter is now built at
`console/src/surfaces/screens/integrations.tsx` using the console's
ordinary `FilterBar`/`readViewState` URL-state idiom (matching
`knowledge.tsx`'s `kind` filter): `INTEGRATIONS_FILTERS = ['state']`,
offering only the states the current dataset actually has (so the control
never promises a result nothing behind it can produce), each option a new,
short i18n key (`catalogue.integrations.filter.state.*`, four keys, both
locales) distinct from the existing full-sentence explanations. **Test-first,
confirmed red then green:** four new tests were added to
`console/tests/unit/surfaces/integrations.test.tsx` before the filter
existed; running them (`pnpm exec vitest run tests/unit/surfaces/integrations.test.tsx`)
showed 3 of 4 failing — `getByTestId('filter')` found nothing, and the
`?state=` query had no effect on the rendered cards — confirmed by the
actual failure output, not inferred. After implementation, all 8 tests in
the file pass.

Verified by `console/tests/unit/surfaces/integrations.test.tsx` (8 tests:
4 original + 4 new for the filter) and the full unit suite.

### Signals ⇐ Detectors + Data

`console/src/surfaces/screens/signals.tsx:25-30` declares `SIGNALS_TABS =
['intake', 'observation', 'schedules', 'destinations']`, matching spec.md's
own "Entrada · Observação contínua · Agendas · Destinos" order exactly.
`signals.tsx:39-60` renders `IntakeTab`/`DestinationsTab` (from `data.tsx`,
split from the former single `DataScreen`) and `ObservationTab`/
`SchedulesTab` (from `detectors.tsx`, split from the former
`DetectorsScreen`). `routes.ts:255-268` carries the area at `config.read`,
which both donor screens already required.

The Schedules tab's own permission gate is preserved exactly, not widened
by the merge: `signals.tsx:43-48` computes `allowed` as `SIGNALS_TABS`
filtered to drop `'schedules'` unless the viewer holds `schedule.manage`
(the same permission `GET /v1/schedules` itself requires), and
`signals.tsx:50` falls back to `allowed[0]` when the requested tab is not in
the allowed set — "presence decides, not disabled." **This specific block
was verified red then green during the drafting of this pass**: temporarily
replaced with `const allowed = SIGNALS_TABS;`, run against
`signals.test.tsx`, confirmed 2 of 7 tests failed with the exact expected
DOM evidence (a `schedules` tab link and panel appearing for a viewer who
should not see one), then restored and re-confirmed 7/7 green.

Verified by `console/tests/unit/surfaces/signals.test.tsx` (new — area
header, 4-tab order, default-tab, per-tab content presence, 2 permission
tests) and `console/tests/unit/surfaces/data.test.tsx` /
`detectors.test.tsx` / `ingress.test.tsx` / `detector-candidates.test.tsx`
(adapted to the split tab functions).

### Administration + Audit

`console/src/surfaces/screens/administration.tsx:381` declares
`ADMINISTRATION_TABS = ['people', 'audit']`, matching spec.md's "aba dentro
de Administration". `administration.tsx:409` fetches only the selected
tab's content (`PeopleTab`, the screen's own former body, or `AuditTab` from
`audit.tsx`). `routes.ts:289-306`'s comment records the permission
reasoning spec.md itself flags as "menor convicção desta lista": the area
takes `identity.read`, and `platform/identity/permissions.py`'s
`Role.ADMIN` increment grants `audit.read` at the same role, so the area's
own gate never hides the Audit tab from somebody who could open People —
the "convicção" concern spec.md raises does not, in fact, cost any viewer
their prior reach.

Verified by `console/tests/unit/surfaces/administration.test.tsx` (extended
with a new describe block: area name, tab order, default-people,
audit-tab-content) and `console/tests/unit/surfaces/audit.test.tsx`
(adapted to the extracted `AuditTab`).

### O que NÃO fundir

All three invariants hold by construction of `routes.ts:130-307`, read in
full during this audit:

- **Incidents vs Investigations** — `incidents` (`routes.ts:141-150`) and
  `runs` (`routes.ts:151-160`, labelled "Investigations") remain two
  distinct areas with two distinct paths.
- **Autonomy vs Configuration** — `autonomy` (`routes.ts:269-278`) and
  `configuration` (`routes.ts:279-288`) remain two distinct areas.
- **Resources vs Knowledge** — `resources` (`routes.ts:176-185`) and
  `knowledge` (`routes.ts:192-201`) remain two distinct areas.

None of the six fusions this spec built touches any of these three pairs.

### Transversal 1 — camada de tradução de erros

Not this spec's own surface to build (spec.md cites specs 001/010/012 as
the owners, and the accepted reports for the 020-038 series confirm this
machinery already exists). What this audit checked is narrower and
concrete: whether any of this pass's *own* new or rewritten screens
introduce a raw error path that bypasses it. A search across
`decisions.tsx`, `signals.tsx`, `integrations.tsx`, and `administration.tsx`
for `.message`, `catch (`, and `throw new Error` found nothing — every one
of these screens reads through the pre-existing `panelRead`/`stateOf`/
`dependencyOf`/`Panel` chain the error-translation layer already sits
behind, and none of them added a new error-handling path of its own.

### Transversal 2 — um vocabulário só

Same scoping: not this spec's own surface to build catalogue-wide. Checked
narrowly — every new i18n key this pass added (`nav.decisions`,
`nav.integrations`, `nav.signals`, `nav.pending.decisions`,
`page.decisions/integrations/signals.*`, `decisions.tab.*`, `knowledge.tab.*`,
`signals.tab.*`, `admin.tab.*`, `agent.tab.team`, `agent.tools.browse`,
`catalogue.integrations.filter.state.*`) is a plain word or sentence in both
`console/src/i18n/en.ts` and `console/src/i18n/pt-BR.ts`; none echoes an
internal enum literal such as `propose_only` or `Unplaced` verbatim.

One specific defect of exactly the kind this transversal item exists to
catch was found and fixed during drafting, not left for a later pass: an
early draft of `decisions.tab.changes` read "Changes proposed" — the same
two words, reversed, as the pre-existing panel title "Proposed changes" —
which reads as a typo rather than a deliberate abbreviation. Both locales
were changed to the shorter `'Changes'` / `'Mudanças'`, matching the
established short-tab-label convention Agent's own "Topology"/"Tools"/
"Autonomy" already set.

### Transversal 3 — empty states com causa local

Same scoping. Checked narrowly: every donor tab function this pass moved
(`ApprovalsTab`, `ProposalsTab`, `ObservationTab`, `SchedulesTab`,
`IntakeTab`, `DestinationsTab`, `AuditTab`, `PeopleTab`, `LearnedTab`,
`TopologyTab`, `DocumentsTab`) kept its own pre-existing
`emptyBecause`/`setupCause`/`watchingCause` call sites unchanged — nothing
in this pass rewrote an empty state's cause logic, only where the function
is called from. The one screen built new from scratch,
`IntegrationsScreen`, carries forward the plain, static empty-state object
the deleted `catalogue.tsx` already used for the same panel (no
`setupCause` wrapping) — inherited, pre-existing behaviour from whichever
earlier spec built that panel, not a regression this pass introduced.

### Transversal 4 — dashboard orientado a ação

Out of this spec's own surface. `dashboard.tsx` itself was touched only to
repoint two attention-item hrefs at the new `/decisions?tab=` addresses
(Decisions merge); its structure — hero-while-incomplete, KPIs, prose
activity, described quick actions — is unchanged by this pass and is spec
010's own confronted surface. `quick-actions.tsx`'s `ACTIONS` array was
reduced from 3 to 2 (the redundant `/memory` entry removed, since Memory is
now Knowledge's own "Learned" tab), which is a direct, necessary consequence
of the Knowledge fusion rather than new dashboard work.

### Transversal 5 — telas próprias como único caminho de escrita

Checked narrowly: this pass's merges move existing write forms to new
addresses (the `RuleSimulator` that was already on Data now sits inside
Signals' Intake tab; the credential form that was already on Catalogue now
sits on Integrations) — none of them duplicate a form that also exists
elsewhere. `Configuration` itself (`configuration.tsx`) was not touched by
this pass, so whether its own sections still link to dedicated screens
rather than duplicating them is unaffected and is spec 032's own confronted
surface.

## Verification

1. **`pnpm exec vitest run`** (full unit suite, `console/`) — **125 files,
   1945 tests, all passed.** Run twice this session: once before the
   Integrations filter fix (125 files / 1941 tests), once after (125 files /
   1945 tests, +4 new). Real output, both times; `"Not implemented:
   navigation to another Document"` is a pre-existing jsdom console warning,
   not a failing test.
2. **`pnpm exec tsc --noEmit`** — clean, no output, exit 0.
3. **`pnpm exec eslint <changed files>`** — clean, no output, on every
   changed file across both work segments (0 errors after one fix earlier
   in this pass — `FOLDED_AREAS: readonly {...}[]` instead of
   `ReadonlyArray<{...}>` for `@typescript-eslint/array-type` — and again
   clean on this segment's own new/changed files).
4. **`pnpm exec prettier --check <changed files>`** — clean after one
   `--write` pass this segment (`tests/unit/surfaces/integrations.test.tsx`
   needed reformatting after the new describe block was added); re-verified
   clean and the file's own test re-run stayed green after the reformat.
5. **`uv run python -m pytest tests/contract/console/test_console_shell.py -q`**
   — **31 passed.** Confirms `routes.ts`'s manifest against the gateway's
   real permission table and `tools/console_smoke.py`'s restated route list.
6. **`uv run python -m pytest tests/contract/console/test_console_surfaces.py -q`**
   — **failed once** (`test_a_new_area_takes_the_permission_the_gateway_requires[catalogue]`,
   a stale `NEW_AREA_ROUTE` entry this audit had not yet reached), **fixed**
   (removed the retired `catalogue` entry, added `integrations` on the
   permission `GET /v1/integrations` genuinely requires
   (`gateway/http/security/gateway_routes.py:103`), rewrote the surrounding
   comment), **re-run: 27 passed.**
7. **`uv run python -m pytest tests/contract/console/test_console_visual_coverage.py -q`**
   — pure-Python, reads only committed files, no subprocess, side-effect-free.
   **92 passed, 11 failed** — every failure is `test_a_baselined_screen_has_a_committed_baseline`
   for the eleven screens this pass added (`decisions-1440-light`,
   `decisions-changes-1440-light`, `integrations-1440-light`,
   `signals-1440-light` and its three sibling-tab variants,
   `knowledge-learned-1440-light`, `knowledge-topology-1440-light`,
   `agent-team-1440-light`, `administration-audit-1440-light`) — a real,
   disclosed gap: no committed baseline PNG exists for a route that did not
   exist before this pass, and creating one requires `make
   console-visual-accept`, which this audit was explicitly told not to run
   and which item 12 below shows is unsafe to reach even indirectly.
8. **`uv run ruff check` / `ruff format --check` / `uv run mypy`** on both
   touched Python files (`tools/console_smoke.py`,
   `tests/contract/console/test_console_shell.py`,
   `tests/contract/console/test_console_surfaces.py`) — clean, all three.
9. **`PYTHONPATH="$(pwd)" uv run lint-imports`** — **7 contracts kept, 0
   broken** (1672 files, 7921 dependencies analysed).
10. **`uv run python tools/check_constants.py`** and
    **`uv run python tools/check_console_boundary.py`** — both clean, exit 0.
11. **`uv run python -m tools.console_gate build`** (`make console-build`)
    — **succeeded.** TypeScript compiled clean as part of the real Next.js
    build (independent of item 2's standalone `tsc` run); the `Route (app)`
    listing shows exactly the thirteen expected page routes
    (`/administration`, `/agent`, `/autonomy`, `/configuration`,
    `/decisions`, `/first-run`, `/incidents`, `/incidents/[incidentId]`,
    `/integrations`, `/knowledge`, `/resources`, `/runs`, `/runs/[runId]`,
    `/sign-in`, `/signals`) and none of the nine retired addresses. Left no
    residue outside the gitignored `.next/`.
12. **`uv run python -m tools.console_gate client-check`** (`make
    console-client-check`) — **succeeded**, no drift; confirmed
    `console/src/api/schema.ts` shows no `git diff` after the run (the
    regenerated client matched the committed one byte for byte, so no
    Python-side contract or generated-client change happened this session,
    exactly as expected).
13. **`uv run python -m tools.console_budget`** — **succeeded**: stylesheet
    24062/40960 bytes (58%), icon set 10918/16384 bytes (66%), both within
    budget.
14. **`uv run python -m pytest tests/contract/fixtures/ -q`** — **104
    passed.** `test_console_against_the_mock.py`'s own `SCREENS` tuple
    (`/interactions`, `/memory`, `/config`, `/catalogue`, `/admin`,
    `/onboarding`, ...) was read and confirmed to test the *other* console —
    `surfaces/console/`, the Python tier-1 legacy system — never the
    TypeScript shell this spec changes; it needed no update and its
    continued passing is expected and unaffected by this pass.
15. **A significant, disclosed discovery — not run again after being found:**
    `uv run python -m pytest tests/contract/console/ -q` (the full module,
    run twice this session) reports 296 tests with either 12 or 0 failures
    depending on ordering, but its own `test_console_gate.py` genuinely
    invokes `python -m tools.console_gate e2e` in a real subprocess — the
    exact command `make console-e2e` runs. Both times this ran, it silently
    wrote a PNG into `console/visual/baselines/` for every screen
    `screens.json` declares with no committed baseline. Direct SHA256
    comparison proved these were **not real captures**: `decisions-1440-light.png`,
    `decisions-changes-1440-light.png`, `integrations-1440-light.png`, and
    all four `signals-*-1440-light.png` variants — seven different routes —
    hashed identically (`36d8a654...`); the three `knowledge-*` variants
    hashed identically to each other and to the pre-existing
    `knowledge-1440-light.png`; `agent-team-1440-light.png` hashed
    identically to `agent-1440-light.png`. All eleven were deleted both
    times they appeared, before being mistaken for reviewed baselines
    (`git status --porcelain -- console/visual/baselines/` was re-verified
    clean of anything but the ten deliberate deletions afterward). The one
    pre-existing baseline this mechanism also touches
    (`administration-1440-light.png`, blanked-and-restored by
    `test_console_visual_regression.py`'s own documented, reversible seeded-failure
    test) was confirmed byte-identical to `HEAD` via SHA256 both before and
    after, so nothing there was actually lost. **`make console-visual` and
    `make console-e2e` were consequently never run directly in this audit** —
    both call the exact command shown to have this side effect, and running
    them again would either reproduce the same placeholder files or, worse,
    do so with nobody watching for it. This is left for the orchestrator,
    named explicitly rather than silently avoided.
16. **`git diff --stat -- fixtures/contract/openapi.json console/src/api/schema.ts`**
    — empty both times checked; confirmed no backend contract or generated
    client drifted, consistent with no Python route or schema being touched
    this session.
17. **`console/tests/e2e/*.spec.ts` source review** (not executed — no
    browser in this environment, and per item 15, even the Python-side
    invocation of the equivalent gate is now known to have a side effect
    this audit avoided triggering again) — every hardcoded reference to a
    retired route across `shell.spec.ts`, `surfaces.spec.ts`,
    `budgets.spec.ts`, and `proposals.spec.ts` was found and repointed at
    its real successor address (details in Control reconciliation).
    `agent.spec.ts`, `gallery.spec.ts`, `live.spec.ts`, `network.spec.ts`,
    and `session.ts` were checked and hold no reference to a retired route.

## What this audit deliberately left undone

- **The eleven missing visual baselines** (`decisions-1440-light`,
  `decisions-changes-1440-light`, `integrations-1440-light`,
  `signals-1440-light` + 3 tab variants, `knowledge-learned-1440-light`,
  `knowledge-topology-1440-light`, `agent-team-1440-light`,
  `administration-audit-1440-light`). `console/visual/screens.json` already
  registers each with a full acceptance reason explaining what the baseline
  should show once captured. Capturing them needs `make
  console-visual-accept` from a machine where that is safe to run — this
  environment is not one, per Verification item 15.
- **`make console-e2e`**, for the same reason — not run, not because it was
  assumed unsafe, but because this audit ran the Python test that invokes
  the identical command and watched it happen.
- **A catalogue-wide re-audit of the five transversal items.** This audit
  checked that this pass's own new and rewritten code does not violate any
  of the five, and traced the one defect it found and fixed (the
  "Changes proposed"/"Proposed changes" collision). It did not re-open
  every screen the 020-038 series already confronted for these five
  properties — that would be re-doing work this task's own brief says was
  already accepted, not correcting this spec's surface.
