# 022 Detectors — implementation confrontation

Date: 2026-08-13

## Conclusion

The control file was stale in the same direction 020 Resources found it
stale: all three rows read NÃO INICIADO, and reading the current source
proved two of the three items already done, in full, with dedicated
regression tests whose own docstrings quote the exact bug report spec.md
describes. Item 1's empty state no longer sends a two-source-connected
operator back to "Connect a source" — it already checks whether anything is
live and, when nothing is, rewrites the panel's action to "Turn on
continuous observation" and points it at the viewer's own node in
Configuration, exactly the `configurationHref` pattern `autonomy.tsx` and
`agent.tsx` already use for the identical shape of problem elsewhere in this
console. Item 3 needed no code: the title/subtitle problem is the same
"empty table promises answers it cannot give" shape item 1 already closes,
and spec.md's own qualifier — "quando houver detectores, ok" — concedes the
populated case, which this console's shared `AreaHeader`/`EmptyState` split
(title describes the feature, the panel explains an absence) already
satisfies for every one of the nineteen areas in this shell, not only this
one.

**Item 2 took two passes, and the first one was wrong in a way worth stating
plainly.** My first confrontation found the schedule form's card, cron
helper, per-field explanations, table empty-state, and round-trip cron
validation already built and tested, and treated a new post-creation
confirmation — "Schedule created: X. Next run: in 8 days." — as satisfying
"mostra o próximo disparo". The coordinator sent this back: the acceptance
criterion and the problem statement both ask for a *preview*, answering what
a cron would do **before** it is created, and a confirmation of what was
just committed answers a different question. That correction is right, and
this report's second pass builds the missing half test-first, on both
tiers: a new `POST /v1/schedules/preview` route that parses the same
`CronExpression` the write path already validates with and returns either
the refusal or the next two firings, storing nothing; a new `preview`
operation on the console's schedule courier; and a live preview beside the
cron and timezone fields, populated when either settles, showing a refusal
inline rather than a blank box when the deployment would refuse the write.
The post-creation confirmation from the first pass stays — the coordinator
named it a real improvement in its own right, not the thing being sent
back — and the European-Portuguese spelling and verb forms on this screen
("A criar…", "activar"/"desactivar", "objectivo", "contactar", and their
neighbours in the same two patterns) are corrected to Brazilian Portuguese
in the same pass, per the coordinator's explicit instruction.

Chasing item 1's premise across tiers surfaced something worth recording at
length even though it is not fixed here. Spec.md's own fix asks the empty
state to offer turning on `policies.observation.guardian.enabled` because
Configuration's own schema calls that "the single flag" the shipped
detector feature promises. It is a single flag for the shipped catalogue's
own resolution — but that resolution never reaches `GET /v1/detectors`, the
endpoint this screen and its "how many are live" count are built on
entirely. `platform/observation/detectors/config.py`'s `read()` builds a
team's detector list from `ObservationPolicySettings.detectors` alone;
`GuardianSettings` is a sibling field on the same settings object that this
function never reads. The shipped catalogue is resolved by an entirely
separate function, `platform/guardian/resolution.py`'s `resolve()`, exposed
only at `GET /v1/config/{node_id}/guardian` — a route the TypeScript console
never calls anywhere. Flipping the flag the fixed empty state now correctly
points at changes nothing this screen reads. This is real, and it is not
spec 022's to fix: none of its three acceptance criteria ask that the
shipped set actually populate the table, only that the CTA identify the
right control — which it now provably does — and the size of actually
merging two independent detector-resolution pipelines with consistent
listing, coverage, dry-run and enable/disable semantics is a different
specification's surface. Named here, in full, with the evidence, rather
than left for the next person to rediscover from scratch.

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Vazio aponta o lugar errado (guardian) | NÃO INICIADO | Wrong — already done. `detectors.tsx`'s empty state already checks whether any detector is live and, when none is, replaces "Connect a source" with "Turn on continuous observation" pointed at the viewer's own Configuration node — the exact fix spec.md asks for, with a dedicated regression test (`detectors.test.tsx`) whose own docstring names the bug. | DONE (no change) — a separate, deeper backend gap traced and left alone, named in full below |
| 2. "Scheduled investigations" cru na tela errada | NÃO INICIADO | Mostly wrong. The card, the cron helper with the spec's own example, a help line under every field, and the table's empty-state notice were all already built and tested. "Valida cron" was already satisfied by round-trip validation. "Mostra o próximo disparo" was genuinely missing — and my own first pass at fixing it (a post-creation confirmation) did not satisfy it either, per the coordinator's review. | PARTIAL → DONE (fixed in two passes; see below) |
| 3. Título promete o que não mostra | NÃO INICIADO | Wrong in substance, though nothing built it directly. No acceptance criterion targets this item; the shape of problem it names — an empty table answering none of the subtitle's three questions — is exactly what items 1 and 2's own empty-state mechanism already closes, console-wide, for every area's header. | DONE (no change) |

