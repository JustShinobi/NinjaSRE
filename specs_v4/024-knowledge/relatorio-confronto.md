# 024 Knowledge — implementation confrontation

Date: 2026-08-13

## Conclusion

The control file drifted in the direction 022 Detectors' confrontation already
saw once: not wrong about what it tracked, but silent about a third of what
`spec.md` actually asks for. `controle.md` carried two rows, `FEITO` on both,
for items 1 and 2 — and both verdicts hold up: reading
`console/src/surfaces/screens/knowledge.tsx` line by line, then tracing the two
routes `gateway/http/routes/knowledge.py` declares and the two ingestion paths
(`platform/knowledge/base/sync/port.py`'s `KnowledgeSync`, wired only into a
background job dispatcher with no HTTP route, and
`capabilities/tools/system/knowledge_propose/tool.py`'s `propose_knowledge`,
which queues into the one proposal store `/v1/proposals` reads) confirmed there
genuinely is no ingestion control anywhere in this console, and that "Proposed
by an agent" genuinely does not render a second copy of the proposal queue.
Item 3 — "Filtro 'Kind: Any' único; dois painéis de vazio empilhados… Mesmos
reparos da spec 023" — was not in the table at all. Not marked done, not
marked outstanding: absent, and a repository-wide search of `console/src` and
`console/tests` found nothing that had ever pinned it. Reading the code proved
the two halves of that dropped item were in two different states — the
two-panels-of-the-same-empty half was already structurally impossible, a side
effect of item 2's earlier redesign, and provably so by reading `stateOf`
against a hard-coded `false`; the single-"Any"-filter half was live and
reproducible on both the `empty` and `first-run` fixture scenarios, because
`FilterBar`'s `choices` array was never filtered to drop an option-less choice
the way `memory.tsx`'s was. Both are named as one item in `spec.md`, and this
report treats the drop as one gap: `controle.md` owed the reader a row it
never wrote.

Item 2 needed a second, narrower correction beyond what the structural fix
already gave it. `spec.md`'s problem states the test in words the report holds
itself to: "se é a mesma fila filtrada... os textos precisam dizer isso," and
the acceptance criterion repeats it — "a relação... está explícita." The
existing implementation satisfied the *behavioural* half (no second list is
ever rendered; the one control on the panel links to the real queue) but the
*textual* half was still silent: the visible sentence read "Changes an
investigation proposed, awaiting review." — true, and answering neither "is
this a separate queue" nor "is it the one Proposed changes shows." That is the
same shape 020 Resources found three times over (structure fixed, explanation
missing), and it is fixed the same way: not a UI restructuring, a corrected
catalogue sentence, in both locales together so neither drifts from the other.

