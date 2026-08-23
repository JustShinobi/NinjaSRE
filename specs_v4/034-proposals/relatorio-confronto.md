# 034 Proposals — implementation confrontation

Date: 2026-08-14.

## Conclusion

`controle.md` was accurate about item 1 and wrong, in the understating
direction, about items 2 and 3 — the same direction 013 Approvals', 031
Autonomy's and 033 Team context's confrontations already found this series
prone to. All three of `spec.md`'s numbered problems were present as rows (no
row was silently dropped the way 024 Knowledge's confrontation found), so the
drift here is entirely in the verdicts, not in the table's shape.

Item 1 — the endpoint that answered nothing — checks out exactly as
`controle.md` describes, and independent verification (running the cited
tests rather than trusting the count) confirms it: `bc26d76`, a prior-wave
commit already at `HEAD`, widened `gateway/http/routes/proposals.py`'s
`_queue` and the two `ProposalQueue` classes it composes
(`platform/proposals/service.py`, `platform/knowledge/proposals.py`) to treat
a scope naming no team as "every team's," which is the shape the durable,
organisation-wide credential first run establishes actually has — while
keeping the write path scoped to each proposal's own team through a new
per-call applier (`KnowledgeApplierByProposalTeam`,
`gateway/http/routes/proposals.py:146`), so the queue can be read
organisation-wide without a knowledge approval ever landing in the wrong
team's corpus. `tests/unit/gateway/http/test_proposal_routes.py` — 8 tests,
all driving the real ASGI application rather than a mock, including the two
that pin this exact regression — passed, run rather than read.

Items 2 and 3 were both marked `NÃO INICIADO`, and both were substantially
built by another prior-wave commit already at `HEAD`,
`a53a009` ("give the console one vocabulary, and name the column a sort is
about"), whose own message says outright what it did to this screen: it added
the mutual cross-link to Approvals (permission-gated, composed from the
target area's own canonical title so it can never say a different name than
the sidebar does), and it made the empty state's mechanism sentence the
*same* catalogue string Knowledge's own panel uses for the identical concept,
rather than a paraphrase of it — literally the two things items 2 and 3 ask
for. `controle.md`'s own text for item 3 ("o texto existe no i18n; a
reescrita segue pendente") is not merely stale, it describes a state the
code was never in: the text was already wired through `setupCause` and
`emptyBecause`, the same mechanism eight other screens in this console share,
verified here by running the two existing tests that pin both branches
(setup outstanding, setup complete) rather than reading them.

What `a53a009` missed is one line short of the fix it made for the sibling
problem in the very same commit. That commit unified Runs' sidebar, page
title *and panel title* to one word ("Investigations everywhere"), but on
this screen it unified the sidebar, the page title and the cross-screen
wording — and left the one panel on this exact page carrying a third,
independently-worded name for itself: `proposals.title` read "Changes the
agent has proposed" in English (and "Mudanças propostas pelo agente" in
Brazilian Portuguese) immediately beneath a page header that already says
"Proposed changes" ("Mudanças propostas"). That is the literal shape item 2
names — a sidebar name, and a *second* name for the identical concept, one
scroll away — just one level deeper than where the prior wave looked. Fixed
here, test-first, confirmed red against the unmodified catalogue before the
edit, mirroring the exact precedent `a53a009` itself set for Runs rather than
inventing a new caption.

One thing outside `spec.md`'s own three items was found and corrected while
editing the one file this confrontation touched for its test: the
pre-existing docstring in `proposals.test.tsx` cited "(spec 034, item 2)" and
"(spec 034, item 3)" directly in a comment, which this repository's own
`CLAUDE.md` forbids in committed source and tests. My own first draft of the
new bullet copied that exact pattern into new text; caught before finishing,
and all three citations in that one docstring — not only the new one — are
rewritten to state the substance instead. The identical pattern (`SC-001`,
`FR-005`, and similar) is present, pre-existing, in several other files this
spec does not reach (`screens.test.tsx`, `contrast.test.ts`,
`src/live/reducer.ts`) — traced, named below, and deliberately not touched,
because fixing them is not this spec's surface.