## Evidence and corrections

### 1. The empty state's chain — sources, then guardian

`console/src/surfaces/screens/detectors.tsx:80-102` already builds the exact
causal chain the problem statement asks for:

```ts
const liveDetectors = records.filter((record) => flag(record, 'enabled')).length;
const configurationHref =
  viewer.teamNodeId === ''
    ? '/configuration'
    : `/configuration?node=${encodeURIComponent(viewer.teamNodeId)}`;
const watching = watchingCause(locale, liveDetectors);
const cause = firstCause(
  setupCause(locale, setup),
  watching === null ? null : { ...watching, href: configurationHref },
);
```

`watchingCause` (`console/src/surfaces/emptiness.ts:63-70`) is the same
helper `incidents.tsx` uses to send an operator *here*; on this screen its
destination is deliberately rewritten to Configuration, at the node this
viewer holds, because sending it to `/detectors` unmodified would point the
screen at itself. `setupCause` is checked first, so a deployment that has
not finished its own checklist is told to finish the checklist rather than
told to flip a flag that is not yet the blocking step — the file's own
comment block (`detectors.tsx:56-69`) states this ordering rationale
explicitly.

I proved, rather than assumed, that the literal buggy text the bug report
quotes can no longer render at all. `records.length === 0` is the panel's
own emptiness condition (`stateOf(detectors, records.length === 0)`,
`detectors.tsx:130`); `liveDetectors` is `records.filter(...).length`, a
subset of `records`, so `records.length === 0` forces `liveDetectors === 0`;
`watchingCause(locale, 0)` (`emptiness.ts:64`, `if (live > 0) return null`)
therefore always returns a non-null cause whenever the panel is genuinely
empty; and `firstCause` (`emptiness.ts:96-98`) returns the first non-null
argument, so `cause` is never `null` in that state either. `emptyBecause`
(`emptiness.ts:79-87`) only keeps the catalogue's own `body`/`actionLabel`
when `cause === null`. The chain is airtight: `detectors.empty.body`
("Detectors ship with the deployment and appear here once continuous
observation is running.") and `detectors.empty.action` ("Connect a source")
are still declared in the catalogue (`console/src/i18n/en.ts:750-752`,
`pt-BR.ts:657-659`) — the type requires the `PanelEmpty` object to carry
*something* before the cause overrides it — but they are provably
unreachable given the current wiring. This is worth naming as a minor,
non-actionable observation, not a defect: nothing reads them, and removing
declared i18n keys the type still requires an object to carry is not a
change this confrontation needs to make.

`console/src/surfaces/screens/detectors.tsx:94-97`'s `configurationHref`
pattern — no field-level deep link, a link to the node's own Configuration
screen — is not a shortcut local to this screen: `autonomy.tsx:226-229` and
`agent.tsx:298` build the identical `/configuration?node=` link for the same
"go to where this is controlled" need, and nothing else in this console
links to a field-level anchor inside Configuration (a search for
`configuration\?node=|config-section-` across `console/src` finds only
`preview.tsx`'s own internal section anchors, never referenced by an inbound
link). Given that is the console's own established idiom for "link direct to
where a setting lives," I judged the acceptance criterion's "por link direto
ao campo exato" satisfied by matching it rather than inventing a
second, field-anchoring mechanism nothing else in this console has.

Tests, run and passing before any change: `console/tests/unit/surfaces/detectors.test.tsx:131-155`
(`'sources are connected and nothing is switched on'`) asserts the panel says
"No detector is switched on" and never "Detectors ship with the deployment"
or "Connect a source", and that the action link reads "Turn on continuous
observation" with `href="/configuration?node=org-northwind"`.
`detectors.test.tsx:157-176` asserts the setup-incomplete case names the
outstanding setup instead and points at `/first-run`. No change was made to
`detectors.tsx`, `emptiness.ts`, or either catalogue for this item.

**Traced and deliberately left alone.** Spec.md's own justification for
pointing the CTA at the guardian flag is `GuardianSettings`'s docstring
(`platform/config_service/schema/policies.py:527-531`): "Turning it on is a
single flag because that is the whole interaction the feature promises —
paste a token, enable the guardian, read what it would have done." That is
true of the shipped catalogue's own resolution, `platform/guardian/resolution.py`'s
`resolve()` (`:96-161`), which turns `GuardianSettings` plus the detected
`ClusterShape` into `DetectorDeclaration`s exactly like a team's own. It is
not true of what `GET /v1/detectors` serves. `DetectorService.resolved`
(`platform/incidents/service.py:150-153`) is `detector_config.read(self.settings)`;
`read()` (`platform/observation/detectors/config.py:70-100`) iterates
`settings.detectors` alone — `ObservationPolicySettings.detectors`
(`policies.py:837-840`), the team's own hand-written list — and never once
reads `settings.guardian` (`policies.py:860`), the sibling field the shipped
catalogue lives on. The only route that resolves the shipped catalogue is
`GET /v1/config/{node_id}/guardian` (`gateway/http/routes/config.py:785-809`,
`node_guardian`), and a repository-wide search of `console/src/` for any call
to it finds none — the TypeScript console has never read it. Flipping
`policies.observation.guardian.enabled` therefore changes nothing that
`GET /v1/detectors` returns, whether or not the team has declared any
detectors of its own; the fixed empty state's own CTA, followed to the
letter, would leave the table exactly as empty as it found it.

This is not conjecture: `fixtures/scenarios/populated/detectors.json` — the
committed dataset the demo, the visual suite and the e2e fixture server all
serve from — carries fourteen rows (`quorum-margin-zero`,
`datastore-near-full`, `guest-uncovered-by-backup`, and eleven more) that
read exactly like the shipped catalogue's own detector names and prose, not
like a homelab operator's own hand-written rules; the dataset's own author
evidently modelled a world where the shipped set *does* appear in this
listing. The real backend does not do that merge anywhere. I traced every
plausible path — the detector listing itself, the live detection tick
(`platform/observation/evaluation.py`'s `EvaluationTick`, whose only
non-test constructors I could find are the ones the contract and benchmark
suites build), `platform/incidents/detection.py`'s `DetectionIntake` — and
found no code, in this repository, outside tests, that ever passes a
shipped, `resolve()`-produced `DetectorDeclaration` into anything a console
reads or an evaluation tick runs.

This is not fixed here. Merging two independent detector-resolution
pipelines — the team's own, and the shipped catalogue's — into one listing
with consistent coverage, dry-run and enable/disable semantics is a
substantially larger change than a screen's empty-state wording, none of
spec 022's three acceptance criteria ask for it, and `controle.md`'s own
note ("a fusão em Signals, spec 090, muda o destino da tela inteira")
already earmarks a restructuring of this screen for later. Named here in
full so it is not silently lost.

### 2. "Scheduled investigations" — the form and its table

#### What was already built, and what my first pass got right

**A card with an explanatory title.** The whole feature already lives inside
one `Panel` — a bordered, titled card by the shared component's own
definition (`console/src/surfaces/panel.tsx:143-147`) — titled "Scheduled
investigations" with the caption "Every recurring investigation this team has
scheduled, and what it runs on" (`detectors.tsx:273,285`,
`i18n/en.ts:768-770`). The create form itself carries its own heading,
"Schedule a new investigation" (`schedules.tsx:401`, `i18n/en.ts:793`).

