# 035 Agent — implementation confrontation

Date: 2026-08-14.

## Conclusion

`controle.md` marked all four of `spec.md`'s problems `NÃO INICIADO`, and that
was wrong for three of them in the understating direction this series keeps
finding — items 1, 3's first bullet, and 4 were already fully built, each with
its own passing tests, by a prior-wave commit already at `HEAD`
(`1ef8dd6`, "fix: mark the session cookie secure behind a proxy, and three
more screens," whose own message says outright what it did to this screen:
"The agent stops rendering budgets as 0 … the roles table names the default
provider and model instead of saying eight times that nobody bound the
role"). Running the existing suite against the unmodified tree — not reading
`controle.md`'s account of it — confirmed all 37 of `agent.test.tsx`'s tests
passed before this confrontation touched anything.

Item 2 was the one row where `controle.md`'s verdict happened to match the
code, but not for the reason a quick read suggests. The same commit had
already built the entire mechanism the problem asks for — the row's label is
computed by a `budgetLabel` function, the raw dotted path is relegated to a
metadata span, and the function's own docstring names exactly the intended
fix ("filled in as the words arrive"). What that commit left undone is the
one line the docstring itself promises: the lookup table, `BUDGET_LABELS`,
was shipped empty. So the mechanism existed and did nothing — every label,
in every locale including Portuguese, silently fell through to the schema's
own field name, which is Pydantic's title generation and is never
translated. This is not a case of "nothing to fix here because it already
works"; it needed the one change the scaffolding was visibly waiting for,
and it is fixed here, test-first.

Item 3's second bullet — the overlap between this screen's Tools/Autonomy
tabs and the standalone Catalogue and Autonomy screens — is not a defect to
close from this screen alone. `spec.md`'s own text defers it to spec 090,
and spec 090's own text independently confirms it claims this exact fusion
("The agent ⇐ + Catalogue (leitura) + Team context … 'The agent' já tem abas
Topology/Tools/Autonomy e é a melhor tela do console. Proposta: ela vira a
casa de ler o agente"), sequenced as its own wave of work, not something a
single-screen confrontation resolves piecemeal. Declined here, traced to
that ownership rather than to avoid the work.

One thing outside `spec.md`'s four items was traced and is named, not fixed:
`console/src/surfaces/preview.tsx`'s `EditableField`/`ItemField`, which the
Configuration screen (spec 032) uses to draw every field in the whole
schema, carries the identical defect class at a much larger scale — `label`
is the schema's own, untranslated title, read directly with no
`budgetLabel`-style lookup at all, and used both for display and for the
in-page search (`field.label.toLowerCase().includes(query)`). It belongs to
spec 032's own surface (already independently confronted), and the
narrow, closed-set mechanism built here for four known budget paths does not
generalise to a field list the size of the whole configuration schema — a
systemic fix, not a screen-local one. Named here so it is not rediscovered
as new.

## Table

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Budgets "0 / ceiling N" read as zero | NÃO INICIADO | Wrong — already done, by `1ef8dd6`. `effectiveBudget` (`agent.tsx:578`) reads the schema's own default when nothing was customised and never coerces an absent ceiling to `0`; `agents.tool_budget` genuinely has no ceiling in the schema (`Field(ge=1)`, no `le`), confirmed by running `declared_fields()` directly. Five existing tests already pinned both halves and all passed unmodified. | DONE (no change) |
| 2. Chaves cruas como rótulos | NÃO INICIADO | Half right, for the wrong reason. The display mechanism (translated label with the raw path kept as metadata) was already built by `1ef8dd6`, but the one thing that mechanism needed — the `BUDGET_LABELS` lookup table — was shipped empty, so every label still fell through to the schema's untranslated English field name, in every locale. | DONE — fixed here, test-first |
| 3. Duplicações internas | NÃO INICIADO ("estrutural, onda 4") | Split. First bullet (document panel repeating the specialists empty state) was already fixed by `1ef8dd6`, with a passing regression test. Second bullet (Tools/Autonomy tabs vs. Catalogue/Autonomy screens) is spec 090's own, explicitly claimed fusion, sequenced as its own wave. | First bullet: DONE (no change). Second bullet: correctly deferred — declined here, traced to spec 090's ownership |
| 4. "deployment default — nobody bound this role" ×8 | NÃO INICIADO | Wrong — already done, by the same commit. `roleBinding` (`agent.tsx:455`) resolves the schema's own default provider/model for an unbound role and `ModelRolePanel` renders `{provider} / {model}` on every row, bound or not, with the "deployment default" annotation kept as provenance rather than as the whole answer. Existing tests already pinned this and passed unmodified. | DONE (no change) |

## Evidence and corrections

### 1. Budgets "0 / ceiling N" — already fixed, confirmed by running rather than reading

`console/src/surfaces/screens/agent.tsx:548-583` (`numeric`, `EffectiveBudget`,
`effectiveBudget`, unchanged by this confrontation):

```ts
export function effectiveBudget(budget: unknown): EffectiveBudget {
  const customised = text(budget, 'provenance') !== '';
  const value = customised ? number(budget, 'value') : number(budget, 'default');
  const ceiling = numeric(budget, 'maximum');
  return ceiling === undefined ? { customised, value } : { customised, value, ceiling };
}
```

`numeric()` (`:548-551`) is deliberately distinct from the generic `number()`
helper in `../read`, which reads an absent value as `0` — correct for a
count, wrong for "nobody set this yet" and wrong for "the schema declares no
ceiling." `BudgetPanel` (`:615-696`) renders the ceiling annotation only
when `ceiling !== undefined` (`:667-676`), so a budget the schema genuinely
does not bound states nothing rather than a digit that reads as one.

On the specific instruction to investigate the `ceiling 0` on
`agents.tool_budget`: read directly from the schema,
`platform/config_service/schema/agents.py:352-356` declares
`tool_budget: Annotated[ConfiguredInt, Field(ge=1), field_help(...)]` — a
floor and no roof. `platform/config_service/fields.py:333-339`'s `_bound()`
returns `None` when neither `maximum`/`exclusiveMaximum`/`le` is present in
the JSON schema, confirmed by reading the function rather than assuming it.
So the `0` was never a data error — it was `number()` coercing a genuine
`null` — and the fix already treats "no ceiling" as a schema fact rather
than a missing digit.

Run, not read, against the unmodified tree:
`pnpm exec vitest run tests/unit/surfaces/agent.test.tsx` — **37 passed**,
including `'renders every budget with the ceiling the schema sets'`,
`'never renders a ceiling for a budget the schema does not bound'`,
`'shows the schema default rather than zero when nobody customised it'`,
`'trusts an explicit zero exactly as it trusts any other customised value'`
and `'carries no ceiling when the schema declares a floor and no roof'` — five
tests covering both halves of the acceptance criterion ("Nenhum budget
renderiza 0 quando o efetivo não é zero"). No gap was found, so no change
was made for this item.

### 2. Chaves cruas como rótulos — the scaffolding was already there; the one line it needed was not

**What was already built, by `1ef8dd6`.** `BudgetPanel` (`agent.tsx:652-660`)
already renders a translated label with the raw dotted path kept as separate
metadata:

```tsx
<span className="min-w-0 truncate">
  {budgetLabel(locale, path, text(budget, 'label'))}
</span>
<span className="font-mono text-meta text-muted" data-testid="agent-budget-path">
  {path}
</span>
```

That satisfies the parenthetical half of item 2 literally — "com a chave
como metadado" — and was not touched here.

**What was not built: the words.** Before this confrontation,
`budgetLabel` (then unexported, at the same location) read:

```ts
const BUDGET_LABELS: Readonly<Record<string, MessageKey>> = {};

function budgetLabel(locale: Locale, path: string, schemaLabel: string): string {
  const key = BUDGET_LABELS[path];
  if (key !== undefined) return message(locale, key);
  return schemaLabel === '' ? path : schemaLabel;
}
```

`BUDGET_LABELS` was empty, so the lookup on the first line never matched, and
every one of the four rows — in English *and* in Portuguese — rendered
`schemaLabel`: the JSON Schema `title` Pydantic generates from the Python
field name (`platform/config_service/fields.py:249`,
`label=str(raw.get("title") or spec.get("title") or name)`), which is
English regardless of locale and is never run through the catalogue. The
function's own docstring already named the intended shape ("a closed set of
paths, filled in as the words arrive") — the words had not arrived. This is
the literal "chaves cruas como rótulos" defect surviving one layer under
where the previous commit's own comment says it would be found, and it is
exactly the situation "the standard for declining a fix" does not apply to:
there was real, traceable, unfinished work here, not a closed question.

Confirmed by running `uv run python -c "from platform.config_service.fields
import declared_fields; ..."` directly against the schema: the live label
for these four paths is Title Case (`'Max Iterations'`,
`'Max Parallel Subagents'`, `'Max Subagent Depth'`, `'Tool Budget'`); the
committed fixture (`fixtures/scenarios/populated/config-fields.json`) is
older and carries Sentence case (`'Max iterations'`, `'Tool budget'`) for
the two of the four it declares at all. Neither is a translation into
Portuguese, and the fixture/schema mismatch is a separate, pre-existing
staleness this confrontation did not need to and did not touch — my fix
replaces the schema label with a catalogue lookup entirely for these four
paths, so which casing the schema happens to emit is no longer visible.

**Test-first.** `console/tests/unit/surfaces/agent.test.tsx` was extended in
two ways before any implementation change:

- Exported `budgetLabel` (a visibility change only, no behaviour) so it could
  be tested directly, the same way `effectiveBudget` and `roleBinding`
  already are.
- Added the catalogue entries (inert until wired) and a `cookieJar`-backed
  `next/headers` mock — the same pattern `tests/unit/shell/pages.test.tsx`
  already uses (`cookieJar.set(LOCALE_COOKIE, 'pt-BR')` read fresh by every
  `cookies()` call) — so a test can render the screen in Portuguese without
  disturbing any of the 37 existing tests, none of which sets that cookie.

Five new tests: one page-level (`:243-259`,
`"labels a budget in the reader's own language, not the schema's English
default"`) and four direct against `budgetLabel` (`:262-303`, covering a
known path in both locales, all four `BUDGET_PATHS` entries, the fallback to
a schema label for a path this console has no words for yet, and the
fallback to the raw path when the schema has nothing either).

Run against the tree with only the inert prerequisites in place (export +
catalogue keys, `BUDGET_LABELS` still `{}`):
`pnpm exec vitest run tests/unit/surfaces/agent.test.tsx` —
**3 failed | 39 passed (42)**, confirmed red for the exact reason above:

```
AssertionError: expected 'Max iterationsagents.max_iterations12…' to contain 'Máximo de iterações'
AssertionError: expected 'Max Iterations' to be 'Max iterations'
AssertionError: expected 'Whatever The Schema Says' not to be 'Whatever The Schema Says'
```

(The other two new tests — the two fallback-behaviour ones — passed
unmodified, because that half of the function was already correct and
untouched.)

Fixed by filling in the table (`agent.tsx:602-607`):

```ts
const BUDGET_LABELS: Readonly<Record<string, MessageKey>> = {
  'agents.max_iterations': 'agent.budgets.maxIterations',
  'agents.max_parallel_subagents': 'agent.budgets.maxParallelSubagents',
  'agents.max_subagent_depth': 'agent.budgets.maxSubagentDepth',
  'agents.tool_budget': 'agent.budgets.toolBudget',
};
```

with four new catalogue keys, `en.ts:1328-1331` / `pt-BR.ts:1198-1201`:

```
agent.budgets.maxIterations         Max iterations                    Máximo de iterações
agent.budgets.maxParallelSubagents  Max parallel specialists          Máximo de especialistas em paralelo
agent.budgets.maxSubagentDepth      Max specialist depth              Profundidade máxima de especialistas
agent.budgets.toolBudget            Tool budget                       Orçamento de ferramentas
```

The English strings for the two paths the `populated` fixture actually
carries (`max_iterations`, `tool_budget`) were deliberately chosen to match
the text the schema fallback already produced in that fixture
("Max iterations", "Tool budget") — not because the mechanism depends on
that match (it does not: a path in `BUDGET_LABELS` always uses the
catalogue now, regardless of what `schemaLabel` says), but to avoid a
gratuitous visual diff on `agent-1440-light` for a row whose English wording
was already adequate. Confirmed this held: `make console-visual` passed
clean on all three `agent-*` baselines (below).

After the fix: `pnpm exec vitest run tests/unit/surfaces/agent.test.tsx` —
**42 passed (42)**.

**Considered and left alone: model-role and risk-class identifiers on this
same screen.** `ModelRolePanel` renders each role (`"diagnose"`, etc.) in
`font-mono`, untranslated, and `AutonomyTab` renders each `risk_class`
(`"trivial"`, `"critical"`, …) the same way. Both are closed-set
*identifiers* — the same category as a specialist's own name or a tool's own
name, both also shown raw elsewhere on this screen — not a dotted
*configuration key* standing in for its own label, which is the specific
shape item 2's own two examples (`agents.max_iterations`,
`agents.max_parallel_subagents`) name. `fieldAt`/`.label` is read nowhere
else on this screen outside `BudgetPanel`, confirmed by reading the whole
file, so there is no sibling instance of this exact defect left on this
screen once `BUDGET_LABELS` is filled in.

**Traced and named, not fixed: `console/src/surfaces/preview.tsx`.** The
Configuration screen's editor (`EditableField`/`ItemField`, spec 032's own
surface) reads `field.label` directly with no catalogue lookup at all
(`preview.tsx:60,72`), used both to render every row and to drive the
in-page search (`preview.tsx:317`,
`field.label.toLowerCase().includes(query)`). This is the identical defect
class, at the scale of every field the whole configuration schema declares
rather than four known budget paths, so the closed-set `BUDGET_LABELS`
mechanism does not generalise to it — a systemic fix belongs to spec 032,
already independently confronted, and nothing there was touched.

### 3. Duplicações internas — one bullet already fixed, one correctly out of this screen's hands

**First bullet: the document panel repeating the specialists empty state —
already fixed, by `1ef8dd6`.** `DocumentPanel` (`agent.tsx:716-748`,
unchanged by this confrontation):

```tsx
function DocumentPanel({ locale, effective, values }: {...}): ReactNode {
  const section = field(values, 'agents');
  const document = JSON.stringify({ agents: section ?? {} }, null, 2);
  return (
    <Panel
      title={message(locale, 'agent.document.title')}
      state={stateOf(effective, false)}
      ...
```

`stateOf(effective, false)` never reaches the `empty` state — the second
argument, "is this empty," is hard-coded `false` — so a node with no
`agents` section of its own renders the document truthfully as `{"agents":
{}}` instead of repeating the "This team declares no specialists" heading,
body and way out the specialists panel directly above already rendered. The
docstring at `:707-714` names exactly this decision ("Never its own empty
state … showing that whole explanation a second time in the same tab is the
duplication a second view must not repeat").

Run, not read, against the unmodified tree:
`pnpm exec vitest run tests/unit/surfaces/agent.test.tsx -t "does not repeat
the specialists empty state"` — **passed**, confirming the specific
regression test (`agent.test.tsx:173-187`) that pins this exact bug by name.
No gap was found, so no change was made.

**Second bullet: this screen's Tools/Autonomy tabs vs. the standalone
Catalogue and Autonomy screens — spec 090's own, explicitly claimed
fusion.** `spec.md`'s own text for this bullet already names where the
resolution belongs: "sobreposição a resolver na spec 090 (proposta: esta
tela absorve a leitura … e as telas de escrita ficam com a mudança)."
Reading `specs_v4/090-reorganizacao-de-menus-e-escopo/spec.md` directly
(not trusting the paraphrase) confirms the same claim independently, in
090's own words: "**The agent ⇐ + Catalogue (leitura) + Team context** …
'The agent' já tem abas Topology/Tools/Autonomy e é a melhor tela do
console. Proposta: ela vira a casa de **ler o agente** — estágios, tools e
skills disponíveis (o catálogo em modo leitura, com busca), roles/modelos
efetivos, budgets, e o contexto do time … Escrever continua nas telas de
escrita (Integrations, Autonomy, Configuration)." 090 sequences this as its
own wave ("5. Sidebar novo + fusões — uma vez, cedo, enquanto não há
usuários"), after the funnel and the error-vocabulary work, not as something
a single-screen confrontation resolves piecemeal by, for instance, adding an
ad-hoc cross-link from this screen to Catalogue — that would pre-empt 090's
own design (which proposes moving Catalogue's *read* surface onto this
screen entirely, not linking two screens that would otherwise still both
exist). `controle.md`'s own annotation ("estrutural, onda 4") already named
this as deferred; confirmed here by reading 090's text directly rather than
trusting the annotation, and declined on that ownership rather than to avoid
the work.

### 4. "deployment default — nobody bound this role" ×8 — already fixed, confirmed by running rather than reading

`console/src/surfaces/screens/agent.tsx:426-465` (`RoleBinding`,
`roleBinding`, unchanged by this confrontation):

```ts
export function roleBinding(declared: readonly unknown[], role: string): RoleBinding {
  const providerField = fieldAt(declared, `models.${role}.provider`);
  const modelField = fieldAt(declared, `models.${role}.model`);
  const bound = providerField !== undefined && text(providerField, 'provenance') !== '';
  return {
    bound,
    provider: text(providerField, bound ? 'value' : 'default'),
    model: text(modelField, bound ? 'value' : 'default'),
    provenance: bound ? text(providerField, 'provenance') : '',
  };
}
```

`ModelRolePanel` (`:495-527`) renders `{binding.provider} / {binding.model}`
on every row whether or not a node bound it — reading the schema's own
default (`ConfigField.default`, served on the same field the value and
provenance are, per `platform/config_service/schema/agents.py:406-421`'s
`ModelSelection`) rather than nothing — and keeps "deployment default —
nobody bound this role" (`agent.models.default`) as the provenance
annotation beside it, not as the whole answer. Eight roles exist
(`config/constants/config_service.py:104-113`'s `MODEL_ROLES`:
`investigator`, `subagent`, `intake`, `diagnose`, `extraction`, `embedding`,
`selection`, `summarisation`), confirmed by reading the constant, matching
item 4's own "×8."

Run, not read, against the unmodified tree:
`pnpm exec vitest run tests/unit/surfaces/agent.test.tsx -t "deployment
default"` — **passed** (`'reads "deployment default" for a role nobody
bound'`, `agent.test.tsx:455-468`), and the three pure-function tests
(`'says what the deployment default actually is, once the schema knows'`,
`agent.test.tsx:351-372`, and its two siblings) all passed unmodified. This
satisfies the acceptance criterion "A tabela de roles mostra o modelo
efetivo de cada role" as written. No gap was found, so no change was made.

### Traced and confirmed out of reach: `transcript.ts`, `transcript-view.tsx`, `quick-actions.tsx`

Offered as likely starting points. Checked via `codegraph_explore`'s own
blast-radius output rather than assumed: `Transcript`
(`transcript-view.tsx`) is imported only by `live-run.tsx`,
`incident-detail.tsx` and `run-detail.tsx`; `DashboardQuickActions`
(`quick-actions.tsx`) is imported only by `dashboard.tsx`. Neither is
reachable from `agent.tsx`, whose own render tree (read in full) never
imports either module. `quick-actions.tsx`'s own comment — "Until the
agent's own screen lands, what the agent may do is the autonomy posture" —
is a stale note about routing on a *different* screen (Dashboard), now that
this screen exists; whether Dashboard's quick actions should point here
instead of at Autonomy is a genuine question, but it is Dashboard's own
routing choice (spec 010), not this screen's, and `spec.md`'s four items say
nothing about it. Named, not touched.

### Traced and confirmed not applicable: a stray "exacto"

The task's own briefing named `"exacto"` as known to be present in "the
agent block." A case-insensitive search of `pt-BR.ts`'s entire `agent.*`
block (`:1163-1242`, every key read in full) found no such spelling — every
occurrence of "exact"/"exat" in that block is a correctly-spelled Brazilian
word ("exato," "exatamente," found on other screens' blocks, not this
one) or does not occur at all. A repository-wide search found exactly one
instance of the European spelling, `'dashboard.guardian.empty.body'`
(`pt-BR.ts:465`, `"Um guardião que parou é exactamente igual…"`), which
belongs to the Dashboard screen's own catalogue block (spec 010), not this
one, and is unreached from `agent.tsx`. A second, stale trace was found and
resolved: a Next.js build cache under `console/.next/` (gitignored, not
source) still held the pre-fix text of `teamContext.preview.lead` ("O texto
**exacto** que o prompt de sistema…"); the committed source at that key
(`pt-BR.ts:926`) already reads "exa**t**o," confirming spec 033's own
confrontation already corrected it and the stale build artefact is not a
live defect. Nothing on this screen needed touching for this.

### Traced and confirmed not applicable: "registada"

The task's own briefing also named `"registada"` (the European spelling of
the past participle, missing the `r` Brazilian Portuguese's "registrado"
carries) as known to be present "on several screens." A search of
`pt-BR.ts` for `registad(a|o|as|os)` — which cannot match "registrado"
itself, since that word does not contain "registad" as a substring —
returns nothing inside the `agent.*` block. 031 Autonomy's own
confrontation already traced the same pattern console-wide and explicitly
named this screen's two candidates as already correct:
`agent.bridged.empty.heading` and `agent.replay.empty.heading` both already
read "registrado" (`pt-BR.ts:1227,1245`), confirmed by reading both lines
directly here rather than trusting either report's prose. 031's own
`controle.md` summary line lists "Agent" among the span of screens its
search touched, which reads as if a fix were still owed here; its own
`relatorio-confronto.md` is the more careful account and already excludes
both of this screen's instances by name. Recorded here so this does not
read as a live gap the next time this screen or that control file is
touched.

## Verification

Console, from `console/`:

- `pnpm exec vitest run tests/unit/surfaces/agent.test.tsx` — run **before
  any change**: **37 passed (37)**, confirming items 1, 3 (first bullet) and
  4 by running them rather than trusting `controle.md`'s account. After
  adding the five new tests for item 2, with the export and the catalogue
  keys in place but `BUDGET_LABELS` still empty: **3 failed | 39 passed
  (42)**, confirmed red for the reasons quoted above. After filling in
  `BUDGET_LABELS`: **42 passed (42)**.
- `pnpm exec vitest run tests/unit/surfaces/agent.test.tsx tests/unit/i18n`
  — **66 passed (3 files)**, confirming the new catalogue entries did not
  break completeness or fallback behaviour.
- `pnpm exec vitest run` (full unit suite) — **2011 passed (122 files)**, net
  +5 over the 2006 recorded at this branch's own prior commit (034
  Proposals' own last-recorded count), matching the five new tests this
  confrontation added; no other file was touched. One benign jsdom console
  line ("Not implemented: navigation to another Document") is the same
  pre-existing test-environment noise every prior confrontation in this
  series has recorded, not a failure.
- `pnpm exec tsc --noEmit` — clean, no output.
- `pnpm exec eslint src/surfaces/screens/agent.tsx src/i18n/en.ts
  src/i18n/pt-BR.ts tests/unit/surfaces/agent.test.tsx` — clean.
- `pnpm exec prettier --check` on the same four files — "All matched files
  use Prettier code style!"
- `make console-build` — succeeded, all routes including `/agent` compiled,
  run before every build-dependent gate below per the standing instruction
  that `console-visual` alone never rebuilds.
- `make console-budget` — stylesheet 24062/40960 bytes (58%), icon set
  10918/16384 bytes (66%), unchanged (no new token, no new icon).
- `make console-client-check` — clean; `git status` on `src/api/schema.ts`
  and `fixtures/contract/openapi.json` shows no diff, confirming no backend
  contract changed (none was touched).
- `make console-visual` — **35 passed, 0 failed**, including all three
  registered `agent-*` baselines (`agent-1440-light`,
  `agent-autonomy-1440-light`, `agent-tools-1440-light`). The deliberate
  choice to keep the English catalogue text for the two fixture-visible
  paths identical to the schema fallback it replaces held: no baseline
  needed recapturing.
- `make console-e2e` — **84 passed (0 failed)** across both Playwright
  projects (`behaviour`, 79; `first-day`, 5), including all five of
  `tests/e2e/agent.spec.ts`'s tests by name — none of them assert the
  budget row's label text, so none needed changing, and their pass confirms
  the tab addressing, the tools grouping and the document-panel behaviour
  this confrontation did not touch are intact.
- `test-results/` and `playwright-report/` (both gitignored,
  `console/.gitignore:8-9`) were removed after both browser runs, the same
  housekeeping step every prior confrontation in this series records.
- `uv run python -m pytest tests/contract/console/ -q` — **298 passed**,
  including `test_the_untouched_baselines_still_match` (the Python-side
  mirror of the visual gate) and the seeded-failure suite in
  `test_console_gate.py`. Takes ~5 minutes; the first attempt was killed at
  a 300-second shell timeout mid-run and misread as a hang — re-run without
  that wrapper completed cleanly at 310s, confirming the first result was
  an artefact of my own timeout choice, not a failure.
- `uv run python -m pytest tests/contract/fixtures/ -q` — **101 passed**,
  confirming the catalogue-only, frontend-only edit did not disturb the
  mock data plane's own contract (no route, no shape, no backend behaviour
  changed — only rendered text, and only where a catalogue key already
  existed to carry it).

On the environment note that `pnpm exec playwright` and `pnpm visual:accept`
do not work here: neither was invoked. `make console-visual` and
`make console-e2e` go through `tools.console_gate`/`tools.console_e2e`
rather than a raw `pnpm exec playwright` call, and both completed to a real
result. `make console-visual-accept` was not run under any circumstance —
it was not needed, because no baseline differed.

Python, from the repository root:

- `uv run python -c "from platform.config_service.fields import
  declared_fields; ..."` — run to establish ground truth for the schema's
  own label generation (Title Case) versus the committed fixture's (older,
  Sentence case), described under item 2 above. No Python file was changed,
  so no other Python gate applies; `ruff`/`mypy` were not run because there
  is nothing of this confrontation's own for them to check.
