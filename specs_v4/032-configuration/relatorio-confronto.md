# 032 Configuration — implementation confrontation

Date: 2026-08-14.

## Conclusion

`controle.md` was accurate for six of `spec.md`'s seven numbered problems, and
independent verification — running the tests it cited rather than trusting
that they existed, and reading the code they claimed to fix — confirmed all
six rather than merely repeating the prior wave's prose. Item 1 (docstrings
leaking `FR-\d+`/`Article [IVX]+`/source paths/reST into the UI) is closed by
`platform/config_service/schema/types.py`'s `field_help`/`section_help` pair,
and its own regression test — parametrised over four leak patterns, walked
across every declared field *and* every list-entry field — was run
independently and passed clean (340 tests, `tests/unit/platform/config_service/`).
Item 2 (sections collapsed by default, a table of contents, a field search,
and a sticky preview/save bar) holds structurally and is proven in a real
browser: `surfaces.spec.ts`'s `'the configuration preview is the deployment's
answer'` reaches a specific field by typing its path into the search box,
never by scrolling, and was re-run to a real pass in this session rather than
assumed from the report that describes it. Item 4 (the "Set at default"
ambiguity) and item 5 (the effective-configuration disclosure and the
`UNKNOWN` badge) both hold, independently confirmed by reading the code and by
running the unit tests that pin the sharpest edge case each names — a node
literally named `default` holding a real override. Item 7 (this screen
competing with dedicated screens) is genuinely untouched, and `spec.md` itself
defers it to spec 090; no misrepresentation there either.