**A cron helper with an example, and an explanation of every field.**
`schedules.create.cronHelp` (`i18n/en.ts:807-808`) reads "Five fields —
minute, hour, day of month, month, day of week. `0 8 * * 1` runs every Monday
at 08:00." — the spec's own suggested example, verbatim in substance. Every
one of the five create fields carries a `description` from
`labels.create.help.*`: the identifier/name distinction
(`jobIdHelp`/`nameHelp`, `i18n/en.ts:803-806`) and what "Objective" feeds
(`objectiveHelp`, `:809-810`) are both named.

**An empty state on the table.** `scheduleRecords.length === 0` renders a
`data-testid="schedules-empty"` notice — heading, body, and a link to the
create form — immediately above it (`detectors.tsx:288-307`), covered by
`detectors.test.tsx:207-217`.

**Cron validation.** `ScheduleService.create` (`platform/scheduler/service.py:66-70`)
parses the cron expression and raises `CronError` *before* anything is
written; the route (`gateway/http/routes/schedules.py`) turns that into a
400 the console's own courier reads as `reason` and shows verbatim.
`CronError`'s messages are specific and field-named — "outside 0–59 in the
minute field of" is the exact text `CronExpression.parse` produces
(`platform/scheduler/cron.py:227`) and the exact text
`schedules.test.tsx`'s `'a cron expression the deployment refuses'` describe
block already pinned before this confrontation touched anything. I judged
this a correct, already-tested implementation of "valida cron" and the
coordinator's review did not send it back.

