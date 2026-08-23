# 023 Memory — implementation confrontation

Date: 2026-08-13

## Conclusion

Unlike 020 Resources (control stale in both directions) and 022 Detectors
(control stale, one item needing real work), this confrontation lands where
021 Topology did: `controle.md`'s claim that all three of `spec.md`'s problems
— plus the accessibility CTA duplication it tracks as a fourth row — were
already fixed in "onda 3" is accurate. Reading
`console/src/surfaces/screens/memory.tsx` line by line against each problem
and each acceptance criterion, then running the nine tests `controle.md`
counts, proved every claim rather than repeating it: all nine passed against
the tree exactly as it stood before this confrontation touched anything, and
the full console suite (1939 tests, 120 files) was green alongside a clean
`tsc`, `eslint`, and `prettier`. Nothing in `spec.md`'s three numbered
problems or two acceptance criteria was left undone, and nothing was
regressed.

What the control did not track, because nothing in `spec.md` asks for it in
words a control file would quote, is dialect. This confrontation's own brief
asked specifically for a Brazilian-Portuguese sweep of the screens this spec
reaches, and that sweep found two genuine European-Portuguese leaks reachable
from the Memory screen: `memory.episodes.empty.action` read "Ver o que está a
correr" — the periphrastic "a + infinitive" construction European Portuguese
uses for a progressive, where the very same English source string
("See what is running"), translated for the identical purpose on the
Proposals screen three hundred lines later in the same file, already reads
"Ver o que está em execução". And `empty.cause.setup` — the shared sentence
that closes the exact causal chain problem 1 asks this screen to close, and
which eight screens including this one call through `setupCause` — read
"este deployment continua a ser configurado", the same European construction
applied to "continuar". Both are fixed here, in `console/src/i18n/pt-BR.ts`
only. Both are pure content corrections to catalogue entries that were
already passing every existing test — the completeness test only checks that
a key exists, not that its Portuguese is Brazilian, and no test anywhere
asserts the specific wording that changed — so there is no failing test to
show red before green for either one, and this report says that plainly
rather than inventing one.

Two related instances were traced and deliberately left alone. `empty.cause.watching`
carries the identical defect ("nada está a ser observado") but is never
reached from the Memory screen — only `incidents.tsx` and `detectors.tsx`
call `watchingCause` — so fixing it belongs to whichever confrontation next
touches one of those two screens, not to this one. And `surface.loading`
("A carregar {panel}…", used by every one of this console's screens through
`panelLabels`) does render inside Memory's own panels while they load, but it
is generic loading chrome with zero connection to what `spec.md` asks this
spec to fix, shared identically by every panel in the whole console rather
than owned by Memory's own vocabulary — correcting it is a console-wide sweep
that belongs to whichever surface owns the shared vocabulary this file's own
`give the console one vocabulary` commit established, not to a Memory
empty-state polish pass. Both are named in full below rather than silently
dropped or silently expanded into.

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. O vazio não fecha a cadeia causal | FEITO (onda 3) | Confirmed accurate. `memory.tsx:113-133` computes `cause = setupCause(locale, setup)` and hand-composes `cycleBody` from the two mechanism sentences plus, when a cause applies, `cause.body` — never `emptyBecause`, which would replace rather than append, exactly as `controle.md` describes. Covered by two tests in `memory.test.tsx`, both passing. Two Brazilian-Portuguese corrections made to the shared sentence this item closes with (see below); the mechanism and the causal chain itself were already correct. | DONE (dialect corrected, no structural change) |
| 2. Filtros vazios e contador órfão | FEITO (onda 3) | Confirmed accurate. `memory.tsx:97-108` filters both filter choices to `options.length > 0`; no `/v1/memory/stats` read and no "Episodes: N" text remain anywhere in the screen. Covered by three tests, all passing. | DONE (no change) |
| 3. Dois painéis empilhados de vazio | FEITO (onda 3) | Confirmed accurate. `memory.tsx:149-217` renders exactly one `Panel` when `corpusEmpty`, computed from the unfiltered record count (`memory.tsx:112`), and two panels — Episodes and Strategies, the latter permanently explaining the mechanism since no endpoint yet serves synthesised strategies — otherwise. Covered by three tests, all passing. | DONE (no change) |
| 4. (CTA duplicado na acessibilidade) | FEITO (onda 3, no `Panel`) | Confirmed accurate, and confirmed shared rather than local. `console/src/components/state.tsx`'s `EmptyStateAction` (`:32-34`) is a union — an action has either an `href` or an `onSelect`, never both — so `EmptyState` (`:65-97`) renders exactly one control, a single anchor carrying `data-testid="way-back"`, never a button beside a hidden twin. The fix lives in the shared primitive every panel's empty state uses, not in Memory. | DONE (no change) |