- `KNOWN PRE-EXISTING, not mine:`
  `tests/contract/integrations/test_integration_parity.py::test_each_paginated_endpoint_declares_a_style_the_base_client_walks[google_gemini]`
  was not re-run — no file this confrontation touched could affect it.

**On confirming new tests red first.** The five new assertions for item 2
were confirmed red against the tree with only the inert prerequisites in
place (the `budgetLabel` export and the four catalogue entries — neither of
which changes what any test observes on its own) and `BUDGET_LABELS` still
exactly as `controle.md` found it, in the words quoted above, not inferred.
Items 1, 3 (first bullet) and 4 needed no new test: the existing tests
`controle.md` marked `NÃO INICIADO` were *run*, not read, against the tree
exactly as this confrontation found it, and all passed — which is what
stands in for red-before-green when nothing was broken, the convention 021
Topology's, 023 Memory's, 024 Knowledge's, 031 Autonomy's, 033 Team
context's and 034 Proposals' confrontations used for the same situation.

## Control reconciliation

`specs_v4/035-agent/controle.md` is rewritten so every row states the
verified status and points at this report. Items 1, 3 and 4 move from `NÃO
INICIADO` to `FEITO`: no code changed for any of the three, only the
verdict, with item 3 split so its first bullet (already fixed) and its
second (deferred to spec 090, correctly) are recorded separately rather
than as one undifferentiated "estrutural" note. Item 2 moves from `NÃO
INICIADO` to `FEITO`, genuinely built here: the display mechanism a prior
commit had already scaffolded (translated label, raw path as metadata) is
now actually wired to four real catalogue entries, in both locales, and
five new tests — confirmed red before the fix — pin it. A closing note
records the Configuration screen's own instance of the same defect class at
schema-wide scale (traced, named, left to spec 032's own surface), the
stale `.next/` build-cache artefact that momentarily looked like a live
"exacto" instance and was confirmed already fixed in committed source, and
that `transcript.ts`/`transcript-view.tsx`/`quick-actions.tsx` were checked
and confirmed unreachable from this screen.