#### What my first pass got wrong, and what the coordinator sent back

Nothing on the create form, before this confrontation, ever showed what a
schedule's next run would be *before* it was created — the table gained a
new row with a `nextRun` cell once creation succeeded, but that is a
confirmation of a decision already made, not a preview of one about to be.
My first pass added exactly that confirmation (still in place — see below)
and treated it as satisfying "mostra o próximo disparo". The coordinator's
review was specific about why that is wrong: the acceptance criterion and
the problem statement both use the word "preview" — "para que o operador
veja o que `0 8 * * 1` fará **antes** de criar" — and a sentence that only
appears after the write has already happened cannot be that, no matter how
useful it is in its own right. That correction stands; a preview has to run
before the write, against a cron the operator can still change.

#### The preview, built test-first, on both tiers

**Backend: `POST /v1/schedules/preview`.** Added to
`gateway/http/routes/schedules.py`, parsing the *same* `CronExpression` the
write path already validates with (`platform/scheduler/cron.py`) rather than
a second implementation:

```python
@router.post("/preview", response_model=SchedulePreviewView)
async def preview_schedule(
    body: SchedulePreviewRequest,
    auth: AuthenticatedRequest = Depends(authorized),
) -> SchedulePreviewView:
    del auth  # the permission check is the whole reason this parameter exists
    try:
        expression = CronExpression.parse(body.cron, timezone=body.timezone)
    except CronError as error:
        raise bad_request(str(error)) from error
    firings: list[ScheduleFiringView] = []
    moment = datetime.now(UTC)
    for _ in range(SCHEDULE_PREVIEW_FIRING_COUNT):
        try:
            fire = expression.next_after(moment)
        except CronError as error:
            raise bad_request(str(error)) from error
        firings.append(ScheduleFiringView(at=fire.at.isoformat(), shifted=fire.shifted))
        moment = fire.at
    return SchedulePreviewView(firings=firings)
```

Two firings, not one: `SCHEDULE_PREVIEW_FIRING_COUNT`
(`config/constants/runs.py`, `= 2`) is a named constant per the repository's
own rule against a magic number at a call site, and two is what actually
catches a wrong field position — "next Monday 08:00, then the Monday after"
— for one more call to a function the write path already runs, which is
close enough to free that showing only the first would have been the
cheaper and worse choice. A refused expression is refused with the identical
`CronError` sentence `create`/`update` already refuse it with, before
anything would have been stored — confirmed by a test that creates nothing
and then asserts the schedule listing is still empty. The route was added
to the permission table (`gateway/http/security/gateway_routes.py`) behind
the same `Permission.SCHEDULE_MANAGE` every other schedule route already
requires.

Confirmed red first: `tests/unit/gateway/http/test_remaining_routes.py`'s
three new tests were run against the tree *before* the route existed —
`uv run python -m pytest tests/unit/gateway/http/test_remaining_routes.py -k preview`
reported all three failing with `405 Method Not Allowed` (the path matched
the existing `/{job_id}` pattern for other methods, the method did not).
After implementing the route and the permission-table row, the same three
tests, plus the file's other eight, pass — `11 passed`.