## Evidence and corrections

### 1. The causal chain, and the two dialect corrections inside it

`console/src/surfaces/screens/memory.tsx:110-133`:

```ts
const corpusEmpty = episodes.status === 'ready' && records.length === 0;
const cause = setupCause(locale, setup);

const cycleBody = [
  message(locale, 'memory.episodes.empty.body'),
  message(locale, 'memory.strategies.empty.body'),
  ...(cause === null ? [] : [cause.body]),
].join(' ');

const cycleEmpty: PanelEmpty = {
  heading: message(locale, 'memory.episodes.empty.heading'),
  body: cycleBody,
  actionLabel:
    cause === null
      ? message(locale, 'memory.episodes.empty.action')
      : cause.actionLabel,
  href: cause === null ? '/runs' : cause.href,
};
```

This is exactly the shape `controle.md` describes: the two mechanism
sentences ("An episode is written when an investigation ends… A strategy is
synthesised once enough episodes agree…") stay, and when `setupCause` finds
outstanding setup steps, one more sentence and a redirected action close the
chain — not `emptyBecause`, which would have discarded the mechanism
sentences rather than appending to them. `setupCause` itself
(`console/src/surfaces/emptiness.ts:45-53`) returns `null` once
`outstanding(setup) === 0`, so a deployment whose setup is finished but whose
corpus is still empty keeps its own words and points at `/runs` instead of
`/first-run` — the second branch `controle.md`'s row 1 describes ("Com o
setup fechado e o corpus vazio, a acção volta a 'ver o que está a correr'").

Two tests in `console/tests/unit/surfaces/memory.test.tsx:88-146` pin both
halves and were run, not just read, against the unmodified tree before this
confrontation changed anything: `'names the unfinished setup as the reason,
with a link that finishes it'` (`:89-110`) asserts both mechanism sentences
stay, that "this deployment is still being set up" and "7 step(s) are
outstanding" appear, and that the one `way-back` link points at
`/first-run`; `'points at what is running instead of at the setup'`
(`:136-146`) asserts the reverse — no "still being set up" text, and the link
points at `/runs` — once the setup checklist is served complete. Both passed
before this confrontation touched anything (`pnpm exec vitest run
tests/unit/surfaces/memory.test.tsx` — 9 passed, run first, before any edit).

**The dialect corrections.** `controle.md`'s own description of the
setup-complete fallback (quoted above) names the action label verbatim as
"ver o que está a correr" — and that is genuinely what
`console/src/i18n/pt-BR.ts:739` said before this confrontation:
`'memory.episodes.empty.action': 'Ver o que está a correr'`. "Está a correr"
is the European Portuguese periphrastic progressive ("estar a" + infinitive);
Brazilian Portuguese uses the gerund or, as this same catalogue already does
for the identical English source string ("See what is running") on the
Proposals screen, a different phrasing entirely —
`'proposals.empty.action': 'Ver o que está em execução'`
(`console/src/i18n/pt-BR.ts:1258`, unchanged). Corrected to match:

```
console/src/i18n/pt-BR.ts:739
- 'memory.episodes.empty.action': 'Ver o que está a correr',
+ 'memory.episodes.empty.action': 'Ver o que está em execução',
```

The second correction is in the shared sentence this item is *about*.
`empty.cause.setup` (`console/src/i18n/pt-BR.ts:520-521`) is what
`cause.body` reads when `setupCause` finds outstanding steps — the exact
sentence problem 1 asks this screen to add, and it is shared by every one of
the eight screens that call `setupCause`
(`memory.tsx:113`, `topology.tsx:104`, `knowledge.tsx:73`, `data.tsx:78`,
`approvals.tsx:174`, `proposals.tsx:94`, `incidents.tsx:144`,
`detectors.tsx:100`, confirmed by grep against the current tree). It read
"este deployment continua a ser configurado" — the same European "a +
infinitive" construction, this time on "continuar". The same catalogue
already uses the Brazilian gerund for this exact shape of sentence elsewhere
— `'schedules.create.submitting': 'Criando…'`,
`'detectors.control.enabling': 'Ativando…'`, and, closest in construction,
`'agent.role.default.body': '…continua rodando no padrão do deployment.'`
(`pt-BR.ts:1149`) and `'live.takeover.assist.body': 'A investigação continua
rodando…'` (`:1140`) — both already correctly using "continua" plus the
gerund rather than "continua a" plus the infinitive. Corrected to match:

```
console/src/i18n/pt-BR.ts:520-521
  'empty.cause.setup':
-   'Ainda não aconteceu nada aqui porque este deployment continua a ser configurado — faltam {count} passo(s), e não há investigações enquanto isso.',
+   'Ainda não aconteceu nada aqui porque este deployment continua sendo configurado — faltam {count} passo(s), e não há investigações enquanto isso.',
```

Judged in scope rather than named-and-left, unlike the two related instances
below, for three reasons together: the sentence is directly reached by
Memory's own empty state, in the exact state (`spec.md`'s problem 1) this
confrontation was sent to close; it is a single catalogue entry, so fixing it
carries no risk of leaving two screens saying the same thing two different,
now-disagreeing ways — every one of the eight callers reads the same
corrected string; and no test anywhere in the repository asserts the old
wording (checked with a repository-wide search for the literal text before
changing it), so nothing that currently passes was put at risk. This also
repairs the identical sentence on `topology.tsx` and `detectors.tsx`, both
already confronted and accepted (021, 022) on acceptance criteria stated
entirely in English semantics — neither reopens anything either report
verified.