## Table

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. `/v1/proposals` did not respond | FEITO (`bc26d76`) | Confirmed accurate. `gateway/http/routes/proposals.py:116`'s `_queue` no longer rejects a team-less (organisation-wide) credential; `platform/proposals/service.py:313`'s and `platform/knowledge/proposals.py:383`'s `_scoped` both widened the same way, and a per-proposal `KnowledgeApplierByProposalTeam` (`gateway/http/routes/proposals.py:146`) keeps the *write* scoped to the proposal's own team regardless. `tests/unit/gateway/http/test_proposal_routes.py` — 8/8 passed, run rather than read, including the two tests that pin this exact regression by name. | DONE (no change) |
| 2. Screen name vs route vs concept | NÃO INICIADO ("Onda 4") | Wrong on both halves. The cross-link and the shared empty-state sentence (both explicitly what item 2 asks for) were already built by `a53a009`, a prior-wave commit — confirmed by running the existing tests, not reading the commit message. What neither `a53a009` nor any later commit caught: the one panel on this exact page carried its own, third phrasing of the concept (`proposals.title`, distinct from `page.proposals.title`), immediately beneath a page header that already names it correctly — the identical defect class `a53a009` fixed for Runs/Investigations in the same commit, missed here. | DONE — cross-link and shared wording: no change (already correct); panel title: fixed here, test-first |
| 3. The healthy empty state needs the same pattern other screens use | NÃO INICIADO ("texto existe... reescrita pendente") | Wrong. Already fully built by the same prior-wave commit (`a53a009`): `proposals.tsx:93-103` reads the setup checklist, resolves `setupCause`, and threads it through `emptyBecause` — the identical mechanism 021 Topology's, 023 Memory's and 024 Knowledge's confrontations already found shared across eight screens — explaining both where a proposal originates and in what deployment state that is possible. Confirmed by running, not reading, the two existing tests that pin both branches. | DONE (no change) |

## Evidence and corrections

### 1. `/v1/proposals` did not respond — confirmed fixed, verified independently

`controle.md`'s own account names the root cause precisely: the proposal
queues refused an organisation-wide credential with no team (`400`), which is
exactly the credential shape the durable token first run establishes carries
— confirmed by reading `bc26d76`'s own commit message
("the durable credential first run establishes is one") rather than taking
it at face value. Reading the diff itself, three collaborators changed
together:

- `gateway/http/routes/proposals.py:116-141`'s `_queue` no longer raises
  `bad_request` when `scope.team_node_id` is empty; it builds a
  `KnowledgeApplierByProposalTeam` (`:146-183`) instead of one fixed
  `KnowledgeQueue` scoped to the caller.
- `platform/proposals/service.py:313-329`'s `_scoped` treats an empty
  `own_team` as "matches every team's proposals" rather than only its own,
  and `pending()` (further down the same file) mirrors the same relaxation.
- `platform/knowledge/proposals.py:383` carries the identical widening for
  the knowledge-origin queue specifically.