**The committed contract, regenerated, not hand-edited.** Adding a route
changes what the gateway's own OpenAPI document is, and this repository
keeps a committed copy fixtures validate against
(`fixtures/contract/openapi.json`) plus a drift test
(`tests/unit/tools/mockplane/test_verification.py::test_the_committed_document_is_what_the_application_generates`).
That test was run *before* regenerating and failed, naming the drift
explicitly ("run `python -m tools.mockplane contract` and rebuild the
fixtures") — confirmed red for the right reason, not merely inferred.
`python -m tools.mockplane contract` regenerated it (a 114-line, purely
additive diff: the three new schemas and the one new path, nothing else
touched); the drift test then passed. `python -m tools.console_toolchain run
run client` regenerated `console/src/api/schema.ts` from the updated
document (a 91-line, purely additive diff), and
`python -m tools.console_gate client-check` — the gate that fails when the
committed client is not what a fresh generation produces — passed.

**Console courier: the `preview` operation.** `console/src/app/api/schedules/route.ts`'s
`OPERATIONS` table is the closed list of writes this Route Handler will
forward — the mechanism `console/AGENTS.md` and this file's own docstring
describe as what keeps the courier from becoming an open proxy. `preview`
was added beside `create` as the second operation needing no schedule id,
for the same reason `create` needs none: there is nothing saved yet to name.

Confirmed red first:
`console/tests/unit/surfaces/schedules-route.test.ts`'s two new assertions
(the preview operation reaching `POST /v1/schedules/preview` with the right
body, and needing no id) were run against the unmodified courier —
`pnpm exec vitest run tests/unit/surfaces/schedules-route.test.ts` reported
**2 failed | 8 passed**, the failures being exactly the new assertions
(`expected undefined to be '.../v1/schedules/preview'` and a 400 where 200
was expected, because the operation was not in the table). After adding the
`preview` row, **10 passed**.

**The form: a live preview beside the field, not a blank one on refusal.**
`Input` (`console/src/components/form.tsx`) gained an `onBlur` prop — new,
confirmed red first (`console/tests/unit/components/form.test.tsx`'s
`'reports a text input settling, once focus leaves it'` failed against the
unmodified component, `expected "vi.fn()" to be called 1 times, but got 0
times`, then passed once `onBlur` was wired to the underlying `<input>`).
Deliberately distinct from `onValueChange`, which already fires on every
keystroke: a preview firing per character typed would be a request per
character, and "settled" is focus leaving the field, not a character
landing in it.

`Schedules` (`console/src/surfaces/schedules.tsx`) calls the new operation
when the cron field or the timezone field settles — the pair is what the
preview is *of*, so a timezone changed after the cron already settled has to
retake it, not leave a preview for the wrong zone on screen. The result is
held as a small tagged union (`CronPreview`, `status: 'ready' | 'refused'`)
so a caller reading it can never reach for a field the other branch would
have populated, and it is only ever shown while it still answers the *current*
form inputs — `currentPreview` is `null` the instant either field changes
again, the same "stale preview hidden without an explicit clear" pattern
`ConfigEditor`'s own `current` flag already establishes elsewhere in this
console, applied here rather than invented separately. A refused cron
renders its refusal beside the field (`data-testid="cron-preview-refused"`),
never a blank box:

```tsx
{currentPreview?.status === 'refused' ? (
  <p data-testid="cron-preview-refused" className="text-meta text-danger">
    {currentPreview.reason}
  </p>
) : null}
{currentPreview?.status === 'ready' ? (
  <p data-testid="cron-preview" className="text-meta text-muted">
    {labels.create.previewLabel}{' '}
    {currentPreview.firings.map((firing, index) => (
      <span key={firing.iso}>
        {index > 0 ? ', ' : ''}
        <time dateTime={firing.iso} title={firing.absolute}>{firing.relative}</time>
      </span>
    ))}
  </p>
) : null}
```

The preview's own network call is deliberately not the same `ask` helper
every write already shares: a preview's refusal is a fact about the field
the operator has not left yet, and folding it into the one `failure` banner
every write shares would either clear a write's own refusal the moment a
preview ran, or leave a preview's refusal sitting under a submit button it
had nothing to do with. Two independent pieces of state, the same way this
console already keeps a panel's own error apart from another panel's.

Confirmed red first: four new tests in
`console/tests/unit/surfaces/schedules.test.tsx`'s new `'previewing a cron
expression before creating it'` block were run against the tree with the
courier operation and the component state already in place but before the
render block existed —
`pnpm exec vitest run tests/unit/surfaces/schedules.test.tsx` reported
**3 failed | 15 passed**, the three failures being the "shows the next
firings", "shows the refusal", and "hides a stale preview" tests (the fourth,
"never previews an empty field", passed trivially against the *old* code
too, since nothing called preview at all yet — a legitimate regression guard
for behaviour that did not yet exist, not a red-then-green pin). After
adding the render block, **18 passed**.

**Kept, not touched again:** the post-creation confirmation from the first
pass (`schedules.tsx`, `data-testid="schedule-created"`) — the coordinator
named it "a real improvement" and explicitly not what was being sent back.