Three genuine gaps this audit found and closed, all with a test confirmed red
first except where noted: the missing explicit-relationship sentence (item 2),
the un-hideable single-option "Kind" filter (item 3), and two European
Portuguese leaks reachable from this screen — `'knowledge.column.updated':
'Actualizado'` and, on the very same catalogue line group,
`knowledge.documents.empty.body`'s
"nenhum **controlo** de upload" (the noun, not the verb — the same PT-PT/PT-BR
split "controlo remoto" vs. "controle remoto" makes famous). Both were on
adjacent lines of the same block; fixing only the first and missing the second
is exactly the "one line short" failure this audit was warned to watch for, so
both are corrected together. `tree.tsx`, named as a likely starting point, was
checked and is not reached from this screen at all — its callers are
`catalogue.tsx`, `topology.tsx`, `team-context.tsx`, `autonomy.tsx`,
`agent.tsx`, `configuration.tsx`, and `approvals.tsx`, never `knowledge.tsx` —
so nothing there needed touching, and nothing was.

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. "Configure ingestion" sem destino claro | FEITO (onda 3) | Confirmed accurate. `knowledge.tsx`'s empty state names the two real paths a document can arrive by and points its action at `/proposals`, the only one reachable from the console; verified against the gateway (two GET-only routes) and the two backend ingestion mechanisms. | DONE (no change) |
| 2. "Proposed by an agent" duplica a fila de Proposals? | FEITO (onda 3) | PARTIAL. The structural half (no second list, one link to the real queue) was already correct and tested. The acceptance criterion's textual half — the relationship stated *explicitly* — was not: the visible sentence never said this is the same queue Proposed changes shows. | DONE (fixed — catalogue text only) |
| 3. Filtro "Kind: Any" único; dois painéis de vazio empilhados | **Not tracked — absent from `controle.md` entirely** | Split. The two-panel half was already structurally impossible (a side effect of item 2's earlier fix), confirmed by reading `PROPOSALS_POINTER`/`stateOf`, no gap. The filter half was live: `FilterBar` rendered a "Kind ▾ [Any]" control with zero real options on both the `empty` and `first-run` scenarios, unlike `memory.tsx`'s filters, which drop an option-less choice. | Panel half: DONE (no change). Filter half: DONE (fixed) |

## Evidence and corrections

### 1. "Configure ingestion" without a destination

`console/src/surfaces/screens/knowledge.tsx:130-142` composes the Documents
panel's empty state through `emptyBecause({..., href: PROPOSALS_HREF}, cause)`
(`PROPOSALS_HREF = '/proposals'`, `:52`), so a viewer with an unfinished setup
is sent to `/first-run` (via `setupCause`) and a viewer whose setup is finished
but whose corpus is still empty is sent to `/proposals` — never to
`/configuration`, which is what the bug report actually quoted. The catalogue
text answers "what, from where, how" directly:
`knowledge.documents.empty.body` (`en.ts:860-861`) — "A document reaches this
corpus when the sync your deployment was set up with brings it in, or when an
investigation proposes one and a reviewer approves it."

I re-verified `controle.md`'s own claim that no ingestion control exists,
rather than trusting the prior wave's prose. `gateway/http/routes/knowledge.py`
declares exactly two routes, both `GET`
(`list_documents` at `:60-69`, `get_document` at `:72-94`); a repository-wide
search of every `gateway/http/routes/*.py` for a `POST`/`PUT`/`PATCH`/`DELETE`
route naming knowledge, sync, ingest, or document found nothing. The two real
paths: `platform/knowledge/base/sync/port.py`'s `KnowledgeSync`, instantiated
only inside `gateway/http/scheduled_work.py`'s `dispatcher_for`
(`:45-63`) and driven by the background `ScheduledJobWorker` — no `@router`
anywhere in that file, so nothing in the console can trigger it — and
`capabilities/tools/system/knowledge_propose/tool.py`'s `propose_knowledge`
(`:95-165`), which queues a `KnowledgeProposal` and returns a receipt that
says outright the document is **not** written and a search will not find it.
Both match `platform/AGENTS.md`'s own description of this package: "There is
no path from an agent's proposal to the corpus without a human."

Test: `console/tests/unit/surfaces/knowledge.test.tsx`'s two existing
`describe` blocks ("a deployment still being set up",
"a finished deployment that has ingested nothing yet") were run, unmodified,
against the current tree before this audit touched anything — both passed.
No change made to this item.

### 2. The relationship was behaviourally true and textually unstated

`console/src/surfaces/screens/knowledge.tsx:166-194` (the "Proposed by an
agent" panel) never fetches and never renders a second `RowList` — its
`state` is hard-coded ready (`PROPOSALS_POINTER = { status: 'ready', data:
undefined }`, `:61`; `stateOf(PROPOSALS_POINTER, false)`, `:174`, always
returns `'ready'` because the second argument is a literal `false`). That is
the structural half of "duplica a fila de Proposals?", and it was already
correct: one link (`data-testid="proposals-link"`, `href="/proposals"`), no
second list, confirmed by the existing test
(`knowledge.test.tsx:108-123`, `'points at the one proposal queue instead of
rendering a second copy of it'`), run before any change and passing.

What was missing is what `spec.md`'s own words ask for beyond that: "se é a
mesma fila filtrada... **os textos precisam dizer isso**" and the acceptance
criterion, "a relação... está explícita." Before this audit, the only visible
sentence was `knowledge.proposals.lead` — "Changes an investigation proposed,
awaiting review." (`en.ts:864`, pre-edit) — which says what the items are and
that they are pending, but never says whether they are a separate, smaller
queue or the very same one a reader would find under "Proposed changes." A
first-time reader landing on this panel has no way to tell from the text
alone, only from behaviour they would have to go verify by clicking through.

Test-first: added
`'says in words that this is the same queue Proposed changes shows, not a
separate one'` (`knowledge.test.tsx:125-138`), asserting
`screen.getByText(/same queue as every other proposed change/)`. Run against
the unmodified tree: **failed** — `TestingLibraryElementError: Unable to find
an element with the text: /same queue as every other proposed change/`,
confirmed red. Fixed by extending the one catalogue sentence, in both locales
together so neither could drift from the other:

```
console/src/i18n/en.ts:864-865
- 'knowledge.proposals.lead': 'Changes an investigation proposed, awaiting review.',
+ 'knowledge.proposals.lead':
+   'Changes an investigation proposed, awaiting review in the same queue as every other proposed change.',

console/src/i18n/pt-BR.ts:762-763
- 'knowledge.proposals.lead':
-   'Mudanças que uma investigação propôs, à espera de revisão.',
+ 'knowledge.proposals.lead':
+   'Mudanças que uma investigação propôs, à espera de revisão na mesma fila de qualquer outra mudança proposta.',
```

No component change was needed — the sentence already renders from this one
key (`knowledge.tsx:184-186`). Because the sentence itself changed, the
pre-existing test's exact-string assertion
(`screen.getByText('Changes an investigation proposed, awaiting review.')`)
would no longer match; it is loosened to a prefix regex
(`knowledge.test.tsx:116-118`) rather than deleted, so it still pins that the
sentence begins the same way. After the catalogue edit, both the new test and
the adjusted existing one pass.

### 3. The dropped item: two different states behind one number

`spec.md`'s item 3 reads "Filtro 'Kind: Any' único; dois painéis de vazio
empilhados — Mesmos reparos da spec 023," importing 023 Memory's own
acceptance bar ("Nenhum filtro com única opção visível") for the filter half.
`controle.md` had no row for it at all — not `FEITO`, not `NÃO INICIADO` —
and its closing note ("3 testes novos, confirmados vermelhos") in fact counts
the three tests for items 1 and 2 in the pre-existing `knowledge.test.tsx`,
not anything for item 3.

**The two-panel half was already resolved, as a side effect of item 2's own
redesign, not by anything this item's own fix produced.** Because the
"Proposed by an agent" panel's `state` can never be anything but `'ready'`
(traced above), it can never render `EmptyState` — `Panel`
(`console/src/surfaces/panel.tsx:173-188`) only draws the empty branch when
`resolved === 'empty'`. The only panel on this screen that can ever be empty
is Documents, so "two stacked empty panels" cannot occur by construction, not
merely by the current data. I added one assertion to the existing
"a deployment still being set up" test rather than write a new one from
scratch — `knowledge.test.tsx:82-89` — filtering every `data-testid="panel"`
to `data-state="empty"` and asserting exactly one. Run against the *current*
tree with no implementation change: **passed immediately**. This is a
verification, not a red-then-green fix — nothing was broken, so nothing was
changed for this half, matching the instruction to say so plainly rather than
invent a fix for something that already holds.

**The filter half was live.** `console/src/surfaces/screens/knowledge.tsx`
(pre-edit) built the `FilterBar`'s `choices` inline, with no filtering:

```tsx
choices={[
  {
    name: 'kind',
    label: message(locale, 'knowledge.column.kind'),
    options: kinds.map((value) => ({ value, label: value })),
  },
]}
```

`memory.tsx:97-108` computes the equivalent array and appends
`.filter((choice) => choice.options.length > 0)` — knowledge.tsx never did.
`kinds` is `[]` whenever no document's `metadata.kind` is set — which is every
document in `fixtures/scenarios/empty/documents.json` and
`fixtures/scenarios/first-run/documents.json` (both `{"documents": []}`), and
also true whenever the corpus is genuinely empty on a finished deployment
(the `serveFinishedButEmpty` test helper). In every one of those cases the
screen rendered a "Kind" dropdown offering nothing but "Any" — precisely the
defect `spec.md` names, on the exact two scenarios this file's own tests
already exercise for other reasons, just never checked for this.

Test-first: added a `describe('a filter with nothing behind it but "Any"',
...)` block (`knowledge.test.tsx:141-174`) with three tests. Run against the
unmodified tree: **2 failed, 1 passed** — `'is hidden when no document in the
corpus has a kind'` and `'is hidden on a finished deployment that has ingested
nothing yet, too'` both failed (`expected true to be false`, the "kind"
filter was present when it should have been absent), confirmed red.
`'stays once the corpus has more than one kind to choose between'` **passed
trivially against the unmodified code** — the pre-fix implementation always
rendered the filter regardless of `kinds`, so an assertion that only checks
*presence* could not fail before the fix; it is a regression guard going
forward, not evidence the bug was pinned, and this report says so rather than
counting it as a third red test.

Fixed by mirroring `memory.tsx`'s exact pattern —
`console/src/surfaces/screens/knowledge.tsx:9` (`import { FilterBar, type
FilterChoice } from '../filters';`), `:86-96` (a local `choices` computed
once, filtered to non-empty options), `:116-122` (`<FilterBar ... choices=
{choices} />`, replacing the inline unfiltered array). After the fix, all
three tests in the block pass, and no other test in the file regressed.

### The Brazilian-Portuguese sweep: two leaks, on adjacent lines of the same block

Neither instance is on `controle.md`'s or the coordinator's list of remaining
known offenders (`surface.loading`, `dashboard.attention.empty.action`,
`approvals.empty.action`, `page.detectors.context`, "esta equipa"); both were
found by reading the whole `knowledge.*` block of `console/src/i18n/pt-BR.ts`
against the two patterns those confrontations established (pre-agreement
silent consonants, and dialect-specific nouns/verbs), because that block is
squarely inside the surface this spec reaches.

```
console/src/i18n/pt-BR.ts:755
- 'knowledge.column.updated': 'Actualizado',
+ 'knowledge.column.updated': 'Atualizado',
```

The column header, rendered whenever the Documents table has rows
(`knowledge.tsx:158`). Pre-agreement silent consonant, the same class as
`Objectivo`→`Objetivo` and `Activar`→`Ativar` fixed in 022 Detectors'
confrontation.

```
console/src/i18n/pt-BR.ts:758-759 (knowledge.documents.empty.body)
- '...este console não tem nenhum controlo de upload...'
+ '...este console não tem nenhum controle de upload...'
```

This one sits one line below the filter that had already been read for the
first fix, in the same catalogue value — the exact shape of "one line short"
this audit was told to watch for. "Controlo" as a *noun* ("um controlo") is
European Portuguese; Brazilian Portuguese uses "controle" for the same noun —
the same split "controlo remoto" vs. "controle remoto" makes visible for
"remote control." Reachable whenever the Documents panel's empty state
renders its own words (setup complete, corpus still empty).

No test in this repository asserts pt-BR wording for this screen — like every
prior confrontation in this series found, `resolveLocale` defaults every test
to English and nothing here requests `pt-BR`. **Neither dialect correction had
a failing test to show red first**, and this report says that plainly rather
than inventing one; both are content-only corrections to catalogue entries
that were already complete and already passing the fallback and completeness
tests (`tests/unit/i18n/catalogue.test.ts`).

**Traced and deliberately left alone**, named rather than silently dropped or
silently expanded into: `surface.loading` (`pt-BR.ts:364`, "A carregar
{panel}…") renders inside every panel on this screen while it loads, through
`panelLabels` — but it is generic chrome shared by 52 call sites across the
whole console, not owned by Knowledge, matching exactly how 023 Memory's
confrontation left it. `knowledge.search` (`en.ts:854`, `pt-BR.ts:756`) is
declared in both catalogues and referenced nowhere in `console/src` or
`console/tests` — the same "unreachable, not a defect" shape 023 Memory found
for `memory.search` and its siblings. `knowledge.proposals.empty.heading`,
`.empty.body`, and `.empty.action` (`en.ts:865-868`, `pt-BR.ts:764-767`) are
computed and passed to the "Proposed by an agent" `Panel`'s `empty` prop, but
— as shown above — that panel's state can never resolve to `'empty'`, so
these three keys are provably unreachable, the same shape 022 Detectors found
for `detectors.empty.body`/`.action`: declared because the type requires an
object, never rendered. Not a defect; not touched. `tree.tsx`, offered as a
likely starting point, was checked via its own blast radius and is not
imported by, and has no caller chain into, `knowledge.tsx` — its actual
callers are `catalogue.tsx`, `topology.tsx`, `team-context.tsx`,
`autonomy.tsx`, `agent.tsx`, `configuration.tsx`, and `approvals.tsx`. No
change was made there because nothing there is reached by this spec's
surface.

## Verification

Console, from `console/`:

- `pnpm exec vitest run tests/unit/surfaces/knowledge.test.tsx` — run
  **before** any change: **3 passed (3)**, confirming `controle.md`'s
  structural claims for items 1 and 2 rather than assuming them. After adding
  the new tests and the loosened assertion, **before** implementing any fix:
  **3 failed | 4 passed (7)** — confirmed red for the explicit-relationship
  sentence and both filter-hiding cases; the fourth new test passed trivially
  against the unmodified code, as stated above. After the fix: **7 passed
  (7)**.
- `pnpm exec vitest run tests/unit/surfaces tests/unit/i18n` — **71 files
  passed, 966 tests passed.**
- `pnpm exec vitest run` (full unit suite) — **120 files passed, 1943 tests
  passed** (1939 before this session, +4 new tests here: the relationship
  sentence, two filter-hidden cases, and the filter-stays regression guard;
  the fifth new assertion, the empty-panel count, was added inside an
  existing test rather than as a new one). One benign jsdom console line
  ("Not implemented: navigation to another Document") is the same
  pre-existing test-environment noise every prior confrontation in this
  series recorded, not a failure.
- `pnpm exec tsc --noEmit` — clean, exit 0.
- `pnpm exec eslint src/surfaces/screens/knowledge.tsx src/i18n/en.ts
  src/i18n/pt-BR.ts tests/unit/surfaces/knowledge.test.tsx` — clean,
  including `no-untranslated-strings` and `no-design-literals`.
- `pnpm exec prettier --check` on the same four files — the test file needed
  `--write` once (the new blocks were not yet reformatted); after that,
  "All matched files use Prettier code style!" on all four.
- `make console-visual` — **35 passed (35)**, including
  `knowledge-1440-light`. This spec changed what the screen renders (the
  filter's presence and the proposals panel's sentence), so the gate was run
  rather than skipped, per the current instruction that it is no longer
  known-red. No baseline differed and none was touched.

Not run: `make console-e2e` (this confrontation changed panel text and a
filter's presence, not a route, a navigation, or anything the e2e suite's
existing Knowledge assertions check — both `shell.spec.ts` and
`budgets.spec.ts`'s Knowledge references test navigation and area identity
only, confirmed by reading them, and neither would exercise the changed
text). `make test-postgres` — no `platform/persistence/` file was touched.

Python: no Python file was changed, so no Python gate was run. The backend
was read, not edited, to verify `controle.md`'s claim about the ingestion
paths: `gateway/http/routes/knowledge.py` (both routes, confirmed `GET`-only),
`gateway/http/scheduled_work.py` (confirmed `KnowledgeSync` has no HTTP
route), and `capabilities/tools/system/knowledge_propose/tool.py` (confirmed
`propose_knowledge` queues into the one proposal store and never writes the
corpus directly). A repository-wide search for a `POST`/`PUT`/`PATCH`/`DELETE`
route naming knowledge, sync, ingest, or document, across every file in
`gateway/http/routes/`, found none. Nothing here needed a fix, so nothing here
was changed.

**On confirming new tests red first.** Item 2's new test failed against the
unmodified tree with `Unable to find an element`, confirmed red before the
catalogue edit. Item 3's filter fix had two of its three new tests fail
(`expected true to be false`) against the unmodified tree, confirmed red
before the code edit; its third new test passed trivially before the fix
existed, and this report says so rather than presenting it as a pin. Item 3's
panel-count assertion and item 1 needed no red state: both were already true
of the unmodified tree, verified by running the assertion against it and
watching it pass immediately, which is what stands in for red-before-green
when nothing was broken — the same convention 021 Topology's and 023 Memory's
confrontations used.

## Control reconciliation

`specs_v4/024-knowledge/controle.md` is rewritten with three rows instead of
two, one per `spec.md` problem, so item 3 is no longer silently absent. Items
1 and 2 keep their `FEITO` verdict but the detail column is corrected: item 1
now cites the routes and paths actually verified rather than repeating the
prior wave's prose unchanged, and item 2 records that the structural half was
already right while the textual half — the acceptance criterion's own
"está explícita" — was not, until this confrontation's catalogue fix. Item 3
is added as a new row, split into the two independent halves it actually
contains, both now `FEITO`: the two-panel half was already resolved as a side
effect of item 2's earlier redesign (no change), and the filter half was
genuinely broken and is now fixed. A closing note records the two
Brazilian-Portuguese corrections made in this pass and the four
out-of-scope/unreachable observations traced but deliberately left (
`surface.loading`, `knowledge.search`, the three unreachable
`knowledge.proposals.empty.*` keys, and `tree.tsx`'s irrelevance to this
screen), so none of them is rediscovered from nothing next time this screen is
touched.
