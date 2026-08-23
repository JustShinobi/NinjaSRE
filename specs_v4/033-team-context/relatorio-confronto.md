# 033 Team context — implementation confrontation

Date: 2026-08-14.

## Conclusion

`controle.md` understated this spec's own state, in the same direction 031
Autonomy's confrontation already found for two of its own six rows: three of
this spec's four numbered problems were marked `NÃO INICIADO`, and two of
those three were, on inspection, already fully or partly built. Item 4 — an
entire "Organisation" column spent on one node's name — was already fixed:
`team-context.tsx:104-123` collapses the tree panel to a breadcrumb the
moment there is exactly one node and draws `OrgTree` only once there is a
real tree to navigate, and `team-context.test.tsx:102-124`'s two dedicated
tests, run against the unmodified working tree before this audit touched
anything, both passed. Item 1 — two link-sentences glued together with no
separator, the literal defect `spec.md` quotes — was likewise already fixed
and already tested: `operating-context.tsx:240-244` separates "Runbooks live
in Knowledge" and "Procedures live in Autonomy" with `' · '`, each sentence
carrying its own verb rather than being a bare noun, and
`operating-context.test.tsx:174-191` pins the exact concatenated string the
bug once produced. Item 2's first symptom — no concrete example anywhere
near the empty editor — turned out to be structurally satisfied too, in a
way `controle.md`'s own text ("NÃO INICIADO", no detail) could not have
distinguished from the deeper problem still sitting in the same numbered
item: `teamContext.factNotInstruction`'s catalogue sentence carries the
"Container metrics come from the host, by vmid" example verbatim, and
`operating-context.tsx:240-241` renders it unconditionally at the very top
of the editor — before any section exists, whether the editor is showing
zero rows because nothing has been written yet, or (the case `controle.md`
never distinguished, and the case a real deployment's second visit to this
screen is actually in) zero *explicit* rows with a deployment-derived
starting document sitting one click away. A new regression test
(`team-context.test.tsx:139-156`) pins exactly that second case and passed
on first run, against the code as it already stood — a verification, not a
fix, and this report says so rather than presenting it as one.

What `controle.md` marked `NÃO INICIADO` for the rest of item 2 and for item
3 was genuinely so, and both are fixed here, test-first, every new assertion
confirmed red against the unmodified tree before its own implementation
landed. "Start from this" never said what it was starting *from*, and
nothing near it did either — the catalogue's own better sentence,
`teamContext.template.lead`, had been written and translated in both
locales and never read by any component; renamed to "Use the starting
document" / "Usar o documento inicial" and its lead sentence wired in as the
button's own tooltip. "Show me the prompt" was disabled with no explanation
anywhere, the literal shape acceptance criterion 3 names — and checking, as
instructed, what else lives in the same file's disabled-state conditionals
found its exact sibling, "Add a section", disabled with no explanation
either, on the same screen, one component away, untested and unfixed by
whatever produced `controle.md`'s account of this item. Both now carry a
`title` explaining why, exactly and only while they are disabled — the same
mechanism `simulation.tsx:151-159` already established for this console,
reused rather than invented. And the budget line — "Prompt budget 0 of 1200
tokens" — never said what crossing it does; a new line, always visible,
under and over budget alike, now does. A Brazilian-Portuguese sweep of the
whole `teamContext.*` catalogue block, `nav.teamContext` and
`page.teamContext.*` — the cluster this confrontation's brief named as the
known remaining offender — found thirteen genuine European-Portuguese
spellings and constructions across those thirteen keys, four beyond the five
named in the brief, and all thirteen are fixed below.

**Correction made after coordinator review.** The first pass of this
confrontation traced item 4's parenthetical — "Vale igual para Configuration
e Autonomy, que têm o mesmo painel" — read it as a side note describing a
fact about two other specs' surfaces, and left Configuration's own copy of
the panel untouched on the grounds that neither spec 032's nor spec 031's
own `spec.md` names the problem. That reasoning was wrong about *whose*
surface the sentence belongs to: `specs_v4/033-team-context/spec.md:34` is
the last line of *this* spec's own item 4, not an aside about somebody
else's contract, and a reader of spec 033 is owed item 4 closed on every
screen it names. Corrected here: the collapse logic is extracted into one
shared function, `OrgNav` (`tree.tsx:179-203`), and both `team-context.tsx`
and `configuration.tsx` are moved onto it — reusing the already-tested logic
rather than writing a second copy, per the coordinator's instruction.
Autonomy's screen was re-confirmed, as it had already been traced, not to
use this component at all (`autonomy.tsx` imports neither `OrgTree` nor
`tree.tsx`), so that half of the parenthetical was already true and needed
no change. A new test (`configuration-tree.test.tsx:83-91`) was written and
confirmed red against `configuration.tsx` before this fix — the single-node
collapse it now proves did not exist on this screen a moment earlier.