Item 6 was mostly right and one line short in the same way this series has
found before: the named complaint — an integration's card titled by its
evaluation slug rather than its own name — is correctly fixed, but its exact
sibling, in the same conditional, in the same function, was not. A boolean
toggle inside a list entry that has *no name yet* — the state of every entry
immediately after "Add another," before anyone has typed into it — still
named nothing when read in isolation, reproducing the literal defect the
problem statement quotes ("toggles 'Enabled' sem objeto quando lidos
isolados") for exactly the one case its own fix left uncovered. Closed here,
test-first, confirmed red first.

Item 3 is the one place this confrontation disagrees with `controle.md`'s
verdict, and the disagreement is narrow and specific rather than a rejection
of the work already done. The field editor's own row — the ~80-field,
highest-volume instance the problem statement names — genuinely shows the
effective default now ("Using the deployment default: 5"), tested, and that
part of the fix is correct and unchanged here. What the control recorded as a
sustained refusal — the preview diff's own "Now" column staying blank for a
field that was never set at this node, which is the *other* half of the same
numbered problem, quoted verbatim in `spec.md` — deserved a second look
because the reason given for the refusal ("fabricá-lo seria a merge do lado
do cliente que o AGENTS.md proíbe") is a true statement about the *console*
and an incomplete one about the *system*: the value in question is something
the *server* already computes elsewhere, so a server-side fix would not be
the client-side merge the console's `AGENTS.md` forbids. I traced the actual
computation into `platform/config_service/preview.py`, worked out precisely
what a correct fix would need to do, and then found that doing it would
change a **deliberately tested, pre-existing invariant** of that module —
`test_clearing_a_field_nothing_inherits_reverts_to_no_value_at_all`, added in
commit `827ec0b`, 171 commits before this spec's own UI commit `c512fae`, and
untouched since. That is not a gap this confrontation's surface owns; it is a
foundational design decision of a backend package this spec does not control,
and overturning it here — however locally justifiable it looks from this one
screen — is exactly the kind of change that belongs to whoever owns
`config_service`'s own contract, not to a screen-focused confrontation. I
built nothing there, and I am naming the reasoning in full below rather than
either quietly accepting the control's account or quietly overriding it.

A Brazilian-Portuguese sweep of this screen's own catalogue block (only —
`teamContext.*`, which sits in the same file and shares several of the same
words, is a different screen and is named, not touched) found seven genuine
European-Portuguese spellings and constructions, none previously reported:
two silent-consonant leaks (`efectiva`/`efectivos`), one noun that is a false
friend across the two dialects (`controlo`, the same class 024 Knowledge's
confrontation already fixed once elsewhere), one progressive-tense
construction that is specifically European (`A guardar…`, the exact
grammatical shape `surface.loading`'s already-known `A carregar…` is), one
vocabulary item that means something different in Brazilian Portuguese
(`sítio`, "place" in Europe and "small rural property" in Brazil — the same
shape as the already-known `equipa`), one more silent-consonant leak
(`contactar`), and one internal inconsistency where this exact screen's own
catalogue used both spellings of the same word (`secção` beside an already-
correct `seção`, six lines apart). All seven are fixed below.

## Table

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Docstrings leak `FR-\d+`/`Article`/paths/reST | FEITO (lote 6) | Confirmed accurate. `field_help`/`section_help` (`types.py:70-104`) declare a short, operator-facing text beside every field and section; `EditableField` (`preview.tsx:70-125`) has no `description`/`section_summary` at all, so a leak through this screen is structurally impossible, not merely absent today. The regression test (`test_fields.py:122-163`) was run, not assumed: 340 passed. | DONE (no change) |
| 2. Everything expanded, save far away | FEITO com desvio (lote 6) | Confirmed accurate, deviation included. Sections start closed and remember state per browser via `useSyncExternalStore` with a correct SSR snapshot (`preview.tsx:341-414`); a sticky top bar carries search and a table of contents (`:617-650`); a sticky bottom bar carries preview/save once anything is pending (`:697-744`). The acceptance criterion names "sumário ou busca," not a side rail, so the documented deviation (top bar, not a side column) does not fall short of it. `surfaces.spec.ts:82-116` was re-run and reaches a field by search, in a real browser: passed. | DONE (no change) |
| 3. Undefined field hides the effective default | FEITO (lote 6) | PARTIAL. The field row (`preview.tsx:769-779`, `:816-823`) genuinely shows "Using the deployment default: N" for the ~80-field high-volume case; tested (`config-editor.test.tsx:361-374`). The preview diff's own "Now" column — the *other* half of this same numbered problem, quoted verbatim in `spec.md` — still reports blank for such a field, traced to `platform/config_service/preview.py:139-164`, and a fix was investigated in full rather than assumed impossible: it would change a deliberately tested, pre-existing invariant of that module (`test_preview_redundancy.py:176-183`, commit `827ec0b`, 171 commits before this spec's own UI work). | PARTIAL — the field-row half stands, confirmed; the diff-cell half is investigated, named, and correctly left to whichever surface owns `config_service/preview.py`'s own contract |
| 4. "Set at default" is ambiguous | FEITO (lote 6) | Confirmed accurate, in both of the screen's two independent provenance vocabularies. `provenanceLabel` (`configuration.tsx:94-118`) never lets "no override" and "an override, recorded at a node named default" share a word; `FieldRow`'s own text (`preview.tsx:816-823`) makes the identical distinction independently. Both are tested against a node literally named `default` (`configuration.test.ts:17-31`, `config-editor.test.tsx:376-383`), run and passing. | DONE (no change) |
| 5. Effective config: cryptic collapse, `UNKNOWN` badge | FEITO (lote 6) | Confirmed accurate. `ConfigValue`/`prettyNested` (`configuration.tsx:41-73`) give a nested value a working `<details>` disclosure where none existed before. A repository search of every file this screen reaches found no `'unknown'`/`UNKNOWN` fallback anywhere in the chain; `provenanceLabel`'s "mixed" case (`configuration.tsx:114-116`) replaces it for the one case that needs a word. | DONE (no change) |
| 6. Generated labels ("EVALUATED 1/2", isolated toggle) | FEITO (lote 6) | PARTIAL. The named complaint — a card titled by its evaluation slug — is fixed: `entryTitle` (`preview.tsx:424-429`) reads only the entry's own `name` field, and "Evaluated N" is repurposed as an honest, distinct position label, tested (`config-editor.test.tsx:482-486`, `object-list.test.tsx:224-231`). Its exact sibling in the same conditional — a boolean toggle inside an entry with no name typed yet still names nothing in isolation — was untested and still reproduced. | DONE (residual fixed here, test-first) |
| 7. Competes with dedicated screens | NÃO INICIADO (estrutural) | Confirmed accurate. Nothing in `configuration.tsx`/`preview.tsx` links to or from Autonomy, Team context, Data, Detectors, or Administration; `spec.md` itself names spec 090 as the owner of this item. | NOT STARTED (unchanged, correctly deferred) |

## Evidence and corrections

### 1. Docstrings leaking FR/Article/paths/reST — confirmed done, run independently

`platform/config_service/schema/types.py:70-104` declares `field_help(text,
**constraints)` and `section_help(text)`, both carrying their short text
through `json_schema_extra={"help": ...}` — the same channel that already
carries type, range and default to the catalogue (`fields.py:246-264`), so a
field cannot have one without the other. `platform/config_service/fields.py`'s
`ConfigField` (`:61-105`) keeps `help`/`section_help` as fields distinct from
`description`/`section_summary`, and `gateway/http/routes/config.py`'s
`ConfigFieldView`/`ItemFieldView` (`:210-273`) serialise both pairs, but
`console/src/surfaces/editable.ts:86-112`'s `editableFields()` only ever reads
`help`/`section_help` off the wire, and `console/src/surfaces/preview.tsx:70-125`'s
`EditableField` interface has no `description`/`section_summary` property at
all — the long text cannot reach this screen even if a future change put it
back on the wire, because there is nowhere on this type for it to land.

The regression test the control cites was run rather than read:
`tests/unit/platform/config_service/test_fields.py:122-163`
(`_LEAKS`/`test_no_help_text_carries_what_only_this_repository_can_read`)
checks every declared field's `help` *and* `section_help`, plus every
list-entry field's, against `FR-\d+`, `\bArticle\s+[IVX]+\b`, a `[\w/]+\.py\b`
path, and a double-backtick, across all 116 top-level fields, their 33
sections, and every item field inside an ordered list. `uv run python -m
pytest tests/unit/platform/config_service/ -q`: **340 passed**. No change
made.

### 2. Everything expanded, save far away — confirmed done, deviation upheld

`console/src/surfaces/preview.tsx:341-414` is the open-sections mechanism:
`readOpenSections`/`saveOpenSections` persist to `localStorage`, but the
*component* reads them through `useSyncExternalStore(subscribeToOpenSections,
readOpenSections, openSectionsServerSnapshot)` — the third argument returns
`NOTHING_OPEN` unconditionally, which is what the server rendered, so a
returning operator's first paint matches the HTML the server sent and the
browser's own memory of what was open arrives on the next tick rather than as
a visible correction. This is `console/src/shell/browser.ts`'s own documented
pattern for theme/density/locale, reused rather than reinvented — read to
confirm the claim rather than trusted.

`:617-650` is the sticky top bar: a `<Input type="search">` and a `<nav>` of
section links, `sticky top-0`. `:701-744` is the sticky bottom bar, `sticky
bottom-0` only once `!empty` (something is pending) — matching acceptance
criterion 4 ("editar qualquer campo torna preview/save alcançáveis sem rolar
a página") exactly: the moment a field is edited, `empty` becomes `false` and
the bar docks to the viewport's own bottom edge, not the document's.

The acceptance criterion's own words are "chegar a qualquer campo por sumário
ou busca em < 5 s" — summary *or* search, with no mention of a side rail. The
control's own account of choosing a sticky top bar over a side column, for a
closed spacing scale with no width declared for a new rail, is a defensible
reading of that same closed-scale principle `console/AGENTS.md` states for
this whole design system ("the scales are closed sets... `p-9` is not a
utility"), and it does not fall short of the criterion as written.

`console/tests/e2e/surfaces.spec.ts:82-116`
(`'the configuration preview is the deployment's answer'`) was re-run in a
real browser in this session, not assumed from the report: it fills
`input[name="config-field-search"]` with `'approval.required_above'`,
finds `select[name="approval.required_above"]` without ever scrolling, and
completes a preview. `make console-e2e`: **84 passed**, this test named among
them (see Verification). No change made.

### 3. Undefined field hides the effective default — the control's refusal, re-examined

**The field-row half — confirmed correct, unchanged.**
`preview.tsx:769-779` (`FieldRow`): `defaultKnown = field.provenance === ''
&& stringify(field.default) !== ''`; when true, the control opens on the
default and the provenance text (`:816-823`) reads `${labels.usingDefault}
${stringify(field.default)}` — "Using the deployment default: 5" — rather
than a blank control and "Set at nothing yet." Tested at
`config-editor.test.tsx:361-374` (`'shows the deployment default that
applies...'`, `'prefills the control with that default...'`), both passing.
This is the case `spec.md`'s own text names as the volume problem ("sob ~80
campos"), and it is genuinely fixed.

**The diff cell — traced to the backend, and left, for a reason stronger than
the one recorded.** `spec.md`'s problem 3 names a second, specific symptom in
the same sentence: "no diff do preview a coluna NOW vem vazia para um campo
não definido." `configuration.preview.before`'s catalogue value is literally
`'Now'` (`console/src/i18n/en.ts:1013`), confirming this is the same column.
Traced with `platform/config_service/preview.py:122-164`'s `preview_of`:

```python
before = dict(paths.leaves(document.settings))
...
changes=tuple(
    PreviewChange(path=path, before=before.get(path), after=_after(path, after, effective))
    for path in changed
),
```

`before` is built only from `document.settings` — this node's *own*, unmerged
document. For a path this node has never set (whether it is inherited from an
ancestor, or resolves purely to the schema's default with nothing anywhere in
the chain setting it), `before.get(path)` is `None`, which the console's
`stringify` renders as an empty string, verbatim, per `console/AGENTS.md`'s
"nothing here computes what the server computes" rule — confirmed correct as
a description of the *console's* behaviour: `Diff` (`preview.tsx:1170-1251`)
renders `change.before` with no further logic. `controle.md`'s recorded
reason for not fixing this — that fabricating the value client-side would be
the merge `AGENTS.md` forbids — is true and would stop a *console-side* fix.
It does not, on its own, stop a *server-side* one: `preview_of` already
computes `inherited = build(node_id, chain[:-1])` for the redundant/reverts
calculations a few lines below, so a fix mirroring the existing `_after`
pattern (`:182-192`, "read the explicit value if there is one, else consult
what the merge resolves to") was a small, well-precedented change to write —
and I wrote it out in full during this confrontation, in analysis, before
deciding not to commit it.

**Why it was not built.** `tests/unit/platform/config_service/test_preview_redundancy.py:176-183`:

```python
async def test_clearing_a_field_nothing_inherits_reverts_to_no_value_at_all() -> None:
    service = await _service(team_values=NodeDocument.of({"llm": {"model": "large"}}).to_values())
    preview = await service.preview_settings(TEAM, {}, remove=("llm.model",))
    assert [entry.path for entry in preview.reverts] == ["llm.model"]
    assert preview.reverts[0].value is None
    assert preview.reverts[0].inherited_from == ""
```

This test pins, by name, the exact sibling of what a "before" fix would also
have to change: `RevertedValue.value` (computed by the same `paths.value_at`
pattern `before` would need) is asserted to be `None`, not a schema default,
when nothing in the chain supplies the field. `git log --oneline --follow`
on this test file shows exactly one commit, `827ec0b`, "tell a preview when
a value is already inherited, and let one be cleared" — and `git log
--oneline | grep -n` places that commit 171 rows before `c512fae`, this
spec's own "write the configuration form" commit. This is not a decision
`c512fae` made and could revise; it is a foundational, deliberately tested
property of `platform/config_service/preview.py` that predates spec 032
entirely, confirmed by dating the commit rather than assuming it. Overturning
it would require deciding whether "before"/"reverts" ever consult a schema
default at all — a question about what `config_service`'s own preview
contract means, owned by whichever surface built that contract, not by a
screen-focused confrontation of the console that reads it. **No test was
written and no implementation was built for this half**, and this report
says so plainly rather than presenting the investigation as a fix.

Given this, item 3's acceptance-criterion coverage is real but not total:
"todo campo não definido mostra o default efetivo" holds for every field a
reader browses or edits on this screen, and does not hold for the one moment
a reader has already started editing a field that was undefined and asks the
deployment to preview it. That is a narrower gap than the one `spec.md`
opens with, and it is named rather than folded into either "done" or
silently dropped.

### 4. "Set at default" ambiguity — confirmed done

Two independent vocabularies on this one screen, both checked rather than
assumed to agree with each other. `configuration.tsx:94-118`
(`provenanceLabel`), for the effective-configuration table: `direct !==
undefined && direct !== ''` reads `'configuration.provenance.setAt'` ("Set
at: {node}"), and the no-override case reads `'configuration.provenance.default'`
("Deployment default") — the two catalogue keys never share the word
"default" for the unset case. `preview.tsx:816-823` (`FieldRow`), for the
editor: `field.provenance !== '' ? \`${labels.setAt} ${field.provenance}\` :
...` — "Set at:" (with a colon) for a real override, "Using the deployment
default:" or "Set at nothing yet" for the two unset cases, again never
sharing "default" as the word for "no override."

Both are tested against the literal trap the problem statement names — a
node whose id is the string `default`, holding a real override:
`configuration.test.ts:17-23` (`provenanceLabel('en', 'agents.tool_budget',
new Map([['agents.tool_budget', 'default']]))` → `'Set at: default'`, never
`'Deployment default'`), `config-editor.test.tsx:376-383` (`'never says an
override is "the default", even at a node literally named default'`). Both
run: passing. No change made.

### 5. Effective configuration: cryptic collapse, `UNKNOWN` badge — confirmed done

`configuration.tsx:41-73` (`ConfigValue`/`prettyNested`): a nested value now
renders inside a native `<details>`, collapsed to an 80-character preview and
expanding to `JSON.stringify(..., null, 2)` — a working disclosure where the
"before" state (per the problem statement) had none at all, only an
un-expandable truncated line. A repository search (`grep -rn "UNKNOWN\|
'unknown'"`) across `configuration.tsx`, `preview.tsx`, `tree.tsx`,
`editable.ts`, and `read.ts` — every file this screen's data flow
reaches — found nothing: no `'unknown'` string literal and no `UNKNOWN`
badge status anywhere in the chain. `provenanceLabel`'s `children.size > 1`
branch (`configuration.tsx:114-116`) is the one case that genuinely needs a
word for "this compound row's leaves disagree on their source," and it says
so — `'Set across more than one node'` — rather than falling back to a
generic placeholder. No change made.

### 6. Generated labels — the named complaint fixed already, its sibling fixed here

**Confirmed already correct: the card is no longer titled by its evaluation
slug.** `entryTitle` (`preview.tsx:424-429`) reads only `item.path === 'name'`
on the entry itself, with no fallback to index or path — "Falling back to
anything derived... would put a guess where 'proxmox' belongs," per its own
comment. `ObjectList` (`:989-1022`) renders that name as `entry-title` and
`labels.entryPosition` ("Evaluated") plus the 1-based index as a *separate*,
honestly-labelled `entry-position` span beside it — the fix reinterprets
"Evaluated N" as a genuine, distinct fact (first-match-wins order) rather
than removing it, which is the correct reading of a routing-rule list where
position *is* the value. Tested: `config-editor.test.tsx:482-486`,
`object-list.test.tsx:224-231`.

**The residual: an unnamed entry's toggle still named nothing, in the exact
same conditional.** Before this session,
`preview.tsx:1063-1069` read:

```tsx
item.type === 'boolean' && title !== ''
  ? { ...item, label: `${title} — ${item.label}` }
  : item
```

For an entry with `title === ''` — every entry immediately after "Add
another," before a name has been typed — a boolean toggle inside it fell
through unchanged, with no object context at all: exactly "toggles 'Enabled'
sem objeto quando lidos isolados," the literal words of the problem
statement, for the one case its own fix left uncovered. No existing test in
`config-editor.test.tsx` or `object-list.test.tsx` exercised a boolean item
field together with an empty-titled entry — confirmed by reading both files
in full before writing anything.

Test-first: `config-editor.test.tsx`'s new `'names the toggle by its
position instead, for an entry with no name typed yet'`
(`:495-503`), asserting `screen.getByLabelText('Evaluated 1 — Enabled')`
against an entry with `name: ''`. Run before the fix: **failed** —
`TestingLibraryElementError: Unable to find a label with the text of:
Evaluated 1 — Enabled` — confirmed red. Fixed at `preview.tsx:1063-1075`:

```tsx
item.type === 'boolean'
  ? {
      ...item,
      label: `${title !== '' ? title : `${labels.entryPosition} ${String(index + 1)}`} — ${item.label}`,
    }
  : item
```

Position is substituted for name only when there is no name — never invented
where one exists, and never omitted where none does; `index` and `labels`
were both already in scope, so nothing new had to be threaded in. After the
fix: the new test passes, and the two pre-existing tests in the same
`describe` block (naming by an existing entry's real name) are unaffected —
`config-editor.test.tsx`/`object-list.test.tsx` together: 69 passed. One
real `eslint` finding surfaced while fixing this (below), corrected before
declaring it done.

### The Brazilian-Portuguese sweep, on this screen's own catalogue block

Found while reading the whole `configuration.*` block of
`console/src/i18n/pt-BR.ts` for the exact lines items 3, 4 and 6 needed —
not a repository-wide sweep, and every instance below is reachable from this
screen specifically.

```
pt-BR.ts:873  'Configuração efectiva'                → 'Configuração efetiva'
pt-BR.ts:892  'Ver os valores efectivos'              → 'Ver os valores efetivos'
```
The pre-agreement silent-consonant class 022 Detectors' and 024 Knowledge's
confrontations already fixed elsewhere (`Objectivo`→`Objetivo`,
`Actualizado`→`Atualizado`); reachable from the "Effective configuration"
panel's own title and its empty-state action.

```
pt-BR.ts:936  'Cada controlo abaixo vem do esquema...' → 'Cada controle abaixo vem do esquema...'
```
`controlo` as a noun (a form control) is the European spelling; Brazilian
Portuguese uses `controle` for the same noun — the identical
`controlo`/`controle` split 024 Knowledge's confrontation already fixed once
for `knowledge.documents.empty.body`'s "nenhum controlo de upload," now found
a second time, independently, in this screen's own editor lead sentence
(`configuration.tsx:272`, always rendered above the editor).

```
pt-BR.ts:939  'A guardar…'                            → 'Guardando…'
```
The "estar a + infinitive" progressive is specifically European; Brazilian
Portuguese uses the gerund. This is the identical grammatical shape
`surface.loading`'s already-known `'A carregar {panel}…'` is — but this key
is `configuration.editor.saving`, owned by this screen alone, not the
52-call-site shared chrome string named in this confrontation's brief, so it
is fixed here rather than merely named. The verb itself (`Guardar`) is kept
unchanged: `'Guardar'`/`'Guardado'` are lexical choices valid in both
dialects, the same judgement 022 Detectors' and 031 Autonomy's confrontations
already recorded for the identical word.

```
pt-BR.ts:942  'Não foi possível contactar o deployment.' → 'Não foi possível contatar o deployment.'
```
`contacto`/`contactar` (European, the 'c' pronounced) versus `contato`/
`contatar` (Brazilian, and independent of the 1990 orthographic agreement —
Brazil never had the 'c' to begin with) is the same class of split as
`objectivo`/`objetivo`, just not one the agreement touches. Reachable
whenever the editor's own preview or save request fails to reach the
deployment.

```
pt-BR.ts:944  '...o diff é o único sítio onde a herança é visível.' → '...o único lugar onde...'
```
`sítio` meaning "place" is European usage; in Brazilian Portuguese `sítio`
means a small rural property, and "place" is `lugar` — the same shape as the
already-known `equipa`/`equipe` split (a word that exists in both dialects
but means something else in one of them). Single occurrence in the whole
catalogue, confirmed by a repository-wide search before fixing it, so nothing
elsewhere needed to move in step.

```
pt-BR.ts:950  'Uma lista ou uma secção livre: ...'    → 'Uma lista ou uma seção livre: ...'
```
The same pre-agreement silent-consonant class as `efectiva` above
(`secção`→`seção`), and specifically an internal inconsistency within this
one screen's own block: `configuration.editor.toc` six lines below, at
`pt-BR.ts:961`, already correctly reads `'Ir para uma seção'` — one line
using each spelling for the same word, the exact "one line short" shape this
audit was told to watch for.

**Traced and deliberately left alone**, named rather than rediscovered next
time this screen is touched: `surface.loading` (`'A carregar {panel}…'`) is
reachable from every `Panel` on this screen through `panelLabels`, but it is
the 52-call-site shared chrome this confrontation's brief already names as
out of scope. `teamContext.*`'s own `secção`/`secção`/`secção` (`pt-BR.ts:909-911`),
`contactar` (`:931`), `A guardar…` (`:928`), and `ecrã` (`:895`), and
`signIn.unreachable`'s `contactar` (`:350`) are the identical patterns found
above, on catalogue keys belonging to the Team Context and Sign-in screens
respectively — a different surface each, not fixed here. `nav.teamContext`/
`page.teamContext.title`'s `equipa` is the cluster this confrontation's brief
already names as a known offender in schedules/Team Context; confirmed
present, not rediscovered as new, not touched.

## Verification

Console, from `console/`:

- `pnpm exec vitest run tests/unit/surfaces/config-editor.test.tsx
  tests/unit/surfaces/object-list.test.tsx tests/unit/surfaces/configuration.test.ts`
  — run **before** any change: **73 passed (3 files)**, confirming items 1,
  2, 4 and 5's structural claims by running them rather than reading them.
  After adding item 6's new test, before its fix: **1 failed** (isolated
  run, `-t "names the toggle by its position"`), confirmed red — `Unable to
  find a label with the text of: Evaluated 1 — Enabled`. After the fix:
  **74 passed**, then **74 passed** again after the pt-BR corrections (no
  regression from a content-only catalogue edit).
- `pnpm exec vitest run tests/unit/surfaces tests/unit/i18n` — **98 passed
  (5 files)**, run after the pt-BR sweep to confirm the catalogue
  completeness/fallback tests still pass with the corrected values.
- `pnpm exec vitest run` (full unit suite) — **1992 passed (121 files)**,
  net +1 over the 1991 recorded at this branch's own prior commit, matching
  the one new test this confrontation added. One benign jsdom console line
  ("Not implemented: navigation to another Document") is the same
  pre-existing test-environment noise every prior confrontation in this
  series recorded, not a failure.
- `pnpm exec tsc --noEmit` — clean, no output.
- `pnpm exec eslint src/surfaces/preview.tsx src/i18n/pt-BR.ts
  tests/unit/surfaces/config-editor.test.tsx` — one real finding during the
  work: `@typescript-eslint/restrict-template-expressions` on `${index + 1}`
  inside a template literal (a `number` where the rule wants a string);
  corrected to `${String(index + 1)}`, re-linted clean, tests re-run to
  confirm the correction changed nothing behaviourally (69 passed across the
  two files).
- `pnpm exec prettier --check src/surfaces/preview.tsx src/i18n/pt-BR.ts
  tests/unit/surfaces/config-editor.test.tsx` — "All matched files use
  Prettier code style!" both before and after the lint fix.
- `make console-client-check` — clean; nothing about the API changed, so
  regenerating `src/api/schema.ts` from `fixtures/contract/openapi.json`
  produced no diff, confirmed by running it rather than assuming it from the
  absence of a backend change.
- `make console-build` — succeeded, all 47 routes including `/configuration`
  compiled, run before every build-dependent gate below per the standing
  instruction that `console-visual` alone never rebuilds.
- `make console-budget` — stylesheet 24062/40960 bytes (58%), icon set
  10918/16384 bytes (66%), both unchanged from the prior confrontation's
  own measurement (no new token, no new icon).
- `make console-visual` — **35 passed (35)**, including
  `configuration-1440-light`, run against the build that carries both
  changes in this confrontation. No baseline differs: the toggle-label fix
  is invisible in the `populated` fixture (its entries already carry names)
  and the catalogue edits are pt-BR-only, not exercised by the English
  capture. Nothing here needed the orchestrator's review.
- `make console-e2e` — **84 passed (0 failed)** across both Playwright
  projects (`behaviour`, 79; `first-day`, 5), including
  `surfaces.spec.ts:82` — `'the configuration preview is the deployment's
  answer'` — by name, confirming acceptance criterion 2 in a real browser
  rather than only in `jsdom`.
- `uv run python -m pytest tests/contract/console/ tests/unit/gateway/http/test_config_write_routes.py`
  — **650 passed** (this run also exercises `test_console_gate.py`'s seeded
  failures for lint/typecheck/format-check/e2e/visual, and
  `test_console_visual_regression.py`'s own seeded pixel-diff check —
  independent confirmation that the gates above are not walking an empty
  file list). `tests/unit/gateway/http/test_config_write_routes.py` was also
  run alone: **12 passed**.

On the environment note that `pnpm exec playwright` and `pnpm visual:accept`
do not work here: I did not invoke either directly. `make console-visual`
and `make console-e2e` go through `tools.console_gate`/`tools.console_e2e`
rather than a raw `pnpm exec playwright` call, and both completed to a full,
real pass in this session — confirmed by the seeded-failure sub-tests inside
`test_console_gate.py` genuinely failing when a fixture is spliced in and
genuinely passing once it is removed, not merely by the headline number
being zero. I did not run `make console-visual-accept` under any
circumstance, consistent with the standing instruction, and there was
nothing to accept: every baseline already matched.

Python, from the repository root:

- `uv run python -m pytest tests/unit/platform/config_service/ -q` — **340
  passed**, confirming item 1's regression guard by running it, and
  confirming (via `test_preview_redundancy.py`) the pre-existing invariant
  item 3's evidence rests on, both before any change and unmodified after
  (no Python file was touched).
- No Python file was changed in this confrontation. `ruff`/`mypy` were not
  run because there is nothing of this confrontation's own for them to
  check; the suite above was run to *read* the backend's current, correct
  behaviour, not to verify an edit to it.
- `KNOWN PRE-EXISTING, not mine:`
  `tests/contract/integrations/test_integration_parity.py::test_each_paginated_endpoint_declares_a_style_the_base_client_walks[google_gemini]`
  was not re-run — no file this confrontation could affect it was touched.

**On confirming new tests red first.** The one genuinely new assertion this
confrontation added — item 6's residual toggle-context test — was confirmed
red against the code as it stood immediately before its own fix, in the
words above, not inferred. No other item needed a new test: items 1, 2, 4,
and 5 were confirmed by *running* the existing tests and gates that already
covered them, unmodified, and all passed before this confrontation touched
anything, which is what stands in for red-before-green when nothing was
broken — the convention 021 Topology's, 023 Memory's, and 024 Knowledge's
confrontations used for the same situation. Item 3's backend investigation
produced no test, in either direction, and this report says that plainly:
a fix was designed in analysis and deliberately not written, because writing
it would have meant first breaking, and then rewriting, a test that belongs
to a package this confrontation does not own.

## Control reconciliation

`specs_v4/032-configuration/controle.md` keeps its seven rows, one per
`spec.md` problem — no row was missing, matching this series' better outcomes
rather than 024 Knowledge's dropped-row pattern. Items 1, 2, 4, 5, and 7 keep
their verdicts, with the detail column corrected to cite what was
independently run rather than repeating the prior wave's prose unchanged.
Item 3 moves from `FEITO` to `FEITO PARCIALMENTE`: the field-row half stands
exactly as recorded, and the diff-cell half's refusal is kept, but its stated
reason is corrected — not "the console must not merge" alone, but "a
server-side fix was designed, and found to collide with a deliberately
tested, pre-existing invariant of `config_service/preview.py` dated 171
commits before this spec's own UI work," which is a materially different and
more specific claim than the one on record. Item 6 stays `FEITO`, with its
detail split into what was already correct (the card's own title) and what
this confrontation closed (the isolated toggle inside an unnamed entry). A
closing note records the seven Brazilian-Portuguese corrections made in this
screen's own catalogue block, the "Guardar" verb choice left unchanged on
established precedent, and the six instances on `teamContext.*` and
`signIn.*` that carry the identical patterns but belong to other screens —
named so they are not rediscovered from nothing the next time either of
those screens, or this control file, is touched.