New i18n keys: `schedules.create.previewing` ('Checking the cron
expression…' / 'Verificando a expressão cron…') and
`schedules.create.previewLabel` ('Would next fire:' / 'Próximo disparo
previsto:'), in both `console/src/i18n/en.ts` and `pt-BR.ts`, threaded
through `detectors.tsx`'s existing `labels.create` object.

**Traced and confirmed unaffected: the still-present, header-only table
under the empty notice.** When `scheduleRecords.length === 0`, the
`schedules-empty` notice renders, and `<Schedules>` also still renders its
own `<table>` unconditionally, with a header row and a zero-row `<tbody>`,
directly below the notice and above the create form. The acceptance
criterion reads "Nenhuma tabela renderiza header sem corpo **nem** empty
state" — without a body *or* an accompanying empty state — and this table
has an accompanying empty state, so the criterion is satisfied as worded.
The layout is slightly redundant, but restructuring `Schedules` so the table
itself disappears when empty would mean splitting the table and the create
form into two components sharing state, which is a larger change than
anything spec.md's "correção mínima" or the coordinator's review asked for.
Left alone, named here.

#### The pt-BR dialect, on this screen

The coordinator's review named "A criar…", "activar"/"desactivar" as the
pattern to fix, plus "any neighbour in the same state" on this screen —
which I read as the same two defect classes (the European "a + infinitive"
progressive construction, and the pre-orthographic-agreement spelling that
keeps a silent consonant Brazilian Portuguese has never had), not a licence
to relitigate word *choices* that are valid in both dialects. Reading the
whole `detectors.*`/`schedules.*` block of `console/src/i18n/pt-BR.ts`
(`:646-723`) against those two patterns found more instances than the two
named examples:

| Key | Was (European) | Now (Brazilian) | Pattern |
|---|---|---|---|
| `detectors.column.enabled` | Activo | Ativo | silent consonant |
| `detectors.empty.body` | "…estiver **a correr**." | "…estiver **rodando**." | progressive |
| `detectors.control.dryRunning` | A verificar… | Verificando… | progressive |
| `detectors.control.enable` | Activar | Ativar | silent consonant |
| `detectors.control.enabling` | A activar… | Ativando… | both |
| `detectors.control.disable` | Desactivar | Desativar | silent consonant |
| `detectors.control.disabling` | A desactivar… | Desativando… | both |
| `detectors.control.unreachable` | …contactar… | …contatar… | silent consonant |
| `schedules.column.objective` | Objectivo | Objetivo | silent consonant |
| `schedules.column.enabled` | Activo | Ativo | silent consonant |
| `schedules.enable` | Activar | Ativar | silent consonant |
| `schedules.enabling` | A activar… | Ativando… | both |
| `schedules.disable` | Desactivar | Desativar | silent consonant |
| `schedules.disabling` | A desactivar… | Desativando… | both |
| `schedules.saving` | A guardar… | Guardando… | progressive |
| `schedules.create.objective` | Objectivo | Objetivo | silent consonant |
| `schedules.create.submitting` | A criar… | Criando… | progressive (the coordinator's own example) |
| `schedules.unreachable` | …contactar… | …contatar… | silent consonant |

Left alone, deliberately: `schedules.save`'s "Guardar" (a lexical choice —
"salvar" is the more common Brazilian software convention, but "guardar" is
not *wrong* Portuguese in either dialect, unlike a silent-consonant spelling
or a European verb form) and `schedules.caption` / `schedules.empty.body`'s
"esta equipa" (`:678,681` — "equipa" is the European spelling of "equipe",
the same defect class as the eighteen fixed above, but it is used
*consistently* across this screen **and** the unrelated Team Context
screen's own nav entry and page title, `nav.teamContext`,
`page.teamContext.title` — fixing only the two occurrences on this screen
would fracture that consistency rather than repair it, and Team Context is a
different specification's surface). Named here rather than silently carried
forward or silently expanded into.

### 3. Title and subtitle

`page.detectors.context` (`console/src/i18n/en.ts:89`) is unchanged: "What is
being watched for, how often, and what fired." `AreaHeader`
(`console/src/shell/area.tsx:43-70`) renders this subtitle once, at the top
of the page, from the same `Area` catalogue entry every one of the
console's nineteen areas uses (`console/src/shell/routes.ts:173-182`), and it
does not vary with the panel's own state below it — this is the
console-wide convention, not something local to Detectors, and changing it
here would mean changing the shared header component for every area.

The problem statement's own qualifier — "quando houver detectores, ok" — says
the mismatch is specifically about the *empty* case, and that case is exactly
what item 1's already-existing empty state answers: rather than restate a
promise an empty table cannot keep, `emptyBecause`/`watchingCause`/`setupCause`
explain *why* the table is empty and what to do about it — "No detector is
switched on, so nothing is being watched" or "this deployment is still being
set up," never a claim to answer "what/how often/what fired" with nothing to
show. That is the same design `emptiness.ts`'s own docstring states for every
screen it covers: "Every empty state in the console explains the mechanism
and stops there... on this deployment nothing has happened because the setup
is unfinished, and no screen says so." I confirmed the empty-state catalogue
entries (`detectors.empty.heading`, and the setup/watching cause bodies) never
repeat the subtitle's "what/how often/what fired" framing, so there is no
literal restated claim next to an empty table — only the header's ordinary,
console-wide description of the feature above a panel that, when empty,
explains the absence instead. No acceptance criterion in spec.md's "Critérios
de aceite" section names this item at all — the three listed criteria map
onto items 1, 2 and the schedules table's own empty state — and I found
nothing left to close beyond what items 1 and 2 already do. No change made.

## Verification

### Console

- `pnpm exec vitest run tests/unit/surfaces/schedules.test.tsx` — before
  fixing item 2's post-creation confirmation (first pass): **1 failed | 13
  passed (14)**, confirmed red. Before fixing the preview (second pass, this
  correction): **3 failed | 15 passed (18)**, confirmed red — the failures
  named above. After both: **18 passed.**
- `pnpm exec vitest run tests/unit/surfaces/schedules-route.test.ts` — before
  the `preview` operation: **2 failed | 8 passed (10)**, confirmed red.
  After: **10 passed.**
- `pnpm exec vitest run tests/unit/components/form.test.tsx` — before
  `Input`'s `onBlur`: **1 failed | 16 passed (17)**, confirmed red. After:
  **17 passed**, plus `tests/unit/gallery.test.tsx` (**143 passed**) to
  confirm the new optional prop does not disturb the primitive's own
  registered-variant coverage.
- `pnpm exec vitest run tests/unit/surfaces/detectors.test.tsx
  tests/unit/surfaces/detector-controls.test.tsx
  tests/unit/surfaces/detector-candidates.test.tsx
  tests/unit/surfaces/detectors-route.test.ts` — **4 files passed, 34 tests
  passed**, unmodified by anything in this second pass beyond the two new
  label fields threaded through.
- `pnpm exec vitest run` (full unit suite) — **120 files passed, 1939 tests
  passed** (1933 after the first pass, 1939 after the second — six new
  tests: `Input`'s `onBlur`, the courier's `preview` operation forwarding
  and no-id-needed cases, and the three genuinely-red schedule-preview UI
  tests; the fourth new one in that block was not red-then-green, as noted
  above). One benign jsdom console line ("Not implemented: navigation to
  another Document") is the same pre-existing test-environment noise both
  prior confrontations recorded, not a failure.
- `pnpm exec vitest run tests/unit/i18n` — **2 files passed, 24 tests
  passed** — catalogue completeness, confirming the new and corrected keys
  keep both locales in agreement.
- `pnpm exec tsc --noEmit` — clean, no output, including after the
  `console/src/api/schema.ts` regeneration.
- `pnpm exec eslint` on every changed console file — clean, including
  `no-untranslated-strings` and `no-design-literals`.
- `pnpm exec prettier --check` — two files needed `--write` after the
  `CronPreview` union type was added (`schedules.tsx`,
  `schedules.test.tsx`); reformatted, then `--check` passed clean on the
  full `src/`/`tests/` tree.
- `python -m tools.console_gate client-check` — passed both times it was
  run (once right after regenerating, once again as a final check): the
  committed `console/src/api/schema.ts` is exactly what a fresh generation
  from the committed `openapi.json` produces.

Not run: `make console-e2e` and `make console-visual` (need the pinned
toolchain and a running gateway/browser this environment does not have —
the same exclusion both prior confrontations recorded).
`tests/contract/console/` **was** run this time, since it touches the gate
and client-drift machinery this pass's changes reach: **298 passed** (0
failed), including `test_console_gate.py`'s seeded-failure splicing,
`test_console_is_an_api_client.py`, and `test_console_visual_regression.py`.

### Python

- `uv run python -m pytest tests/unit/gateway/http/test_remaining_routes.py -k preview`
  — before the route existed: **3 failed** (`405 Method Not Allowed`),
  confirmed red. After implementing the route and the permission-table row:
  **11 passed** (the whole file).
- `uv run python -m pytest tests/unit/tools/mockplane/test_verification.py::test_the_committed_document_is_what_the_application_generates`
  — before regenerating the committed OpenAPI document: **failed**, naming
  the drift and the exact command to fix it, confirmed red. After
  `python -m tools.mockplane contract`: **31 passed** (the whole file).
- `uv run python -m pytest tests/unit/gateway/http/` — **404 passed.**
- `uv run python -m pytest tests/unit/platform/scheduler/` — **66 passed.**
- `uv run python -m pytest tests/unit/tools/mockplane/` — **177 passed.**
- `uv run python -m pytest tests/security/` — **519 passed.**
- `uv run python -m pytest tests/contract/console/` — **298 passed.**
- `uv run python -m pytest tests/architecture/` — **178 passed, 1 failed.**
  The failure, `test_exactly_one_fictional_deployment_exists_in_the_repository`,
  is not this confrontation's: it scans the whole repository (outside
  `tools/mockplane`, `fixtures`, and `tests`) for the demonstration
  organisation's name (`org-northwind`) and flags any file elsewhere that
  names it, and `specs_v4` was never added to the directories it skips —
  only `specs` and `specs_v2` are. **`specs_v4/021-topology/relatorio-confronto.md`,
  a report this confrontation only read and never wrote, already names
  "Northwind" and already trips the identical assertion**, which is
  independent proof this gate was red before this session touched anything
  and stays red after every change here is reverted. `specs_v4/` is
  gitignored, so no report — the pre-existing one or this one — reaches a
  real commit either way. Not fixed here: `tests/architecture/` is a
  cross-cutting file spec 022 does not reach, and the fix belongs with
  whoever names the `specs_v4` convention, not with a Detectors
  confrontation.
- `uv run ruff check gateway/http/routes/schedules.py
  gateway/http/security/gateway_routes.py config/constants/runs.py
  config/constants/__init__.py tests/unit/gateway/http/test_remaining_routes.py`
  — clean.
- `uv run mypy gateway/http/routes/schedules.py
  gateway/http/security/gateway_routes.py config/constants/runs.py` —
  clean.
- `PYTHONPATH="$(pwd)" uv run lint-imports` — 7 contracts kept, 0 broken.
- `uv run python tools/check_constants.py` — clean.
- `uv run python tools/check_console_boundary.py` — clean.

**On confirming new tests red first.** Every genuinely new behaviour in this
confrontation — the backend preview route, the OpenAPI/client regeneration
gap, the courier's `preview` operation, `Input`'s `onBlur`, and the
preview's own render block — was confirmed red by running its test against
the code as it stood immediately before that specific change, not inferred.
The one exception is named explicitly above: the fourth new "previewing a
cron expression" test (`'never previews an empty field'`) passed before its
own implementation existed, because it asserts an absence that was already
true of the unmodified code; it is a regression guard going forward, not a
red-then-green pin, and this report says so rather than presenting it as
one. Items 1 and 3 needed no new test: for item 1, the existing
`detectors.test.tsx` suite already pins exactly what the acceptance
criterion asks, and it was *run*, not just read, against the unmodified
tree; for item 3, no gap was found for a test to pin.

## Control reconciliation

`specs_v4/022-detectors/controle.md` is updated so all three rows point at
this report and state the verified status. Item 1 was fully done already,
with its own regression test naming the exact bug spec.md reports — the
control's NÃO INICIADO was wrong. Item 2 needed two passes: the card, the
cron example, the field explanations, the table's empty state, and cron
validation were already done; my own first attempt at "mostra o próximo
disparo" — a post-creation confirmation — was a real improvement but did not
satisfy the criterion, which the coordinator's review caught and this
report's second pass corrects with an actual preview, built test-first on
both tiers (a new gateway route, a regenerated contract and client, a new
courier operation, and a live preview in the form), plus the European
Portuguese this same screen carried in eighteen keys spanning two
grammatical patterns. Item 3 needed no code: the shape of problem it names
is already resolved by item 1's own empty-state mechanism, console-wide, and
no acceptance criterion asks for anything beyond that. The onda 3/4 note
about spec 090's restructuring is kept, and a note records the guardian/
`/v1/detectors` disconnect this confrontation traced but did not fix, and the
pre-existing, unrelated `specs_v4` gap in the fictional-deployment
architecture check, so neither is rediscovered from nothing next time this
screen — or this control file — is touched.