## Table

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Links corridos sem pontuação | FEITO (`bf5f055`) | Confirmed accurate. `operating-context.tsx:240-244` separates the two link-sentences with `' · '`, each carrying its own verb ("live"/"vivem"); `operating-context.test.tsx:174-191` reproduces the literal glued string and passes against it. No sibling gluing found elsewhere in this screen's two files. | DONE (no change) |
| 2. O editor não se explica | NÃO INICIADO | Split three ways by what the code actually held. The concrete-example half was already true for every render of the editor — `factNotInstruction` (`operating-context.tsx:240-241`) is unconditional — including the specific "zero rows, template available" case `controle.md`'s bare verdict could not have distinguished. "Start from this" genuinely explained nothing: its own better sentence existed in both catalogues (`teamContext.template.lead`, `en.ts:1085`/`pt-BR.ts:921`) and was never wired into any component. "Show me the prompt" (`ask-context-preview`) was disabled with no explanation anywhere on the page, and its exact sibling in the same file, "Add a section" (`add-section`), was disabled the identical way, untouched by whatever produced the control's account. | Example: DONE (no change; now regression-tested, `team-context.test.tsx:139-156`). Naming + tooltips: DONE (fixed here, test-first) |
| 3. Orçamento sem consequência explicada | NÃO INICIADO | Confirmed accurate. `context-budget` (`operating-context.tsx:253-261`, pre-edit) showed the count and nothing else; no sentence anywhere on the page said what happens past it. | DONE (fixed here, test-first) |
| 4. Coluna Organisation desperdiçada | NÃO INICIADO | Wrong on Team context, right on Configuration. `team-context.tsx:104-123` (pre-refactor) already collapsed to a breadcrumb at exactly one node; `team-context.test.tsx:102-124`'s two tests, run against the unmodified tree, both passed before this audit touched anything. `configuration.tsx:184` (pre-fix), by contrast, rendered `OrgTree` unconditionally — the same defect spec.md's own item 4 names for this screen, in its own last line, still genuinely present. | DONE on both screens. Team context: no change. Configuration: fixed here, test-first — see the correction note in the Conclusion. Autonomy re-confirmed not to use this component, so nothing there needed touching. |

## Evidence and corrections

### 1. Links corridos sem pontuação — confirmed done, no sibling found

`operating-context.tsx:240-244`:

```tsx
<p data-testid="fact-not-instruction" className="text-meta text-muted">
  {labels.factNotInstruction} <Link href="/knowledge">{labels.runbooks}</Link>
  {' · '}
  <Link href="/autonomy">{labels.policy}</Link>
</p>
```

`teamContext.runbooks` (`en.ts:1064`) is "Runbooks live in Knowledge" and
`teamContext.policy` (`en.ts:1065`) is "Procedures live in Autonomy" — both
already full sentences with their own verb, not bare nouns standing in for
one, and the pt-BR pair (`pt-BR.ts:898-899`, "Os runbooks vivem em
Conhecimento" / "Os procedimentos vivem em Autonomia") carries the same
shape independently. `operating-context.test.tsx:174-191`
(`'states that this field is for facts and points at where instructions
go'`) asserts both link hrefs and, specifically, that the rendered text
contains `` `${LABELS.runbooks} · ${LABELS.policy}` `` — the exact
concatenated string the bug report quotes, with the separator now between
them. Run before any change in this confrontation: **passed**. I read both
files in full (`operating-context.tsx`'s 417 lines, `team-context.tsx`'s 191
lines) for any other place two link-sentences sit next to each other in
prose; there is exactly one such spot on this whole screen, and it is this
one. No change made.

### 2a. The concrete example — already structurally true, now pinned against the case that mattered

`operating-context.tsx:240-241` renders `labels.factNotInstruction`
unconditionally, as the very first thing inside
`data-testid="operating-context-editor"`, before the `rows.map(...)` that
draws any actual section. `teamContext.factNotInstruction` (`en.ts:1062-1063`)
carries the exact sentence `spec.md` names as the example that should be
reachable: "Write facts, not instructions. "Container metrics come from the
host, by vmid" changes how an agent reads what it sees...". Because this
paragraph does not branch on `rows.length`, it is present whether the editor
has real sections, has zero sections with nothing to show, or — the case
that matters here — has zero explicit sections but a deployment-derived
`template` waiting one click away, which is the state `stateOf`
(`team-context.tsx:129`, `sections.length === 0 && template.length === 0`)
resolves to `'ready'` rather than `'empty'` for, so `Panel`
(`panel.tsx:173-200`) renders the editor itself rather than its own
composed `EmptyState`.

`team-context.tsx:128-144`'s `empty.body` — `` `${message(locale,
'teamContext.empty.body')} ${message(locale,
'teamContext.factNotInstruction')}` `` — covers the *other* empty case, both
`sections` and `template` empty, where `Panel` shows its own `EmptyState`
instead of the editor at all; the pre-existing test
`team-context.test.tsx:127-138` already pinned that one and continues to
pass, unmodified.

What was missing was a test for the case in between — an editor that
*renders*, with zero rows, because a starting document exists.
`team-context.test.tsx:139-156` (new, `'keeps the same example visible once
a starting document exists, before anything is written'`) serves a node
with `sections: []` and a non-empty `template`, and asserts
`getByTestId('operating-context-editor')` contains "Container metrics come
from the host, by vmid". Run against the code exactly as it stood: **passed
immediately** — a verification of a case that was already structurally
correct, not a fix, and this report records it as one rather than folding it
silently into "done."