The write path is not widened the same way: `KnowledgeApplierByProposalTeam`
(`gateway/http/routes/proposals.py:146-183`) builds a fresh, team-scoped
applier *per proposal it applies*, from the proposal's own
`team_node_id` rather than the reviewer's scope — so an organisation-wide
reviewer can decide any team's knowledge proposal, but the write still lands
in that proposal's own corpus, never wherever the reviewer happens to be
scoped. This is the invariant `controle.md` names ("o applier de knowledge é
construído no apply, escopado ao team da própria proposta") and it holds,
confirmed by reading the class rather than trusting the sentence describing
it.

Run, not read: `uv run python -m pytest
tests/unit/gateway/http/test_proposal_routes.py -q` — **8 passed**, including
`test_an_org_scoped_credential_reads_an_empty_queue_not_an_error` (`:209-229`)
and `test_an_org_scoped_reviewer_sees_and_decides_every_teams_proposals`
(`:232-252`), both driving the real `create_app(state)` over
`ASGITransport`/`AsyncClient` rather than a stub. `uv run python -m pytest
tests/unit/gateway/http/test_proposal_routes.py
tests/unit/gateway/http/test_proposal_loop.py tests/unit/platform/proposals
tests/unit/platform/knowledge/test_proposals.py
tests/unit/platform/knowledge/test_proposal_characterisation.py -q` —
**62 passed**. The whole gateway tier, `uv run python -m pytest
tests/unit/gateway -q` — **645 passed**.

**On the acceptance criterion "Teste de contrato cobrindo a rota."** This
repository has no `tests/contract/` directory devoted to gateway HTTP routes
— confirmed by listing every subdirectory of `tests/contract/` and grepping
it for "proposal" — and every comparable route (`test_config_write_routes.py`,
`test_incident_routes.py`, and this file itself) lives under
`tests/unit/gateway/http/` while still driving the real ASGI application
end-to-end, which is what a contract test is for: proving the wire behaviour
rather than a mocked collaborator's. `test_proposal_routes.py`'s own module
docstring says as much ("Driven through the running gateway rather than
against the service, because every acceptance this feature is judged on is
about what a *person* can reach"). This is the shape the acceptance
criterion is satisfied in, in this repository, and it is the same shape 032
Configuration's confrontation treated `test_config_write_routes.py` as
adequate route coverage without moving it. The console-level walk this
spec's own text cites as the "spec_v3 050" pattern — `tools/console_smoke.py`
(`SHELL_PATHS`, `:49-67`, includes `/proposals`) — was also confirmed: it
checks that every shell route answers `200` while signed in, which this
outage never violated (`panelRead` turns a failed dependency into an
in-page `ErrorState`, never a page-level `500`), which is exactly why
`spec.md` says the pattern was "followed in form" while "the cause remained
alive" — the smoke walk cannot see inside a panel, only the page's own status
code, confirmed by reading `tools/console_smoke.py` end to end.

No change was made for this item.

### 2. Screen name vs route vs concept — partially already done, the residual fixed here

**Already correct, confirmed by running rather than reading.**
`console/src/surfaces/screens/proposals.tsx:105,114-122` renders the
cross-link to Approvals, gated on `may(viewer, approvals.permission)`, with
its link text composed from `message(locale, approvals.title)` —
`approvals.title` here is the *area's* own title field
(`'page.approvals.title'`), so the link can never say anything other than
whatever the sidebar and Approvals' own page header currently say. The
symmetric line on `approvals.tsx:293-300` does the identical thing in
reverse, confirmed by reading both files side by side. Both were built by
`a53a009` (further refined by `0f82401`), a prior-wave commit already at
`HEAD` before this confrontation touched anything, and are pinned by
`proposals.test.tsx`'s existing `describe('the proposals screen and the
approvals queue it is not', ...)` block, run and passing before any change.

The empty-state body is the second, more literal half of what item 2 quotes
("empty states de outras telas dizem 'proposes the change here'"):
`proposals.tsx:98` reads `body: message(locale,
'knowledge.proposals.empty.body')` — the *same* catalogue key Knowledge's own
"Proposed by an agent" panel declares for its own (structurally unreachable,
per 024 Knowledge's confrontation) empty state
(`console/src/surfaces/screens/knowledge.tsx:179`). Rather than writing a
second sentence that happens to agree with the first, this screen reads the
identical string, so the two can never drift independently — exactly what
`a53a009`'s own commit message claims ("its empty state adopts the sentence
the Knowledge screen already uses for the same concept, so a proposal is
described the same way wherever it is mentioned"), verified here by reading
both call sites rather than trusting the sentence describing them.

**The residual: one panel, two names, one page.**
`console/src/surfaces/screens/proposals.tsx:124-128` (unchanged by this
edit):

```tsx
<Panel
  title={message(locale, 'proposals.title')}
  state={stateOf(queue, proposals.length === 0)}
  dependency={dependencyOf(queue)}
  labels={panelLabels(locale, message(locale, 'proposals.title'))}
  empty={empty}
  bare
>
```

Before this confrontation, `proposals.title` (`en.ts:1378`, pre-edit) read
"Changes the agent has proposed" — a third, independently-worded name for
the exact concept `page.proposals.title` (`en.ts:79`) and `nav.proposals`
(`en.ts:29`) already both call "Proposed changes," rendered as an `<h3>`
directly beneath the `<h1>` that already says so
(`console/src/shell/area.tsx:43-70`'s `AreaHeader`/`PageHeader`). This panel
is the whole of this page's content — not a filtered sub-view the way
"Episodes" is one of two panels on Memory, or "Investigations" is a specific
domain word chosen once and reused everywhere for Runs — so a *different
construction of the same three words* here is a second name for one
concept, not a more specific one. Two screens in this exact console
(`incidents.tsx:212-213`, `detectors.tsx:128-129`) already establish the
alternative, accepted pattern for a page whose one panel *is* the page: the
panel's own title reads exactly what the page title reads
(`incidents.list.title`/`page.incidents.title` both "Incidents";
`detectors.list.title`/`page.detectors.title` both "Detectors"). And
`a53a009` — the very commit that left this instance alone — is the commit
that established the "one name per concept" fix in the first place, applied
to Runs/Investigations in the same diff: "The sidebar said Runs, the page
title said Investigations… The catalogue now says Investigations
everywhere." The identical fix was not carried over to this screen's own
panel.

Test-first: `console/tests/unit/surfaces/proposals.test.tsx`'s new test,
`'names its one panel the same thing the sidebar and the page title already
do'` (`:87-98`), scopes a query to the rendered panel
(`within(screen.getByTestId('panel'))`) and asserts it contains "Proposed
changes," and that "Changes the agent has proposed" is absent from the page
altogether. Run against the code exactly as it stood, before any catalogue
edit: **failed** —
`TestingLibraryElementError: Unable to find an element` inside the panel
scope, confirmed red. Fixed by:

```
console/src/i18n/en.ts:1378 (now :1381, after the added comment)
- 'proposals.title': 'Changes the agent has proposed',
+ 'proposals.title': 'Proposed changes',

console/src/i18n/pt-BR.ts:1297 (now :1300)
- 'proposals.title': 'Mudanças propostas pelo agente',
+ 'proposals.title': 'Mudanças propostas',
```

After the fix, the new test and the file's other 12 tests all pass
(`proposals.test.tsx`: **13 passed**).

**Considered and left alone: `knowledge.proposals.title`.**
`console/src/surfaces/screens/knowledge.tsx:167` titles its own panel
"Proposed by an agent" — a *different* screen's caption for a filtered view
of the same underlying queue (per this spec's own established fact,
`platform/proposals/models.py:81`'s `ProposalType.KNOWLEDGE`, a proposal of
the knowledge kind sitting in the same queue this screen shows unfiltered).
I considered renaming this to match, and declined: it is a locally-scoped
caption in the same pattern as "Episodes" or "Documents" elsewhere in this
console, not a claim to *be* the `/proposals` screen's own name, and 024
Knowledge's confrontation already closed the specific acceptance criterion
this key is about — "a relação... está explícita" — by making the panel's
lead sentence say in words that this is "the same queue as every other
proposed change" (`knowledge.proposals.lead`, fixed by that confrontation,
unchanged here). Renaming Knowledge's own panel caption is Knowledge's
surface, already confronted and accepted; nothing there was touched.

**Considered and left alone: the identical defect, one screen over.**
Reading `approvals.tsx` to confirm its own half of the cross-link surfaced a
second instance of the exact category of bug just fixed here, on a screen
this spec does not reach: `approvals.tsx:304`'s panel title reads
`message(locale, 'approvals.title')` = "Waiting on a decision"
(`en.ts:680`), immediately beneath a page header that already says "Actions
awaiting approval" (`page.approvals.title`, `en.ts:76`, the name 013
Approvals' confrontation gave this screen). Neither `spec.md`'s own text
here nor 013 Approvals' own three problems name this — it is a genuinely new
finding, not a re-litigation of either spec's closed items — and it belongs
to whichever confrontation next revisits Approvals (013) or runs a
console-wide naming sweep, not to this one. Named here rather than silently
fixed or silently dropped.

**Traced and confirmed out of scope: the singular `proposal.*` namespace.**
`console/src/surfaces/proposal.tsx` (`ProposalRow`) and
`console/src/surfaces/decision.tsx`, both offered as likely starting points,
were checked via their actual callers: `ProposalRow` is imported only by
`approvals.tsx`, and `decision.tsx` only by `approvals.tsx` — confirmed by a
repository-wide search for each import. Neither is reachable from
`proposals.tsx`, whose own review component is `proposal-review.tsx`
(`ProposalReview`), a different file entirely. This is worth naming because
the catalogue namespace collision is real — `proposal.title` ("Proposed
action — awaiting your decision", `en.ts:693`, an Approvals-queue action) and
`proposals.title` (this screen's own panel, just fixed) share almost the
same key for two different concepts — but it belongs to Approvals' own
surface, not this one, and nothing there was touched.

### 3. The healthy empty state — already built, verified rather than assumed

`console/src/surfaces/screens/proposals.tsx:93-103` (unchanged by this
confrontation):

```tsx
const setup = await readSetupState(credential);
const cause = setupCause(locale, setup);
const empty = emptyBecause(
  {
    heading: message(locale, 'proposals.empty.heading'),
    body: message(locale, 'knowledge.proposals.empty.body'),
    actionLabel: message(locale, 'proposals.empty.action'),
    href: '/runs',
  },
  cause,
);
```

This is the identical `setupCause`/`emptyBecause` mechanism
`console/src/surfaces/emptiness.ts:45-53,79-87` gives eight other screens
(`memory.tsx`, `topology.tsx`, `knowledge.tsx`, `data.tsx`, `approvals.tsx`,
`incidents.tsx`, `detectors.tsx`, and this one — confirmed by
`codegraph_explore`'s own blast-radius listing for `setupCause`), and it is
exactly "o mesmo padrão das demais telas" item 3's own title asks for: while
setup is unfinished, `cause` replaces the heading's body and action with how
many steps remain and a link to `/first-run`; once setup is finished,
`cause` is `null` and the mechanism sentence renders instead —
`knowledge.proposals.empty.body`'s "When an investigation learns something
worth writing down it proposes the change here rather than making it,"
which is item 3's own parenthetical ("investigação que aprende algo →
propõe mudança de config/knowledge") close to verbatim — pointing at
`/runs`, "in what deployment state this is possible" being "once
investigations have actually run."

Run, not read: `pnpm exec vitest run tests/unit/surfaces/proposals.test.tsx
-t "an empty queue that says where a proposal would come from"` — **2
passed**, both against the code exactly as it stood before this
confrontation touched anything: `'names the investigation mechanism once the
setup is done'` and `'prefers the setup cause when the deployment has never
investigated'`. `describe('a deployment nobody has proposed anything to',
...)`'s `'says so as an empty state rather than as an error'` — **passed**
too, confirming the screen genuinely renders a healthy empty state (not an
error) for a populated-but-decided-nothing queue.

No gap was found here to pin, so nothing was changed. `controle.md`'s own
account — "o texto existe no i18n; a reescrita segue pendente" — is not a
close approximation of this: the text was not merely present, it was already
wired through the exact causal-chain mechanism the item's own title names,
and both branches were already regression-tested.

### A rule violation, found and fixed in the one file touched for this spec

`console/tests/unit/surfaces/proposals.test.tsx`'s own docstring, unchanged
since `a53a009`, cited "(spec 034, item 2)" and "(spec 034, item 3)" directly
in a comment — a specification number in committed test source, which this
repository's own `CLAUDE.md` states plainly must never appear there ("a
contributor cloning this repository does not have those documents"). My own
first pass at the new third bullet copied the same citation shape into new
text before I caught it. Corrected: all three bullets in that one docstring
(`:18-25`) now state the substance with no citation at all, and the new
third bullet does not introduce one either. A repository-wide search
(`spec [0-9]{2,3}\b|spec_v[0-9]|FR-[0-9]|SC-[0-9]{3}`) found the identical
pattern, pre-existing, in several files this spec does not reach —
`console/tests/unit/surfaces/screens.test.tsx` (`SC-001`, `SC-006`,
`SC-007`), `console/tests/unit/design/contrast.test.ts` (`SC-001`),
`console/src/live/reducer.ts` (`FR-005`), and others — named here so the
pattern is not rediscovered as new by whichever confrontation next reaches
one of those files, and deliberately not touched: fixing them is not this
spec's surface.

### Traced and confirmed not applicable: `OrgNav`/`tree.tsx`

Offered as a likely starting point if this screen grows an Organisation
panel. It does not have one, and does not need one: `proposals.tsx` renders
a flat queue across whatever scope the caller's credential covers, with no
per-node tree or breadcrumb at all — confirmed by reading the whole file.
Nothing here needed touching.

## Verification

Console, from `console/`:

- `pnpm exec vitest run tests/unit/surfaces/proposals.test.tsx` — run
  **before any change**: **12 passed (12)**, confirming item 1's
  reachability and item 3's two existing empty-state tests by running them
  rather than reading `controle.md`'s account. After adding the new
  panel-title test, **before** its fix: **1 failed | 12 passed (13)** —
  confirmed red (`Unable to find an element` inside the panel scope). After
  the catalogue fix: **13 passed (13)**.
- `pnpm exec vitest run tests/unit/surfaces/proposals.test.tsx
  tests/unit/surfaces/approvals.test.tsx tests/unit/surfaces/knowledge.test.tsx
  tests/unit/surfaces/dashboard.test.tsx
  tests/unit/surfaces/proposal-review.test.tsx
  tests/unit/surfaces/proposal-route.test.ts tests/unit/i18n` — **84 passed
  (8 files)**, confirming nothing adjacent (the cross-links, the shared
  empty-state sentence, the dashboard's attention band, the catalogue
  completeness/fallback tests) regressed.
- `pnpm exec vitest run` (full unit suite) — **2006 passed (122 files)**, net
  +1 over the 2005 recorded at this branch's own prior commit (033 Team
  context's own last-recorded count), matching the one new test this
  confrontation added. One benign jsdom console line ("Not implemented:
  navigation to another Document") is the same pre-existing
  test-environment noise every prior confrontation in this series has
  recorded, not a failure.
- `pnpm exec tsc --noEmit` — clean, no output.
- `pnpm exec eslint src/i18n/en.ts src/i18n/pt-BR.ts
  tests/unit/surfaces/proposals.test.tsx` — clean, both before and after the
  citation cleanup.
- `pnpm exec prettier --check` on the same three files — "All matched files
  use Prettier code style!"
- `make console-client-check` — clean; `git status` on `src/api/schema.ts`
  and `fixtures/contract/openapi.json` shows no diff, confirming no backend
  contract changed.
- `make console-build` — succeeded, all 47 routes including `/proposals`
  compiled, run before every build-dependent gate below per the standing
  instruction that `console-visual` alone never rebuilds.
- `make console-budget` — stylesheet 24062/40960 bytes (58%), icon set
  10918/16384 bytes (66%), unchanged (no new token, no new icon).
- `make console-visual` — **34 passed, 1 failed**: `proposals-1440-light`,
  reproducibly (658 pixels, 0.01 of the image). The diff image was inspected
  directly and shows exactly the intended change: the panel heading's text,
  in the one line directly under the cross-link sentence, and nothing else
  on the page moved or changed. Per instruction, **this baseline is not
  accepted here** — left for the orchestrator, who already knows the
  convention and will recapture it.
- `make console-e2e` — **84 passed (0 failed)** across both Playwright
  projects (`behaviour`, 79; `first-day`, 5), including
  `tests/e2e/proposals.spec.ts`'s three tests by name — none of them assert
  the panel title text, so none needed changing, and their pass confirms the
  approval-bypass behaviour this confrontation did not touch is intact.
- `uv run python -m pytest tests/contract/console/ -q` — **1 failed, 297
  passed** — the failure is `test_the_untouched_baselines_still_match`, the
  Python-side mirror of the same, expected `proposals-1440-light` diff just
  described; not a new or different failure.
- `uv run python -m pytest tests/contract/fixtures/ -q` — **101 passed**,
  confirming the catalogue-only edit did not disturb the mock data plane's
  own contract (no route, no shape, no behaviour changed — only rendered
  text).
- `test-results/` and `playwright-report/` (both gitignored,
  `console/.gitignore:8-9`) were removed after every browser and contract
  run, the same gap 025 Catalogue's, 031 Autonomy's and 033 Team context's
  confrontations already recorded.

On the environment note that `pnpm exec playwright` and `pnpm visual:accept`
do not work here: neither was invoked. `make console-visual` and
`make console-e2e` go through `tools.console_gate`/`tools.console_e2e` rather
than a raw `pnpm exec playwright` call, and both completed to a real result.
I did not run `make console-visual-accept` under any circumstance; the one
baseline that differs is named above, with the diff inspected and the cause
confirmed, and left for the orchestrator.

Python, from the repository root:

- `uv run python -m pytest tests/unit/gateway/http/test_proposal_routes.py
  tests/unit/gateway/http/test_proposal_loop.py
  tests/unit/platform/proposals
  tests/unit/platform/knowledge/test_proposals.py
  tests/unit/platform/knowledge/test_proposal_characterisation.py -q` —
  **62 passed**, confirming item 1's fix by running it rather than reading
  the prior wave's commit message.
- `uv run python -m pytest tests/unit/gateway -q` — **645 passed**, the
  whole tier the changed route lives in.
- No Python file was changed in this confrontation, so `ruff`/`mypy` were
  not run — there is nothing of this confrontation's own for them to check;
  the suites above were run to *verify* the backend's current, correct
  behaviour, not to check an edit to it.
- `KNOWN PRE-EXISTING, not mine:`
  `tests/contract/integrations/test_integration_parity.py::test_each_paginated_endpoint_declares_a_style_the_base_client_walks[google_gemini]`
  was not re-run — no file this confrontation touched could affect it.

**On confirming new tests red first.** The one genuinely new assertion this
confrontation added — the panel-title test for item 2's residual — was
confirmed red against the code exactly as it stood immediately before its
own fix, in the words above, not inferred. Items 1 and 3 needed no new test:
the existing tests `controle.md` marked `NÃO INICIADO` (item 3) or attributed
to a different cause (item 1) were *run*, not read, against the tree exactly
as this confrontation found it, and all passed — which is what stands in for
red-before-green when nothing was broken, the convention 021 Topology's, 023
Memory's, 024 Knowledge's, 031 Autonomy's and 033 Team context's
confrontations used for the same situation.

## Control reconciliation

`specs_v4/034-proposals/controle.md` is rewritten so all three rows state
the verified status and point at this report. Item 1 keeps `FEITO`, its
detail corrected to cite what was independently re-run (8/8, then 62, then
645) rather than repeating the prior wave's prose unchanged, and to answer
the "teste de contrato" acceptance criterion by name. Item 2 moves from `NÃO
INICIADO` to `FEITO`: the cross-link and the shared empty-state sentence
were already correct (no change), and the one genuine residual — the
panel's own third name for the concept — is fixed here, test-first. Item 3
moves from `NÃO INICIADO` to `FEITO`, with the record corrected that the
control's own account ("a reescrita segue pendente") was not a close reading
of a mechanism that was already fully built and tested. A closing note
records the one baseline left for the orchestrator
(`proposals-1440-light`), the rule violation found and fixed in the one file
this confrontation edited, the two deliberately-declined findings
(`knowledge.proposals.title`, left to Knowledge's own accepted surface; and
the identical panel-title defect on Approvals, left to whichever
confrontation next reaches spec 013 or a naming sweep), and the confirmation
that `proposal.tsx`/`decision.tsx`, offered as likely starting points,
belong entirely to Approvals and were not reached by this screen.