Every test in `memory.test.tsx` and the repository's i18n completeness suite
(`tests/unit/i18n/catalogue.test.ts`) was re-run after both edits: still 9
and 33 passing respectively, because `resolveLocale` defaults every test in
this suite to English (`console/src/i18n/messages.ts:110-138`,
`DEFAULT_LOCALE = 'en'`) and no test in this repository sets an
`Accept-Language` header requesting `pt-BR` for this screen or for
`setupCause`'s seven other callers. **Neither correction had a failing test
to show red first**, and this report says so in those words rather than
inferring one: both are content-only corrections to catalogue entries that
were already complete (present, non-empty, passing the fallback and
completeness tests) before the edit — the defect was in the Portuguese
itself, which no automated check in this console reads for dialect.

**Traced and deliberately left alone**, named rather than silently dropped:

- `empty.cause.watching` (`console/src/i18n/pt-BR.ts:523-524`, "nada está a
  ser observado") carries the identical European construction, but
  `watchingCause` is called only by `incidents.tsx:143` and
  `detectors.tsx:98` — never by Memory. Fixing it belongs to whichever
  confrontation next reaches one of those two screens.
- `surface.loading` (`console/src/i18n/pt-BR.ts:364`, "A carregar
  {panel}…") does render inside Memory's own panels while `episodes` or
  `setup` is in flight, through `panelLabels`
  (`console/src/surfaces/labels.ts:25-32`) — but it is one string shared by
  every panel on every one of this console's screens (52 call sites for
  `panelLabels`, confirmed by `codegraph_explore`'s blast-radius listing),
  generic "please wait" chrome with no connection to anything `spec.md` asks
  this confrontation to fix. Correcting it is a console-wide sweep that
  belongs to whichever surface owns the shared vocabulary layer this
  repository's own history names explicitly (commit `a53a009`, "give the
  console one vocabulary") — not to a Memory-specific empty-state polish
  pass. Left alone.
- Two siblings of the exact instance fixed on this screen, found while
  reading the surrounding lines for the correct replacement and named rather
  than quietly repaired in passing: `dashboard.attention.empty.action`
  (`console/src/i18n/pt-BR.ts:416`) and `approvals.empty.action`
  (`:568`) both still read "Ver o que está a correr" for the same English
  source string Memory and Proposals share. Neither renders on the Memory
  screen; both belong to Dashboard's and Approvals' own confrontations.
- `page.detectors.context`'s Portuguese ("O que está a ser observado…",
  `pt-BR.ts:223-224`) carries the same passive-progressive Europeanism.
  Detectors' own subtitle, not reachable from Memory, and outside what 022
  Detectors already closed on its own acceptance criteria. Named, not
  touched.

A full console-wide dialect sweep was not attempted, and the four instances
above are what surfaced while tracing this screen's own dependencies —
not the result of grepping the whole catalogue for every European
construction, which would be a materially larger undertaking than a Memory
confrontation and is not what was asked.

### 2. Filtros vazios e contador órfão

`console/src/surfaces/screens/memory.tsx:65-71,97-108`:

```ts
const components = [
  ...new Set(records.flatMap((record) => list(record, 'components').map(String))),
].sort();
const outcomes = [
  ...new Set(records.map((record) => text(record, 'outcome'))),
].sort();
...
const choices: readonly FilterChoice[] = [
  { name: 'component', label: message(locale, 'memory.filter.component'), options: components.map(...) },
  { name: 'outcome', label: message(locale, 'memory.filter.outcome'), options: outcomes.map(...) },
].filter((choice) => choice.options.length > 0);
```

Both filters are computed from the whole corpus (`records`, not `filtered`),
so choosing one value never makes the other's real options vanish, and each
is dropped from `choices` — and therefore never rendered by `FilterBar`
(`memory.tsx:139-147`) — once it has nothing behind it but the "Any" the
`Select` itself prepends (`console/src/surfaces/filters.tsx:58`). No
`memory.stats.episodes` read, no `/v1/memory/stats` fetch, and no "Episodes:
N" text remain anywhere in `memory.tsx` — confirmed by reading the whole file
and by a repository-wide search for `/v1/memory/stats` in `console/src`,
which finds it only in the generated `src/api/schema.ts` (the route still
exists on the gateway; nothing in the console calls it any more).

Three tests were run, unmodified, against the current tree:
`memory.test.tsx:127-132` and `:161-166` (both scenarios) assert
`screen.queryByText(/Episodes:\s*\d/)` is `null`;
`:180-213` (`'is hidden, while a filter with real choices stays'`) serves two
episodes with no recorded components and two distinct outcomes, and asserts
the `component` filter is absent from `getAllByTestId('filter')` while
`outcome` remains — the exact "single option hidden, real choice kept"
distinction the acceptance criterion asks for. All three passed before this
confrontation changed anything.

**Traced, non-actionable, named for completeness rather than silently
carried forward:** `memory.search`, `memory.stats.episodes`,
`memory.strategies.lead`, `memory.strategies.supporting`,
`memory.strategies.antipatterns`, and `memory.strategies.edit` are all still
declared in both catalogues (`en.ts` and `pt-BR.ts`) but referenced nowhere
in `console/src` or `console/tests` — confirmed by counting non-catalogue
references per key. These read as the remnants of the "Episodes: N" counter
and a fuller strategy-detail view this file's own comment says does not
exist yet ("No endpoint serves synthesised strategies yet"). The same shape
of observation 022 Detectors made about `detectors.empty.body` and
`detectors.empty.action`: unreachable, not a defect against any acceptance
criterion, and not a change this confrontation needs to make.

### 3. Dois painéis empilhados de vazio

`console/src/surfaces/screens/memory.tsx:149-217` branches once, on
`corpusEmpty`: a single `Panel` titled `memory.stats.title` with `cycleEmpty`
as its empty state, or a `flex flex-col` holding the Episodes panel (a real
table when `rows.length > 0`, its own default empty state otherwise — the
mechanism sentence alone, not the causal-chain composite, because
`corpusEmpty` is false whenever any record exists even if the current filter
matches none) and the Strategies panel, whose `state` is hard-coded to
`stateOf(episodes, true)` — always empty, by design, because nothing serves
synthesised strategies yet, and its body explains what a strategy is rather
than leaving the panel to imply the corpus holds none.

`corpusEmpty` itself (`memory.tsx:112`) is computed over `records.length`,
the whole read, not `filtered.length` — exactly the distinction
`controle.md`'s own closing note describes: "a condição de 'verdadeiramente
vazio' é o número de registos sem filtro… atribuir uma escolha de filtro a
um setup partido seria mentir." Landing on `?outcome=resolved` with nothing
matching renders the ordinary per-panel empty state, not the collapsed
one-panel causal-chain narrative.

Three tests, run and passing against the unmodified tree:
`memory.test.tsx:112-118` (`'collapses to a single section, not two panels of
the same sentence'`) asserts exactly one `panel` test id and no `row-list`;
`:150-159` (`'keeps episodes and strategies as two panels'`) asserts two
panels, both titles, and five rows once `populated` is served;
`:168-177` (`'still explains what a strategy is, in its own words, with no
episode data'`) asserts the Strategies panel's mechanism sentence is present
even while Episodes holds real rows.

### 4. CTA duplicado na acessibilidade

Confirmed the fix `controle.md` attributes to the shared `Panel`/`EmptyState`
pair, not local to Memory. `console/src/components/state.tsx:32-34`'s
`EmptyStateAction` type is a discriminated union — `{ href } | { onSelect }`,
never both — so `EmptyState` (`:44-97`) has exactly one branch that can
render for any given action, and the branch that matches a navigation
(`href !== undefined`) renders one `<a>` carrying `data-testid="way-back"`
(`:85-93`), not a button with a visually-hidden anchor beside it. The
in-repository comment at `console/src/surfaces/panel.tsx:174-181` states the
history directly: "a defect three specs reported independently, from three
screens, none of which could fix it from where they stood" — consistent with
`controle.md`'s note that the root cause was shared and fixed once, in the
component every panel's empty state renders through, rather than patched
per screen. No change made here; the fix already covers Memory because
Memory's `Panel` calls are ordinary calls into the same shared component.

## Verification

Console, from `console/`:

- `pnpm exec vitest run tests/unit/surfaces/memory.test.tsx` — run **before**
  any edit: **9 passed (9)**, confirming `controle.md`'s claim rather than
  assuming it. Run again after both dialect corrections: still **9 passed
  (9)** — the corrected text is not asserted by any test in this file, which
  is exactly why there was no red to show for either correction.
- `pnpm exec vitest run tests/unit/surfaces/memory.test.tsx tests/unit/i18n`
  — after both corrections: **3 files passed, 33 tests passed.**
- `pnpm exec vitest run` (full unit suite) — **120 files passed, 1939 tests
  passed**, matching the count 022 Detectors' confrontation left the tree at.
  One benign jsdom console line ("Not implemented: navigation to another
  Document") is the same pre-existing test-environment noise every prior
  confrontation in this series recorded, not a failure. This full run is
  what stands in for a regression check on the shared `empty.cause.setup`
  string's seven other callers (topology, knowledge, data, approvals,
  proposals, incidents, detectors): nothing broke.
- `pnpm exec tsc --noEmit` — clean, no output.
- `pnpm exec eslint src/i18n/pt-BR.ts src/i18n/en.ts
  src/surfaces/screens/memory.tsx tests/unit/surfaces/memory.test.tsx` —
  clean, including `no-untranslated-strings` and `no-design-literals`.
- `pnpm exec prettier --check` on the same four files — "All matched files
  use Prettier code style!"

Not run: `make console-e2e` and `make console-visual` — the same exclusion
every confrontation in this series has recorded (no toolchain/browser in
this environment), and the visual gate is additionally known-red at HEAD for
reasons unrelated to any spec in this series (baselines drifted in an
earlier commit; confirmed by the orchestrator against the unmodified tree
before this confrontation began). Python gates were not run: nothing under
`platform/`, `gateway/`, or any other Python package was touched or
implicated — `gateway/http/routes/memory.py` and
`platform/persistence/ports/episode_store.py` were read as the task's
"likely starting points" and traced (`EpisodeStore` protocol,
`PostgresEpisodeStore`, `FakeEpisodeStore`, the `/v1/memory/search` and
`/v1/memory/stats` routes) to check for a cross-tier defect of the shape 020
Resources found in `signal_map.py`; none was found. `outcome`, `components`,
and `title` all flow from the same `Episode` dataclass through the same view
model the console reads verbatim, and nothing in `spec.md`'s three problems
or two acceptance criteria points at the backend.

**On confirming new tests red first.** No new test was written. The two
dialect corrections have no failing test to show red-then-green — both are
content-only fixes to catalogue entries that were already complete and
already passing every test that touches them (the fallback test at
`catalogue.test.ts:49-56`, the completeness test at `:34-42`), and no test in
this repository asserts the specific Portuguese wording that changed, so
there was nothing to turn red before making the correction. Items 1 through
4's own structural behaviour needed no new test either: the nine tests
`controle.md` already counts were *run*, not read, against the tree exactly
as this confrontation found it, and all nine passed before anything was
edited — which is what stands in for red-before-green here, per the same
convention 021 Topology's confrontation used when it found nothing to fix.

## Control reconciliation

`specs_v4/023-memory/controle.md` is updated so all four rows point at this
report and record that the confrontation re-ran the nine tests and
re-verified the structure rather than re-asserting the prior claim. The
verdicts themselves are unchanged — all four were already correct — and a
new note records the two Brazilian-Portuguese corrections made during this
confrontation (`memory.episodes.empty.action` and the shared
`empty.cause.setup`, both in `console/src/i18n/pt-BR.ts` only), plus the four
related, out-of-scope European-Portuguese instances traced and left for the
screens and surfaces that own them (`empty.cause.watching`, `surface.loading`,
`dashboard.attention.empty.action`, `approvals.empty.action`,
`page.detectors.context`), so none of them is rediscovered from nothing next
time one of those screens is confronted.