I considered, and rejected, literally moving this text into an HTML
`placeholder` attribute on the "Section name" `Input` or a new section's
`Textarea`, which is the mechanism `spec.md`'s own parenthetical suggests
("que deveria estar como placeholder"). `form.tsx:12-15`'s own doctrine
states the opposite, in words: "Every control has a real label — not a
placeholder, which disappears the moment somebody types and takes the
question with it." Building the literal placeholder would have satisfied
one reading of the problem statement while breaking a deliberate,
documented accessibility rule of this exact component library — and the
acceptance criterion's own words ("um exemplo concreto... visível") ask for
visibility, not for a specific mechanism, which the always-rendered
sentence already gives, permanently rather than only while a field is
empty. Nothing was built here for that reason.

### 2b. "Start from this" — genuinely unfixed, fixed here

Confirmed before any change: `en.ts:1085` (pre-edit) read `'teamContext.template.use':
'Start from this'`, and `operating-context.tsx` (pre-edit) rendered nothing
else near the button — no heading, no lead sentence, nothing answering
"start from what?". `teamContext.template.title`
("A starting point, from what is already known") and `teamContext.template.lead`
("Derived from this deployment's own estate — the kinds it holds, the zones
its addresses sit on, the source that answers each signal question. Nothing
here is written until you save it.") existed in both catalogues, fully
translated, and — confirmed by reading `OperatingContextLabels`
(pre-edit) and `team-context.tsx`'s `labels={{...}}` object in full — were
never passed to the component that could have shown them. Two authored,
translated sentences, sitting completely dead.

Test-first: `operating-context.test.tsx:368-375`
(`'names what the starting-document button does, rather than "start from
this"'`) and `team-context.test.tsx:164-172` (`'says what it does instead of
the unexplained "Start from this"'`) were both run against the unmodified
tree. Both **failed**: the component-level test found no `title` attribute
(`Received: null` against the expected `templateLead` string); the
screen-level test found the literal text "Start from this" still in the
document. Confirmed red.

Fixed by renaming the button's own label to the vocabulary this screen
already uses elsewhere for the same document (`teamContext.empty.body`'s
"The starting document below is derived from..."; the module doc comment's
own "The starting document is offered only where nothing has been
written."): `teamContext.template.use` is now "Use the starting document" /
"Usar o documento inicial" (`en.ts:1087`, `pt-BR.ts:923`). The previously
dead `teamContext.template.lead` is now wired through as the button's own
`title`, so the longer answer is one hover away rather than nowhere:

```tsx
{template.length === 0 ? null : (
  // The label alone answers "start from what?"; the title carries the
  // longer answer (what it was derived from, and that nothing is
  // written until save) for whoever hovers rather than guesses.
  <Button data-testid="use-template" title={labels.templateLead} onClick={...}>
    {labels.templateUse}
  </Button>
)}
```

(`operating-context.tsx:337-350`). `OperatingContextLabels` gained
`templateLead: string` (`operating-context.tsx:79-80`), threaded from
`team-context.tsx:190` (`templateLead: message(locale,
'teamContext.template.lead')`). `teamContext.template.title` remains
declared and unused — I did not invent a place to put a second, shorter
heading beside a single button when the one sentence already answers the
question; named here rather than rediscovered as new. After the fix, both
new tests pass.

### 2c. Disabled buttons with no explanation — the named one, and its unfixed sibling

Confirmed before any change: neither `add-section` nor `ask-context-preview`
ever carried a `title`, a description, or any nearby text explaining why
they were sometimes inert — `Button` (`action.tsx:85-110`) is a plain
`<button>` with no built-in tooltip mechanism, and nothing supplied one.
This is the literal shape acceptance criterion 3 names ("todo botão
desabilitado explica por quê"), and checking every disabled control this
screen's two files can render — the instruction to check siblings before
declaring an item done — found exactly two, both silent: the one `spec.md`
names by name ("Show me the prompt"), and "Add a section", disabled
whenever `naming.trim() === ''`, in the same file, in a sibling conditional
a few lines below. `save-context` (`operating-context.tsx:412-419`) is never
disabled, so it needed nothing; `use-template` is never disabled either
(only conditionally rendered), so its own fix in 2b — a `title` for context
rather than for a disabled reason — is independent of this criterion.
`AreaHeader` (`shell/area.tsx:43-70`), `OrgTree` (`tree.tsx:149-177`) and
`Breadcrumb` (`navigation.tsx:183-204`) — the rest of what this screen
renders — carry no buttons at all, confirmed by reading all three; there was
nowhere else on the page to check. (The tree/breadcrumb choice was later
extracted into `OrgNav`, item 4's own fix below; the underlying components
checked here did not change.)

Test-first, four new tests, run against the unmodified tree before any
component change: `operating-context.test.tsx:245-252`
(`'explains why "Show me the prompt" is disabled...'`) and
`operating-context.test.tsx:459-466` (`'explains why "Add a section" is
disabled...'`) both **failed** — `Received: null` against the expected
reason string in both cases, confirmed red. The other two,
`operating-context.test.tsx:254-259` and `:468-475` (`'carries no disabled
explanation once...'`), **passed trivially** against the unmodified code —
there was never a `title` attribute at all, so a negative assertion cannot
distinguish "explained correctly" from "never explained"; they stand as
regression guards from here rather than as evidence the defect existed, and
this report says so rather than counting them as red-then-green pins.

Fixed at `operating-context.tsx:158-162` (a named boolean, computed once,
rather than the condition repeated at both the `state` and the `title`):

```tsx
// Neither a pending edit nor an existing preview to show: there is nothing
// new for a preview to say yet, and the button explains exactly that.
const previewBlocked = !edited && !current;
```

and at the two buttons themselves (`:323-336`, `:354-370`):

```tsx
<Button
  data-testid="add-section"
  state={naming.trim() === '' ? 'disabled' : 'default'}
  title={naming.trim() === '' ? labels.addSectionDisabledReason : undefined}
  ...
>
```
```tsx
<Button
  variant="primary"
  data-testid="ask-context-preview"
  state={busy === 'preview' ? 'loading' : previewBlocked ? 'disabled' : 'default'}
  title={previewBlocked ? labels.previewDisabledReason : undefined}
  ...
>
```

— the same conditional `title` pattern `simulation.tsx:151-159` already
established elsewhere in this console (`title={answer === undefined ?
labels.needsSimulation : undefined}`), reused rather than invented. Two new
catalogue keys, both locales: `teamContext.addSection.disabledReason`
("Type a name before adding a section." / "Digite um nome antes de
acrescentar uma seção.", `en.ts:1077`/`pt-BR.ts:912`) and
`teamContext.preview.disabledReason` ("Change a section before asking for
the prompt." / "Altere uma seção antes de pedir o prompt.",
`en.ts:1092`/`pt-BR.ts:928`). After the fix, all four tests pass.

### 3. The budget's consequence — genuinely unfixed, fixed here

Confirmed before any change: `operating-context.tsx:253-261` (pre-edit)
rendered `labels.budget` and `labels.budgetUsed` and nothing else; the only
sentence anywhere naming a consequence was `labels.overBudget`
("Over the budget. The deployment will refuse this until it is shorter."),
and it rendered only once a node was *already* over — reactive, never seen
by an operator who has not yet approached the limit, which is the specific
gap `spec.md` names.

Test-first: `operating-context.test.tsx:210-227`, two tests — `'explains
the consequence of the budget before anybody is anywhere near it'` and
`'keeps explaining the consequence once the budget is actually exceeded'`.
Run against the unmodified tree: **both failed**, `Unable to find an
element by: [data-testid="context-budget-consequence"]`, confirmed red (the
element did not exist at all). Fixed by adding one always-visible line,
under and over budget alike, immediately below the count
(`operating-context.tsx:262-266`):

```tsx
{/* Said before anyone is near the limit, not only once they have crossed
    it: what happens past the budget is a refusal, never a silent cut. */}
<p data-testid="context-budget-consequence" className="text-meta text-muted">
  {labels.budgetConsequence}
</p>
```

New catalogue key, both locales: `teamContext.budgetConsequence` — "What
goes over budget is refused, not truncated." / "O que ultrapassa o
orçamento é recusado, não truncado." (`en.ts:1071`, `pt-BR.ts:905-906`),
echoing the exact contrast `spec.md`'s own text draws ("o que passa de 1200
é recusado, não truncado"). After the fix, both tests pass.

### 4. The wasted Organisation column — already fixed on Team context, genuinely broken and fixed here on Configuration

**Team context — confirmed already correct, no gap found.**
`team-context.test.tsx:101-113` (`'collapses the tree panel to a breadcrumb
rather than a one-row nav'`) serves a single-node organisation and asserts
`org-breadcrumb` is present, named "Northwind", and `org-tree` is absent;
`:115-124` (`'keeps drawing the tree rather than collapsing it'`) serves the
`populated` fixture (more than one node) and asserts the reverse. Both were
run against the tree exactly as it stood before this audit touched
anything: both **passed**. No gap was found to pin, and none was invented;
this is a verification, recorded as one.

**Configuration — genuinely broken, and this is this spec's own problem,
not another spec's.** `spec.md`'s item 4 ends with "(Vale igual para
Configuration e Autonomy, que têm o mesmo painel.)" — the last line of the
same numbered item, not a footnote about a different contract. I first read
this the wrong way round, and left it untouched on the reasoning that
neither `specs_v4/032-configuration/spec.md` nor `specs_v4/031-autonomy/spec.md`
names the problem in their own text — true, but beside the point: the
sentence sits inside spec 033's own item 4, and a reader of *this* spec is
owed it closed on the screens it names, whichever package the file
implementing that screen happens to belong to. Corrected after the
coordinator's review.

`configuration.tsx:184` (pre-fix) read:

```tsx
<OrgTree
  nodes={placed}
  selected={selected}
  label={message(locale, 'configuration.tree.title')}
  hrefFor={(id) => `/configuration?node=${encodeURIComponent(id)}`}
/>
```

— no `placed.length > 1` guard anywhere, so a single-node deployment spent
Configuration's whole left column on one node's name, exactly the defect
`spec.md` names. Confirmed by `codegraph_explore`'s blast radius for
`OrgTree` (`tree.tsx:148`, before this fix): exactly two real callers,
`team-context.tsx` and `configuration.tsx`, neither collapsing on
Configuration's side.

**Autonomy — re-confirmed, not fixed, because there is nothing to fix.**
`autonomy.tsx` imports neither `OrgTree` nor anything from `tree.tsx` — a
repository-wide check for the import confirms it — so the parenthetical's
second half ("...e Autonomy, que têm o mesmo painel") does not hold as
literally written: Autonomy does not have this panel at all, under any
name, so there is no column to collapse there. This half of the sentence
was already true before this audit and needed no change; it is not the same
thing as "out of scope," and this report says so rather than filing it
under the item it withdrew from item 2 of 031 Autonomy's own confrontation.

**Reused rather than duplicated.** Rather than copying team-context's
already-working `placed.length > 1 ? <OrgTree ...> : <breadcrumb>` logic a
second time into `configuration.tsx`, both call sites are moved onto one
shared function, `OrgNav` (`tree.tsx:179-203`):

```tsx
export function OrgNav({ nodes, selected, hrefFor, label }: OrgTreeProps): ReactNode {
  if (nodes.length > 1) {
    return <OrgTree nodes={nodes} selected={selected} hrefFor={hrefFor} label={label} />;
  }
  return (
    <div data-testid="org-breadcrumb">
      <Breadcrumb label={label} trail={nodes.map((node) => ({ label: node.name }))} />
    </div>
  );
}
```

`team-context.tsx:103-108` and `configuration.tsx:184-189` both now read
`<OrgNav nodes={placed} selected={selected} label={...} hrefFor={...} />`;
`team-context.tsx`'s own `Breadcrumb` import, no longer needed once the
inline branch moved into `tree.tsx`, is removed with it.

Test-first: `configuration-tree.test.tsx` (new file) mirrors
`team-context.test.tsx`'s own two tests, rendering the real
`/configuration` route. Run against the unmodified `configuration.tsx`,
before any fix: **1 failed, 1 passed** —
`:83-91` (`'collapses the tree panel to a breadcrumb rather than a one-row
nav'`) failed with `Unable to find an element by:
[data-testid="org-breadcrumb"]`, confirmed red; `:94-102` (`'keeps drawing
the tree rather than collapsing it'`) passed trivially, because
`OrgTree` was already the only thing this screen ever rendered. After the
fix, both pass, and `team-context.test.tsx`'s own two pre-existing tests —
run again, unmodified, after the refactor — still pass, proving the
extraction changed nothing about the already-correct screen. Two further
tests were added directly against `OrgNav` in `tree.test.tsx` (the shared
function's own describe block) once the extraction already existed; they
were not confirmed red first, and this report says so rather than
presenting them as a pin — the behaviour they check was already
characterised, before and after the refactor, by the two screen-level test
files above, which *were* run red-then-green at the two points that
mattered (Configuration's own fix; the refactor's preservation of Team
context's own already-correct behaviour).

### The Brazilian-Portuguese sweep, on the whole `teamContext.*` block

Read in full — `nav.teamContext`, `page.teamContext.title`,
`page.teamContext.context`, and every `teamContext.*` key in `pt-BR.ts`,
plus a repository-wide grep for each pattern found, to confirm scope before
touching anything and to catch any sibling elsewhere in the same catalogue.

```
pt-BR.ts:43   'nav.teamContext': 'Contexto da equipa'          → 'Contexto da equipe'
pt-BR.ts:244  'page.teamContext.title': 'Contexto da equipa'   → 'Contexto da equipe'
```
The two instances this confrontation's brief named directly. `equipa`
(European) vs `equipe` (Brazilian) — the same split `page.catalogue.context`
(`pt-BR.ts:249`, unrelated screen) already gets right ("...quais delas a sua
**equipe** pode usar"), confirming which spelling is this repository's own
established one. Two further instances of the same word, `schedules.caption`
and `schedules.empty.body` (`pt-BR.ts:686,689`), carry the identical defect
but belong to the Schedules screen, not Team Context — traced, named, not
touched, matching the brief's own account of where this cluster lives.

```
pt-BR.ts:245  'Factos sobre este ambiente...'                  → 'Fatos sobre este ambiente...'
pt-BR.ts:894  'Factos que um operador escreve...'               → 'Fatos que um operador escreve...'
pt-BR.ts:896  'Escreva factos, não instruções...'                → 'Escreva fatos, não instruções...'
```
`facto`/`fato` is the same pre-agreement silent-consonant split as
`objectivo`/`objetivo` — a repository-wide search found all three instances
of this spelling anywhere in `pt-BR.ts` sitting inside this one screen's own
keys (`page.teamContext.context`, `teamContext.sections.lead`,
`teamContext.factNotInstruction`), and the correct spelling already
established elsewhere in the same file (`agent.replay.title`,
`pt-BR.ts:1233`: "...sobre o que **de fato** aconteceu").

```
pt-BR.ts:894  '...no ecrã de Configuração...'                   → '...na tela de Configuração...'
```
The only `ecrã` in the entire catalogue; European for "screen" where
Brazilian Portuguese uses `tela` — the same word this series has already
corrected once for `surface.loading`'s sibling pattern.

```
pt-BR.ts:896  '"...um contentor vêm do anfitrião..."'  → '"...um container vêm do host..."'
```
Not a silent-consonant spelling but the identical vocabulary defect as
`equipa`/`sítio` in prior confrontations' sweeps: `resources.column.source.hint`
(`pt-BR.ts:631`), describing the *same fact* about the *same platform*
("Um **container** compartilha o kernel do **host**..."), already keeps
"container" and "host" as the English loanwords this repository's own
Brazilian tech vocabulary uses; `teamContext.factNotInstruction` translated
them literally into "contentor"/"anfitrião" instead — an internal
inconsistency inside the very sentence this spec's own problem statement
quotes as the good example, found by reading it against its own sibling
elsewhere in the catalogue rather than assumed correct.

```
pt-BR.ts:900,911,912,914,915  'Secção'/'secção' (×4)            → 'Seção'/'seção'
```
The same pre-agreement silent-consonant class; all four instances of this
spelling anywhere in `pt-BR.ts` are inside this one screen's own keys
(`teamContext.column.section`, `.addSection`, `.sectionName`, `.remove`) —
confirmed by a repository-wide search, so nothing elsewhere needed to move
in step.

```
pt-BR.ts:925  'O texto exacto que o prompt...'                  → 'O texto exato que o prompt...'
```
The lone `exacto` in the catalogue; same class again, confirmed unique by
search before fixing it.

```
pt-BR.ts:929  'teamContext.preview.previewing': 'A montar…'     → 'Montando…'
pt-BR.ts:933  'teamContext.saving': 'A guardar…'                → 'Guardando…'
```
The "estar a + infinitive" progressive is specifically European; Brazilian
Portuguese uses the gerund — the identical shape `surface.loading`'s
already-known `'A carregar…'` is. `A guardar…` is the instance this
confrontation's brief named directly; `A montar…`, six lines below inside
the very same block, carries the identical construction and was not named —
found here by reading the whole block rather than only the named line, and
fixed the same way. The verb itself, `Guardar`/`Guardado`, is left
unchanged throughout — a lexical choice valid in both dialects, the
judgement 022 Detectors', 031 Autonomy's and 032 Configuration's
confrontations already recorded for the identical word, and explicitly not
the catalogue-wide `Guardar`→`Salvar` sweep reserved for later.

```
pt-BR.ts:936  'Não foi possível contactar o deployment.'         → 'Não foi possível contatar o deployment.'
```
The instance this confrontation's brief named directly. `contacto`/`contactar`
(European) vs `contato`/`contatar` (Brazilian) — confirmed against this
exact repository's own established spelling one screen away,
`detectors.control.unreachable` (`pt-BR.ts:681`): "Não foi possível
**contatar** a instalação." Two further instances of the European spelling
were found and are named, not touched, because they belong to the Sign-in
screen: `signIn.context` (`pt-BR.ts:345`, "Esta consola **contacta** a sua
instalação...") and `signIn.unreachable` (`pt-BR.ts:350`, already named by
032 Configuration's own confrontation) — the first of these two is a new
finding this confrontation's own sweep turned up, not previously recorded
anywhere.

All thirteen corrections were verified with a repository-wide,
case-insensitive re-grep of the whole `teamContext.*` block after editing,
confirming none of the nine patterns (`secç`, `contact`, the two
progressive forms, `ecrã`, `equipa`, `contentor`, `anfitri`, `exact`,
`fact[o]`) remains inside it.

## Verification

Two passes: the first covers items 1, 2 and 3 and the Team context half of
item 4; the second, after the coordinator's correction, covers Configuration's
own half of item 4 (the `OrgNav` extraction and its two call sites). Numbers
below are from the final state, with each pass's own red-then-green step
called out where the two differ.

Console, from `console/`:

- `pnpm exec vitest run tests/unit/surfaces/team-context.test.tsx
  tests/unit/surfaces/operating-context.test.tsx tests/unit/surfaces/tree.test.tsx`
  — run **before any change**: **33 passed (3 files)**, confirming items 1
  and 4's structural claims, and item 2's example half, by running them
  rather than reading them. After adding the new tests for items 2b, 2c and
  3, **before** their implementation: **5 failed** in
  `operating-context.test.tsx` (budget consequence ×2, preview-disabled
  reason, add-section-disabled reason, starting-document naming) and
  **1 failed** in `team-context.test.tsx` (the starting-document rename,
  checked against the real catalogue) — six genuinely new failures,
  confirmed red one by one above; two further new assertions ("carries no
  disabled explanation...") passed trivially against the unmodified code, as
  recorded per item. After that fix: **42 passed (3 files)**.
- `pnpm exec vitest run tests/unit/surfaces/configuration-tree.test.tsx`
  (new file) — written and run against the unmodified `configuration.tsx`,
  before the `OrgNav` fix: **1 failed, 1 passed** — the single-node
  collapse test failed with `Unable to find an element by:
  [data-testid="org-breadcrumb"]`, confirmed red; the multi-node test
  passed trivially, since `OrgTree` was already the only thing that screen
  ever rendered. After the fix: **2 passed**.
- `pnpm exec vitest run tests/unit/surfaces/tree.test.tsx
  tests/unit/surfaces/team-context.test.tsx
  tests/unit/surfaces/configuration-tree.test.tsx
  tests/unit/surfaces/configuration.test.ts
  tests/unit/surfaces/operating-context.test.tsx` (final, after the
  `OrgNav` extraction) — **51 passed (5 files)**, including
  `team-context.test.tsx`'s two pre-existing tree/breadcrumb tests, re-run
  unmodified after the refactor and still passing — proving the extraction
  did not change Team context's already-correct behaviour.
- `pnpm exec vitest run tests/unit/i18n` — **24 passed (2 files)**, run
  after the catalogue edits to confirm completeness and fallback still hold
  with every new and renamed key present in both locales.
- `pnpm exec vitest run` (full unit suite, final) — **2005 passed (122
  files)**, net +13 over this branch's own prior state (1992, per 032
  Configuration's own last-recorded count): nine tests from the first pass
  plus four from the second (two in `configuration-tree.test.tsx`, two
  characterising `OrgNav` directly in `tree.test.tsx`). One benign jsdom
  console line ("Not implemented: navigation to another Document") is the
  same pre-existing test-environment noise every prior confrontation in this
  series has recorded, not a failure.
- `pnpm exec tsc --noEmit` — clean, no output, both passes.
- `pnpm exec eslint` on every touched file (`operating-context.tsx`,
  `team-context.tsx`, `configuration.tsx`, `tree.tsx`, `en.ts`, `pt-BR.ts`,
  and the four test files) — clean, both before and after the prettier
  passes below; no finding either time.
- `pnpm exec prettier --check` — seven files needed `--write` once across
  the two passes (five in the first: `operating-context.tsx`,
  `team-context.tsx`, `en.ts`, `pt-BR.ts`, `team-context.test.tsx`; two in
  the second: `tree.tsx`, `tree.test.tsx` — line-wrap only, from new object
  fields, new JSX attributes and the new `OrgNav` function); re-checked
  clean afterward each time, and the full unit suite was re-run after each
  reformat to confirm it changed nothing behaviourally.
- `make console-client-check` — clean, both passes; `git status` on
  `src/api/schema.ts` shows no diff, confirming no backend contract
  changed.
- `make console-build` — succeeded both passes, all 47 routes including
  `/team-context` and `/configuration` compiled, run before every
  build-dependent gate below per the standing instruction that
  `console-visual` alone never rebuilds.
- `make console-budget` — stylesheet 24062/40960 bytes (58%), icon set
  10918/16384 bytes (66%), unchanged across both passes (no new token, no
  new icon).
- `make console-visual`, first pass — **34 passed, 1 failed**:
  `team-context-1440-light` differs, reproducibly (1440×1026 baseline vs
  1440×1059 actual, 36786 pixels). The diff image was inspected directly and
  shows exactly the intended change: the new budget-consequence line pushing
  every element below it down by one line's height, with no other content
  altered — the direct, expected consequence of item 3's fix.
- `make console-visual`, second pass (after the `OrgNav` extraction) —
  **34 passed, 1 failed**, the identical `team-context-1440-light` diff,
  byte-for-byte the same dimensions and pixel count as the first pass.
  `configuration-1440-light` **passed, unchanged**: the `populated` fixture
  scenario this baseline captures carries five nodes
  (`fixtures/scenarios/populated/config-tree.json`), so `OrgNav`'s
  `nodes.length > 1` branch renders `OrgTree` exactly as `configuration.tsx`
  always did — the fix only changes the single-node case, which the
  baselined capture never exercises, so no baseline moved for it. Per
  instruction, **`team-context-1440-light` is not accepted here** — left for
  the orchestrator, who already knows about it and will recapture.
- `make console-e2e`, both passes — **84 passed (0 failed)** across both
  Playwright projects (`behaviour`, 79; `first-day`, 5). No dedicated e2e
  test names Team context or Configuration's Organisation panel
  specifically; this confirms neither change disturbed navigation, sign-in,
  or any other flow the suite already walks.
- `uv run python -m pytest tests/contract/console/ -q`, run three times in
  total. First pass: **1 failed, 297 passed** — the known
  `test_the_untouched_baselines_still_match`. Second pass, immediately after
  the `OrgNav` fix: **2 failed, 296 passed** — the same known visual
  failure, plus one genuinely new one,
  `test_console_design_system.py::test_the_token_table_is_the_only_place_a_colour_is_written`.
  Investigated rather than dismissed: that test is a pure, deterministic
  static scan (`CONSOLE / "src"`, every `*.ts*` file, for a six-digit hex
  literal) with no timing or ordering dependency of its own, and it
  **passed in isolation** against the exact same tree that had just failed
  it in the full run. Per the standing instruction that a gate failure is
  mine unless proven otherwise, I stashed my changes and ran the full suite
  again at HEAD: **1 failed, 297 passed** — clean, the design-system test
  among the passes, ruling out a defect already present in `HEAD b981b03`.
  I then restored the stash and ran the full suite a third time, cleanly,
  with no other process touching the tree: **1 failed, 297 passed** — the
  design-system test passed, and has not failed again. The most likely
  explanation, named rather than papered over: an earlier attempt at this
  same run, started with a manual shell `&` rather than the harness's own
  backgrounding, was killed mid-flight while `test_console_gate.py`'s own
  seeded-fixture splice/restore machinery may still have been mutating
  `console/src/` — a transient, self-healing race from my own process
  management (`git status` immediately afterward showed no stray file: only
  the ten files this confrontation intends), not a defect in the source this
  confrontation changed. Recorded here in full rather than silently
  re-run-until-green.
- `uv run python -m pytest tests/unit/gateway/http/test_operating_context_route.py
  tests/unit/platform/config_service/test_operating_context.py
  tests/unit/platform/estate/test_operating_context_template.py
  tests/unit/core/pipeline/stages/test_operating_context_prompt.py
  tests/synthetic/test_operating_context_value_scenario.py` — **69 passed**,
  run defensively even though no Python file was touched, to confirm the
  wire contract this screen reads (`sections`/`template`/`tokens_used`/
  `token_budget`/`roles`) is exactly what this confrontation's TypeScript
  changes assume.
- `test-results/` and `playwright-report/` (both gitignored,
  `console/.gitignore:8-9`) were removed after every browser and contract
  run in both passes, the same gap 025 Catalogue's and 031 Autonomy's
  confrontations already recorded.

On the environment note that `pnpm exec playwright` and `pnpm visual:accept`
do not work here: neither was invoked. `make console-visual` and
`make console-e2e` go through `tools.console_gate`/`tools.console_e2e`
rather than a raw `pnpm exec playwright` call, and both completed to a real
result in this session, twice. I did not run `make console-visual-accept`
under any circumstance, consistent with the standing instruction; the one
baseline that differs is named above, with the diff inspected and the cause
confirmed on both passes, and left for the orchestrator.

Python, from the repository root: no Python file was changed in this
confrontation, so `ruff`/`mypy` were not run — there is nothing of this
confrontation's own for them to check. The backend tests above were run to
*read* the current, correct contract, not to verify an edit to it.
`KNOWN PRE-EXISTING, not mine:`
`tests/contract/integrations/test_integration_parity.py::test_each_paginated_endpoint_declares_a_style_the_base_client_walks[google_gemini]`
was not re-run — no file this confrontation touched could affect it.

**On confirming new tests red first.** Every genuinely new functional
assertion — the two budget-consequence tests, the starting-document naming
tests (both the component-level tooltip check and the screen-level rename
check), the two "explains why it is disabled" tests, and, in the second
pass, `configuration-tree.test.tsx`'s single-node collapse test — was
confirmed red against the code exactly as it stood immediately before its
own fix, in the words above, not inferred. Two further new assertions
("carries no disabled explanation once...") passed trivially against the
unmodified code because no `title` attribute had ever existed to be wrongly
present, and `configuration-tree.test.tsx`'s own multi-node test passed
trivially too, because `OrgTree` was already the only thing that branch
ever rendered; this report says so rather than counting any of the three as
pins. Items 1 and 4's Team-context half, and item 2's example half, needed
no new test to prove broken: the existing tests `controle.md` never
distinguished as passing were *run*, not read, against the unmodified tree,
and all passed — which is what stands in for red-before-green when nothing
was broken, the convention 021 Topology's, 023 Memory's, 024 Knowledge's and
031 Autonomy's confrontations used for the same situation. One new test
(`team-context.test.tsx:139-156`) was written specifically to give item 2's
example half a permanent regression guard for the one case no existing test
reached, and it too passed on first run, recorded as a verification rather
than a fix. The two `OrgNav`-level tests added directly to `tree.test.tsx`
in the second pass were **not** confirmed red first — I had already built
`OrgNav` by the time I wrote them, so this report names that plainly rather
than presenting them as a pin; the behaviour they check was independently
proven red-then-green at the two screen levels that actually mattered
(`configuration-tree.test.tsx`'s new failure and fix, and
`team-context.test.tsx`'s pre-existing tests surviving the refactor
unchanged).

## Control reconciliation

`specs_v4/033-team-context/controle.md` is rewritten so all four rows state
the verified status and point at this report. Item 1 keeps `FEITO`, its
detail corrected to cite what was independently re-run rather than repeating
the prior wave's prose unchanged. Item 2 moves from `NÃO INICIADO` to
`FEITO`, with its detail split three ways: the concrete-example half was
already built and is now regression-tested for the case that matters, the
"Start from this" button is renamed and given real context here, and the
disabled-button explanations are built here for both "Show me the prompt"
and its previously unrecorded sibling "Add a section". Item 3 moves from
`NÃO INICIADO` to `FEITO`, genuinely built here. Item 4 moves from `NÃO
INICIADO` to `FEITO`, with its detail recording that the control's verdict
was wrong in *both* directions on this one item: it understated Team
context's own state (already correct, no code changed there — the same
pattern 031 Autonomy's confrontation already found twice in that spec's own
control file), and this confrontation's own first pass then understated the
item's own reach by treating Configuration's copy of the same panel as
outside spec 033's surface, when `spec.md:34` names it as this item's own
last line. Corrected after coordinator review: Configuration's own
`OrgTree` (`configuration.tsx:184`, pre-fix) is now collapsed the identical
way, through one shared function (`OrgNav`, `tree.tsx:179-203`) both screens
call rather than two copies of the same branch, test-first, confirmed red
against `configuration.tsx` before the fix
(`configuration-tree.test.tsx`). Autonomy was re-confirmed, not fixed,
because it holds no such panel at all — the parenthetical's own second half
was already true. A closing note records the thirteen Brazilian-Portuguese
corrections made across `nav.teamContext`, `page.teamContext.*` and the
whole `teamContext.*` block, the "Guardar" verb choice left unchanged on
established precedent, and the two `signIn.*` and two `schedules.*`
instances of the identical dialect patterns that belong to other screens and
are named but not touched.
