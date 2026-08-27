# 031 Autonomy — implementation confrontation

Date: 2026-08-14.

## Conclusion

`controle.md` drifted in the same direction 020 Resources and 022 Detectors
already found this series prone to — understating finished work — but only for
two of its six rows, not all of them. Items 2 (three panels, one empty
message) and 5 (the relationship with the topbar's kill switch) were both
already fully built, both with dedicated tests in `autonomy.test.tsx` whose own
docstring names the exact bug each closes, and both were marked `NÃO INICIADO`.
Running those tests against the unmodified tree, not just reading the source
that produced them, confirmed all seven of the file's original tests passed
before this confrontation touched anything.

The other four rows were closer to accurate, but item 3 was half right and
half wrong in the same row: the level descriptions the acceptance criterion
asks for ("os três níveis têm descrição legível no ponto de escolha") were
already built — `postures.ts` resolves each of the deployment's levels to a
full sentence, not a slug, and both `AutonomyEditor`'s and `OverrideEditor`'s
`<Select>` controls already read it — but the three-line glossary the problem
statement also asks for, defining what a rule, a bound, and an override
*are*, was genuinely absent from the rendered page. Items 4 and 6 were
genuinely untouched, exactly as marked: revoking an override still required
typing its name from memory with no list of what was active to revoke from,
and the grant form's fields were still raw — no hint on what the name
identifies, no hint that the reason is audited, and a plain "Seconds
(optional)" number field instead of the presets the problem statement names
by their exact values (1h/8h/24h/custom).

Three things were built, test-first, all confirmed red against the code as it
stood immediately before their own fix: the missing glossary (item 3's second
half), a revoke-by-click list replacing the free-text field entirely (item 4),
and duration presets plus explanatory hints on the grant form (item 6). One
attempted fourth change was built, found to violate a genuine, pre-existing,
tested cross-cutting invariant of this console, and reverted rather than kept
or worked around — recorded in full below because reverting quietly would
have been the wrong kind of silence. A cluster of European-Portuguese
spellings reachable from this exact screen — a silent consonant ("Selector"),
a stress-accent divergence ("autónomo" three times), and "registada" against
this catalogue's own more common "registrada" — was found while reading the
screen's own `pt-BR.ts` block for the strings item 4 and 6 needed, and
corrected together with them; a larger, pre-existing instance of the same
"registada" spelling scattered across several *other* screens was found in the
same pass and is named, not touched, because it is not this screen's surface.

All four of `spec.md`'s acceptance criteria hold now, verified against the
rebuilt screen rather than only against the source: no heading is broken and
exactly one panel resolves to the empty state when there is no policy; the
four levels this deployment declares (the acceptance criterion's own "três"
predates the fourth, `act_silently`, which the same mechanism already covers)
read as full sentences at the point of choice; every override this node's
bounds report is listed with a revoke button of its own, with nothing to
type; and the global automation switch's state — who stopped it, when, and a
resume control for whoever may use it — is on this screen, sharing the exact
component the topbar uses rather than a second implementation of it.

## Table

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Heading "Bounds no level overrides" | FEITO (`bf5f055`) | Confirmed accurate. `en.ts:972`/`pt-BR.ts:856`. | DONE (no change) |
| 2. Três painéis, o mesmo vazio | NÃO INICIADO | Wrong — already done. `showBounds` (`autonomy.tsx:228`) hides the bounds panel only when it would repeat the rules panel's own emptiness; the editor panel is never empty and sits directly beneath, seeded with the first rule. Nine existing tests in `autonomy.test.tsx` already pinned this and all passed unmodified. | DONE (no change; one refinement attempted and reverted, see below) |
| 3. Tela não explica o próprio modelo | NÃO INICIADO | Half wrong. `postures.ts` already resolved every level to a full sentence for the `<Select>` controls — the acceptance criterion's own bar. The three-line glossary the problem statement also names (what a rule/bound/override *is*) was genuinely absent. | DONE (glossary added; level descriptions were already correct) |
| 4. Revogar override exige digitar o nome de cabeça | NÃO INICIADO | Confirmed accurate. The revoke section was a bare "Name of the override" text field with no list of what was active. | DONE (fixed — free-text field removed, replaced by a list with one revoke button per active override) |
| 5. Relação com "Stop automation" | NÃO INICIADO | Wrong — already done. The bounds panel's `stopped` row already renders the shell's own `KillSwitchControl` (`autonomy.tsx:442-446`), with the deployment's full sentence (who, when) and a resume control gated on the same permission as the topbar's. Two existing tests already pinned this and both passed unmodified. | DONE (no change) |
| 6. Campos crus do Grant | NÃO INICIADO | Confirmed accurate. Name and Reason had no hint; "Seconds (optional)" was a raw number field. | DONE (fixed — hints on Name and Reason, a Duration preset select replacing the raw field) |

## Evidence and corrections

### 1. The heading

`console/src/i18n/en.ts:972`: `'autonomy.bounds.title': 'Bounds and level overrides'`.
`console/src/i18n/pt-BR.ts:856`: `'autonomy.bounds.title': 'Limites e exceções de nível'`.
Both catalogues were read directly rather than trusted from the control's own
prose, and `autonomy.test.tsx:148,213,269` assert the rendered English heading
in three different scenarios, all of which pass. No change made.

### 2. Three panels, one empty message — already fixed, and one refinement attempted and reverted

`console/src/surfaces/screens/autonomy.tsx:222-231` (unchanged by this
confrontation):

```ts
const rulesEmpty = rules.length === 0;
const boundsEmpty =
  !stopped && freezes.length === 0 && budgets.length === 0 && overrides.length === 0;
const showBounds =
  nodeId !== '' &&
  (policy.status === 'error' ||
    bounds.status === 'error' ||
    !(rulesEmpty && boundsEmpty));
```

The bounds panel drops out of the page only when it would otherwise repeat
the rules panel's own "nothing recorded" — never when it is reporting a
failure of its own. The editor panel (`:360-406`, "Save this posture") is
never in the empty state at all (`state={stateOf(policy, false)}`) and is
seeded with one deployment-wide row (`FIRST_RULE`, `:121-138`) when there is
nothing to edit yet, so a writer always has a working form directly beneath
the one empty panel, never a second or third copy of "no policy recorded."

`console/tests/unit/surfaces/autonomy.test.tsx`'s own docstring
(`:6-24`, unchanged) names exactly this bug and this fix. Run against the
unmodified tree before this confrontation touched anything:
`pnpm exec vitest run tests/unit/surfaces/autonomy.test.tsx` — **7 passed**
(the file's original count), including `'shows exactly one empty panel, with
the first-rule editor directly beneath it'` and `'still shows only one empty
panel, and the bounds panel keeps its real content'`. No gap was found for a
new test to pin.

**What was attempted and reverted.** The problem statement's own suggested
fix goes further than the panel count: "com o formulário de regra aqui, não
um link genérico para a árvore de Configuration" — and the one empty panel
that remains still offers "Look at the configuration," pointing away, as its
action. I built a refinement: for a writer with a real form one panel down,
the empty state's action became "Create the first rule," linking to
`#autonomy-editor-panel`, an anchor on the editor panel already on the same
page — never leaving it. This is a plain `<a href="#...">`
(`console/src/components/state.tsx:85-93` renders `EmptyStateAction`'s `href`
branch as one anchor, confirmed by reading it before relying on it), so
nothing about the mechanism was invented.

Running the full suite exposed why this was wrong to keep:
`tests/unit/surfaces/first-run.test.tsx`'s `'gives every empty state an
action that names a place this console has'` (`:1564-1578`) walks every
screen's rendered `way-back` links and asserts each `href`'s path (split on
`?`, not on `#`) is one of the console's own registered top-level areas.
Confirmed pre-existing and genuine — stashing this session's changes and
re-running against HEAD `cd5a728` passed clean — so the failure was mine to
fix, and I fixed it by reverting rather than by weakening or working around
the guard: it exists specifically to keep an empty state's action from
becoming a made-up, page-local escape hatch, which is exactly the shape of
thing my attempted fix was. The revert removed the conditional action, the
new `autonomy.empty.createFirst` catalogue key (both locales), the anchor
`id`, and the two tests written for it (`autonomy.test.tsx`'s "sends a writer
to the seeded form..." and "still sends a reader who may not write..."), and
restored the unconditional `configurationHref`/`autonomy.empty.action` the
tree already had. **Item 2's acceptance criterion — "um único empty state
quando não há política" — was already, and remains, literally true**: one
panel resolves to the empty state, never three, and a writer has a real form
one scroll away. The specific complaint that the one remaining empty state's
own action still says "Look at the configuration" rather than something that
keeps the reader on the page is real and is not fixed here — this console's
own invariant that an empty-state action names a registered area is a larger
constraint than this one screen, and satisfying both at once would need a
change to that invariant itself, which is out of this confrontation's scope.
Named here rather than silently dropped.

### 3. The screen does not explain its own model — half already done, half built here

**Level descriptions — already correct, confirmed rather than assumed.**
`console/src/surfaces/postures.ts:21-32` resolves each of the deployment's
levels to a full sentence (`autonomy.level.propose_only` etc.,
`en.ts:40-47`: `"Propose only — every action is written up for a person to
approve. Nothing runs without one."`), not a slug. Both `AutonomyEditor`
(`autonomy-editor.tsx:269-283`) and `OverrideEditor`
(`override-editor.tsx:249-260`) already read `levelLabels?.[level] ?? level`
for their `<Select>` options, and `autonomy.tsx:366,532` already passes
`postureLabels(locale, LEVELS)`/`postureLabels(locale, OVERRIDE_LEVELS)`.
This satisfies the acceptance criterion's own words ("descrição legível no
ponto de escolha") as written; no change was needed. (The criterion names
"os três níveis" — the product now declares four, `act_silently` having been
added since; the same mechanism describes all four, so this is not a defect,
only the criterion predating the addition.)

**The glossary — genuinely missing, built here.** Nothing on the rendered
page ever defined "rule," "bound," or "override" before this confrontation —
confirmed by reading the whole file, where the only place those words were
explained was the module's own server-side JSDoc, invisible to an operator.
Test-first: `autonomy.test.tsx`'s new `'defines a rule, a bound and an
override in the reader's own words, near the top of the page'` (added to a
new `describe('the vocabulary this screen assumes an operator already
has', ...)` block) asserts a `data-testid="autonomy-glossary"` element
mentions all three words. Run against the tree before the glossary existed:
**failed**, `Unable to find an element by: [data-testid="autonomy-glossary"]`
— confirmed red. Fixed by `autonomy.tsx:270-280`:

```tsx
<div
  data-testid="autonomy-glossary"
  className="flex flex-col gap-1 text-meta text-muted mb-5 max-w-prose"
>
  <p>{message(locale, 'autonomy.glossary.rule')}</p>
  <p>{message(locale, 'autonomy.glossary.bound')}</p>
  <p>{message(locale, 'autonomy.glossary.override')}</p>
</div>
```

Three lines, one sentence each, placed directly under the page header and
above everything that uses the words without defining them. New catalogue
keys `autonomy.glossary.rule`/`.bound`/`.override` in `en.ts:991-996` and
`pt-BR.ts:865-870`. After the fix: the new test, and the file's full suite,
pass.

### 4. Revoking an override required typing its name from memory

Confirmed before any change: `console/src/surfaces/override-editor.tsx`
(pre-session) rendered exactly one free-text `Input` labelled "Name of the
override" plus a "Revoke" button, with no list of what was actually active on
the node — the literal bug the problem statement quotes.

Fixed by removing the free-text field entirely and replacing it with a list
of every override this node's bounds report, each with its own revoke
button — matching the problem statement's own reasoning that the free field
"só faz sentido quando houver override que a lista não mostre (não há)."
`OverrideEditor` gained an `active: readonly ActiveOverride[]` prop
(`override-editor.tsx:70-79,99`); `autonomy.tsx:202,209-217` resolves it
once, server-side, from the same `bounds.overrides` the read-only row above
already renders, so the two can never format the same override's expiry two
different ways:

```ts
const activeOverrides: readonly ActiveOverride[] = overrides.map((override) => {
  const expires = timestamp(locale, text(override, 'expires_at'), now, zone);
  return {
    name: text(override, 'name'),
    level: text(override, 'level'),
    expiresIso: expires.iso,
    expiresRelative: expires.relative,
    expiresAbsolute: expires.absolute,
    reason: text(override, 'reason'),
    grantedBy: text(override, 'granted_by'),
  };
});
```

`revoke(name)` (`override-editor.tsx:217-232`) now takes the name from the
row that was clicked, never from a field; a successful revoke removes that
row from the list locally (`revokedNames`, `:173,180-182,231`), the same
optimistic-list pattern `grants.tsx`'s `GrantPanel` already uses for role
removal (`gone`/`rows` at `grants.tsx:143,151`), read as the established
idiom rather than invented separately. A node with nothing active shows
`labels.revokeEmpty` (`:322-325`) instead of an empty list. Revoking one
override this node did not itself grant still asks the deployment and
renders its 404 refusal verbatim (`override-editor.tsx:373-377`), unchanged
from before — this component still has no opinion of its own about
inheritance.

`granted_by` needed no backend change: `platform/autonomy/policy.py:152-162`
(`TimedOverride.to_record`) already includes it, and
`platform/autonomy/service.py:259-272` (`AutonomyService.bounds`) already
serialises it through `BoundsView.overrides` — confirmed by reading both
before assuming a route change was needed. `git diff --stat` on
`fixtures/contract/openapi.json` and `console/src/api/schema.ts` is empty:
nothing about the wire shape changed, only what the console already-received
field is used for.

Test-first, `console/tests/unit/surfaces/override-editor.test.tsx`'s
`'revoking an active override'` block (7 tests, replacing the old 5
free-text-based tests): run with the new tests written and `active` accepted
as a prop but the component's markup unchanged, all 7 **failed** — no
`active-override`/`override-revoke-empty` test ids existed, and
`queryByLabelText('Name of the override')` still found the old field.
Confirmed red. After the fix, all 7 pass, including `'revokes only the row
that was clicked, leaving the others listed'` (two overrides, one revoked,
the other still shown by name). `autonomy.tsx`'s own wiring is pinned
separately in `autonomy.test.tsx`'s new `describe('an active override on the
bounds this node holds', ...)` — its first test initially asserted only that
the override's name appeared anywhere on the page, which **passed against
the unmodified screen** because the read-only bounds row already showed that
name; this was a weak pin that would not have caught the actual defect, so it
was corrected to assert the row is specifically inside the revoke section
(`getByTestId('active-override')`), re-confirmed red against the unmodified
screen (`Unable to find an element by: [data-testid="active-override"]`)
before the fix, and passes after it. The second, `'says there is nothing to
revoke for a node with none active'`, also failed against the unmodified
screen (`revoke-override` was unconditionally present) and passes after.

### 5. The relationship with the topbar's "Stop automation" — already fixed

`console/src/surfaces/screens/autonomy.tsx:425-442` (unchanged by this
confrontation): the bounds panel's `stopped` row renders
`text(dataOf(bounds), 'stop_reason')` — which is
`platform/remediation/autonomy/kill_switch.py:55-62`'s `KillSwitchState.describe()`,
already a complete sentence naming who engaged it and when — directly beside
the shell's own `KillSwitchControl` (`console/src/shell/stop.tsx:76-205`),
not a second implementation of the same control. `KillSwitchControl` itself
gates its own presence on `remediation.execute`
(`stop.tsx:38,91`), so a viewer who may not use it sees the sentence with no
button, exactly as the topbar does.

Two tests in `autonomy.test.tsx:275-316` (unchanged) pin both halves —
`'names why, and offers the same control the topbar carries, to a viewer who
may use it'` and `'names why, without offering the control, to a viewer who
may not use it'` — both run against the unmodified tree and passed before
this confrontation touched anything. No change made.

### 6. The grant form's raw fields

Confirmed before any change: `override-editor.tsx` (pre-session) rendered
`Name` and `Reason` with no `description`, and `"Seconds (optional)"` as a
bare `type="number"` input with no unit guidance — exactly the three
complaints the problem statement names.

**Hints on Name and Reason.** `Input` already supports a `description` prop,
rendered under the label and wired to `aria-describedby`
(`console/src/components/form.tsx:89-95,138-176`) — an existing mechanism,
not a new one. Wired at `override-editor.tsx:239-248` (Name) and
`:261-270` (Reason) to two new catalogue keys:
`autonomy.override.grant.nameHelp` ("A short identifier for this override,
unique on this node. It appears in the audit trail and is what a revoke
names.") and `.reasonHelp` ("Recorded in the audit trail beside the
override, for whoever reviews it later.") — `en.ts:954-958`,
`pt-BR.ts:828-833`.

**Duration presets.** The raw seconds field is replaced by a `Select`
(`override-editor.tsx:271-283`) offering the deployment's own default
(unset — `DEFAULT_AUTONOMY_OVERRIDE_SECONDS`, `config/constants/autonomy.py:168`,
2 hours), 1 hour, 8 hours, 24 hours (`MAX_AUTONOMY_OVERRIDE_SECONDS`,
`:169` — the deployment's own ceiling, confirmed by reading the constant
rather than guessing it), and "Custom duration…", which alone reveals the
plain seconds field (`:284-292`):

```ts
const PRESET_SECONDS: Readonly<Record<string, number>> = {
  '1h': 60 * 60,
  '8h': 8 * 60 * 60,
  '24h': 24 * 60 * 60,
};
```

`grant()` (`:184-215`) reads `PRESET_SECONDS[grantDuration]` for a preset,
`customSeconds(grantSeconds)` (`:145-150`) for the custom branch — the exact
same "blank or unparseable omits the field" guard the original free-field
code had, preserved rather than reimplemented, so a deployment default is
still exactly "send nothing." New catalogue keys
`autonomy.override.grant.duration`/`.durationDefault`/`.durationOneHour`/
`.durationEightHours`/`.durationTwentyFourHours`/`.durationCustom`
(`en.ts:960-965`, `pt-BR.ts:834-839`).

Test-first, `override-editor.test.tsx`'s `'granting an override'` block: five
new tests (preset seconds, the 24-hour ceiling, the custom field's
visibility, carrying a custom value, omitting an unparseable one) plus two
for the hints. Run before the implementation existed: all seven **failed** —
no element labelled "Duration" existed, `screen.queryByLabelText('Seconds
(optional)')` was never `null` (the field was always present), and the hint
text was not in the document. Confirmed red. Two pre-existing tests
(`'carries seconds when a duration was given'`, `'omits seconds rather than
sending one it could not parse'`) needed correcting rather than a fresh
write, because their own premise — a directly-visible seconds field — changed
under them; both are now their "custom duration" equivalents, selecting
"Custom duration…" first. After the fix, all pass.

### The Brazilian-Portuguese sweep, on this screen's own catalogue block

Found while reading `pt-BR.ts`'s `autonomy.*` block for the exact lines items
4 and 6 needed — not a repository-wide sweep.

```
pt-BR.ts:793   'autonomy.column.matcher': 'Selector',      → 'Seletor',
pt-BR.ts:811   '...passa a ser autónomo...'                → '...autônomo...'
pt-BR.ts:814   'autonomy.editor.newlyAutonomous': 'Passam a autónomas' → 'autônomas'
pt-BR.ts:815   'autonomy.editor.nothingChanges': '...mais autónomo.'  → '...autônomo.'
pt-BR.ts:861   'autonomy.empty.heading': 'Nenhuma política registada' → 'registrada'
pt-BR.ts:863   'autonomy.empty.body': 'Sem regra registada...'        → 'registrada'
```

`Selector`/`Seletor` is the same silent-consonant pattern 022 Detectors
already fixed for `Objectivo`/`Activar`; confirmed unique to this screen (no
other `Selector` in the catalogue). `autónomo`/`autônomo` is the
acute/circumflex stress-mark divergence (`sinónimo`/`sinônimo`,
`fenómeno`/`fenômeno` are the same class); all three instances in this
catalogue were the European spelling, none the Brazilian one, and all three
are reachable — two from `AutonomyEditor`'s preview summary, rendered
whenever a preview or a nothing-changed answer comes back.
`registada`/`registrada`: reachable directly from this screen's own empty
state, the state the file's own docstring calls out by name.

Two related instances were traced and deliberately left alone:
`autonomy.editor.save`/`.saving`/`.saved`'s "Guardar"/"Guardando"/"Guardado"
is a lexical choice valid in both dialects — the same judgement 022
Detectors' confrontation already recorded for the identical word, not a
silent-consonant or verb-form defect — and is unchanged.
`autonomy.preview.lead`'s "histórico registado" (`pt-BR.ts:858`) carries the
same defect but `autonomy.preview.*` is declared in both catalogues and
referenced nowhere in `console/src` or `console/tests` — confirmed by a
repository-wide search — the same "unreachable, not a defect requiring
action" shape 023 Memory and 024 Knowledge both found for their own screens'
dead catalogue entries. Not touched.

**A larger, pre-existing instance of the same "registada" spelling, found
and not fixed:** a repository-wide search of `pt-BR.ts` for
`registad(a|o|as|os)` found thirteen more instances outside the autonomy
block — `surface.none`, three in `runs.*`, two in `incident.*`,
`memory.strategies.empty.body`, `topology.empty.heading`, `audit.empty.heading`,
`agent.bridged.empty.heading` (this last one already the Brazilian
`registrado`, and `agent.replay.empty.heading` too) — spanning at least six
other screens. This is a genuine, console-wide inconsistency, but it belongs
to whichever confrontation next reaches Topology, Runs, Incidents, Memory,
Audit, or Agent; fixing it here would be well outside spec 031's own surface.
Named so it is not rediscovered from nothing.

### Traced and confirmed not applicable: `platform/guardian/resolution.py`

Named as a likely starting point. Read via `codegraph_explore`'s blast-radius
and call-graph output: it resolves the *shipped detector catalogue*
(`ShippedDetector` → `DetectorDeclaration`), exposed only at
`GET /v1/config/{node_id}/guardian` — a route this screen's data flow never
touches. The actual backend for everything this screen reads and writes is
`platform/autonomy/` (`service.py`, `policy.py`, `resolution.py`,
`decision.py`, `bounds.py`), confirmed by tracing every one of the six
problems to its actual source. This matches 022 Detectors' own finding that
the guardian package is a second, unrelated resolution pipeline; nothing
here needed touching.

## Verification

Console, from `console/`:

- `pnpm exec vitest run tests/unit/surfaces/autonomy.test.tsx
  tests/unit/surfaces/autonomy-editor.test.tsx
  tests/unit/surfaces/override-editor.test.tsx` — run **before** any change:
  **33 passed (33)**, confirming items 1, 2, and 5 rather than assuming them
  (`autonomy.test.tsx`'s 7, `autonomy-editor.test.tsx`'s unrelated 12,
  `override-editor.test.tsx`'s original 14). After writing the new/changed
  tests for items 3, 4, and 6, **before** their implementation, run over just
  the two files those items touch: `pnpm exec vitest run
  tests/unit/surfaces/override-editor.test.tsx
  tests/unit/surfaces/autonomy.test.tsx` — **17 failed | 16 passed (33)**,
  confirmed red for the reasons named per item above
  (`override-editor.test.tsx`: 7 passed unchanged, 14 new all failed;
  `autonomy.test.tsx`: 9 passed — 7 unchanged plus 2 not-yet-red, including
  the weak wiring pin — and 3 failed). That weak pin was then strengthened
  and re-confirmed red on its own, as described in item 4's evidence.
  `autonomy-editor.test.tsx` was untouched throughout and not re-run at this
  step. After every fix, all three files together: **43 passed (43)** — 21 in
  `override-editor.test.tsx`, 10 in `autonomy.test.tsx` (7 original plus 3
  net new, the CTA experiment's own 2 tests having been removed with it), 12
  unchanged in `autonomy-editor.test.tsx`.
- `pnpm exec vitest run` (full unit suite) — baseline at HEAD `cd5a728`
  (stashed and re-run): **1981 passed (121 files)**. After every change:
  **1991 passed (121 files)** — net +10, matching 7→10 tests in
  `autonomy.test.tsx` and 14→21 in `override-editor.test.tsx` (no other file
  was touched). One benign
  jsdom console line ("Not implemented: navigation to another Document") is
  the same pre-existing test-environment noise every prior confrontation in
  this series recorded, not a failure.
- `pnpm exec tsc --noEmit` — clean, no output.
- `pnpm exec eslint` on every changed file — one real finding during the
  work: three `@typescript-eslint/no-non-null-assertion` errors in a test
  using `array[0]!`; corrected to a named single-fixture constant and a
  `within(row)` scoped query instead of indexing, re-linted clean.
- `pnpm exec prettier --check` — three files needed `--write` once
  (`override-editor.tsx`, `autonomy.tsx`, `override-editor.test.tsx`); after
  reformatting, `--check` passed clean on all six changed files, and the full
  suite was re-run to confirm the reformat changed nothing behaviourally
  (still 1991 passed).
- `make console-budget` — stylesheet 24062/40960 bytes (58%), icon set
  10918/16384 bytes (66%), both within budget and effectively unchanged (no
  new icon, no off-scale utility).
- `make console-client-check` — clean; `git diff --stat` on
  `fixtures/contract/openapi.json` and `console/src/api/schema.ts` is empty,
  confirming no backend contract changed.
- `make console-build` then `make console-visual` — run **twice**, once
  after the main implementation and once more after a docstring-only edit
  (no behavioural change, confirmed by re-running the unit suite in between).
  Both times: **34 passed, 1 failed** — `autonomy-1440-light`, reproducibly
  (identical 58544-pixel diff both runs). The diff image was inspected
  directly and shows exactly the intended change: the three-line glossary
  under the header, the level `<Select>`s reading full sentences, the Name
  and Reason fields' hints, the Duration select defaulted to "Default (2
  hours)," and "No override is active on this node right now" in place of
  the old free-text field (the `populated` fixture scenario carries no
  active override on any node, confirmed by reading
  `fixtures/scenarios/populated/autonomy-bounds.json`, so the empty-list
  message is what the baseline should show going forward). Per instruction,
  **this baseline is not accepted here** — left for the orchestrator to
  review and recapture.
- `make console-e2e` — run in full: **84 passed (0 failed)** across both
  Playwright projects this target drives (`behaviour`, 79 tests against
  `tests/e2e/`; `first-day`, 5 tests). Not skipped: this environment has the
  pinned browser toolchain available, confirmed by `make console-visual`
  succeeding first. The autonomy-adjacent network traffic captured in the
  run (`/v1/autonomy/kill-switch`, `/v1/autonomy/policy/{node}`,
  `/v1/autonomy/policy/{node}/outlook`, `/v1/autonomy/policy/{node}/preview`)
  confirms the kill-switch banner and the agent screen's autonomy outlook tab
  — both adjacent to what changed here — are unaffected.
- `test-results/` and `playwright-report/` (both gitignored,
  `console/.gitignore:8-9`) were removed after each browser run, so no stray
  artefact is left for the next `tests/architecture/` run to trip on, the
  same gap 025 Catalogue's confrontation already recorded for `specs_v4/`.

Python, from the repository root:

- `uv run python -m pytest tests/contract/console/test_console_shell.py` —
  **35 passed.** The only Python test file referencing `autonomy` or
  `override` in `tests/contract/console/`; it holds the route/permission
  table, unrelated to anything changed here.
- No other Python gate was run: no Python file was touched. `granted_by`
  (`platform/autonomy/policy.py:160`,
  `platform/autonomy/service.py:268`) was read to confirm it already reaches
  the console; nothing there needed a change.
- `KNOWN PRE-EXISTING, not mine:`
  `tests/contract/integrations/test_integration_parity.py::test_each_paginated_endpoint_declares_a_style_the_base_client_walks[google_gemini]`
  was not re-run — no Python file this confrontation could affect it was
  touched, and the task's own briefing already names it pre-existing.

**On confirming new tests red first.** Every genuinely new assertion for
items 3, 4, and 6 was confirmed red against the code as it stood immediately
before its own fix, and this report names the one exception explicitly
rather than presenting it as a pin: item 4's first wiring test initially
passed against the unmodified screen (a false positive, described above),
was recognised as too weak, strengthened, and re-confirmed red before being
counted. Items 1, 2, and 5 needed no new test: the existing tests
`controle.md` already implicitly credited were *run*, not read, against the
unmodified tree, and all passed — which is what stands in for red-before-green
here, per the convention 021 Topology's and 023 Memory's confrontations used
when they found nothing to fix. The one change built and then reverted
(item 2's empty-state action) is reported as attempted-and-reverted, in those
words, not folded silently into "no change."

## Control reconciliation

`specs_v4/031-autonomy/controle.md` is rewritten so every row states the
verified status and points at this report. Items 2 and 5 move from `NÃO
INICIADO` to `FEITO`, the control's own claim having been wrong in the
understating direction on both — no code changed for either, only the
verdict. Item 3 moves to `FEITO`, with its detail split into what was already
built (the level descriptions) and what this session added (the glossary).
Items 4 and 6 move from `NÃO INICIADO` to `FEITO`, both genuinely built
here. A closing note records the six Brazilian-Portuguese corrections made
in this screen's own catalogue block, the two deliberately left alone
("Guardar," the unreachable `autonomy.preview.*` block), the larger
pre-existing "registada" pattern spanning six other screens that is named but
not fixed, the `platform/guardian/resolution.py` trace that confirmed it is
not this screen's backend, and the attempted-and-reverted empty-state action
change, so none of them is rediscovered from nothing next time this screen —
or this control file — is touched.
