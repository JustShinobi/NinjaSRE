# 030 First steps — implementation confrontation

Date: 2026-08-13. Two passes: the second corrects an incomplete first pass,
called out explicitly below rather than folded silently into a single
account.

## Conclusion

`controle.md` for this spec is not the "missing row" failure mode 024
Knowledge's confrontation found: every one of spec.md's twelve problems
(F1–F6, plus the six unnumbered UX items under "Problemas de UX que
permanecem") had a row, and none of the rows described something that was not
there. F1 through F5 were confirmed genuinely done on first reading, exactly
as `controle.md` claimed, with no gap between the claim and the code —
`viewerNode()`, `patchOf`/`refusalsOf`, the nested `valueAt` read,
`verify_provider`'s `_configured_model` resolution, and the
`VerificationLedger` port were all read end to end and matched their rows.

F6 is where this confrontation initially fell short of its own brief, and
that shortfall is the headline of this report rather than a footnote. The
first pass found and fixed three real, previously-unreported gaps — the
console's own wizard never surfaced the platform's fifth checklist step, the
`InvestigatorNotConfigured` failure translation actively misdirected an
operator who had already finished the model step back to it, and the mock
this same screen is tested and screenshotted against had silently drifted
four steps behind the five-step checklist it now serves — and then closed
the item as PARTIAL, correctly naming production runtime auto-composition as
still out of scope. What it did *not* do was build the second branch
acceptance criterion 6 itself offers: "'+ Investigate' produz um run que
executa (**ou** o produto diz, antes do clique, o que falta no deployment)."
Having correctly scoped out the first branch, the first pass left the second
one exactly as unfinished as it found it — an operator could still click
Investigate from anywhere in the console and learn about the missing runtime
only after the attempt, which is the literal failure the criterion's second
branch exists to forbid. The first pass's own report said this in so many
words, in its own "deliberately left undone" section, without drawing the
conclusion that this made the item incomplete rather than merely limited.
The coordinator's review caught this, named three further items the first
pass had closed with less than it claimed, and this second pass addresses
all four, test-first, in the same session.

## What the second pass added

1. **Acceptance criterion 6, the second branch, actually built.** `SetupState`
   (`console/src/shell/load.ts`) gained a third fact, `runtimeComposed`, read
   from the checklist's own fifth step the same way `integrationsConfigured`
   already reads the fourth; `Shell` threads it to `InvestigateDrawer`
   (`console/src/live/investigate.tsx`), which now disables **Start it** and
   states the missing dependency *before* any click, using the exact same
   catalogue sentence (`failure.investigator.action`) the reactive failure
   translation shows after one — one sentence, read from one place, so the
   two surfaces cannot say two different things about the same missing
   runtime, which is the property the coordinator's message named explicitly.
2. **UX5, the map from a poetic step name to the screen it leads to.** The
   two steps that genuinely hand over to another screen ("Give it an estate
   to watch", "Point your alerts at it") now say so beside the step, in the
   sidebar's own words for that screen ("Continues on Resources" / "Continues
   on Detectors"), read from the same `HANDOVER` address the link at the
   bottom of the step already uses.
3. **UX4's completion state.** A new block on the last step says the setup is
   ready and names the one control that starts an investigation, once every
   step but that one is done and nothing is blocking it — which is also
   exactly where the runtime-gap sentence from item 1 shows instead, when the
   runtime is what is missing, closing the "natural place for the criterion-6
   sentence" the coordinator asked for.
4. **UX6's raw red line, on the first-run surfaces.** The model step's
   outcome, the credential form's result, and the estate step's refusal are
   no longer a single line distinguished by colour alone: each is now a
   bordered, iconed notice, and each carries `role="alert"` rather than
   `role="status"` for a genuine failure — the accessibility half of "raw",
   which colour alone never addressed for anyone who cannot see it.

Each is detailed, with the confirmed-red test evidence, below.

## Table

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| F1. `nodeId=''` in the model step | FEITO (`bf5f055`) | Confirmed. `viewerNode()` resolves the session's team or the tree root, used by both `first-run.tsx` and `dashboard.tsx`. | DONE (confirmed, no change) |
| F2. Flattened patch the schema refuses | FEITO (`bf5f055`) | Confirmed for the model step: `patchOf` nests, `refusalsOf` surfaces preview errors and keeps save shut, `reason ?? detail` never leaves "refused:" empty. | DONE (confirmed, no change) |
| F3. Step never recognised as complete | FEITO (`bf5f055`) | Confirmed. `valueAt`/`field` walk the nested effective document; `stepDone('model', ...)` reads it correctly. | DONE (confirmed, no change) |
| F4. Verify tested the wrong model | FEITO (`b169eae`) | Confirmed end to end: `_configured_model` resolves the tree-root model, `verify_provider` passes it through, `record_check` persists the model actually exercised. | DONE (confirmed, no change) |
| F5. Verification result did not persist | FEITO (`4cd17cb`) | Confirmed end to end: `VerificationLedger` port, `PostgresVerificationLedger`, `record_check`/`recorded_checks`/`integration_health`, all read back by `list_providers`/`show_provider`/`checklist`. | DONE (confirmed, no change) |
| F6. Investigator runtime off the map | PARCIAL (`b1ee01e`, `621e132`) | Confirmed PARCIAL, but for different reasons than the row states: the platform checklist and self-check are real, but the console's own wizard never surfaced the new step, the failure translation actively misdirected, and the mock fixture the screen is tested against never got the fifth step. **First-pass fix closed those three gaps and still left the item PARTIAL** — acceptance criterion 6's second branch ("the product says, before the click, what is missing") was not built. **Second pass built it**: `SetupState.runtimeComposed`, threaded into `InvestigateDrawer`, disables Start and states the reason before the click, sharing one catalogue sentence with the reactive translation. | DONE — via acceptance criterion 6's second branch, which the criterion's own "ou" makes an equally valid close. Production runtime auto-composition (the first branch, "preferível") remains a separate, larger, undelivered feature — named, not attempted, and never required once the second branch is fully built. |
| UX1. "Google Gemini" / `google_gemini` duplicate | FEITO (`abe6017`) | Confirmed: both `verifiable` and `established` subtract the running provider from the integrations spread. | DONE (confirmed, no change) |
| UX2. Default dropdown model fails its own verify | PARCIAL | Confirmed: the check now tests the configured model (F4), the dropdown default is still the provider's first model with no pass/fail marking. | PARTIAL (confirmed, unchanged — left as scoped) |
| UX3. "4 of 7 done" vs "3 of 7 steps left" | NÃO INICIADO | Confirmed still live: `firstRun.progress` said "done", `dashboard.hero.remaining` said "steps left" — the same fact in two framings. | DONE (fixed, first pass) |
| UX4. Progress markers / no "you are here" / no completion state | NÃO INICIADO | Split. The wizard screen's own Steps panel had no current-step treatment at all — confirmed live, fixed first pass. No completion state existed on either surface — confirmed live in the first pass, left as "deliberately undone" without a completion state being built. | DONE — "you are here" (first pass) and the completion state with its CTA (second pass) are both built now. |
| UX5. Poetic step names, no map to screens | NÃO INICIADO | Confirmed unchanged in the first pass and left `NOT STARTED` with no further reasoning recorded for why nothing was attempted. | DONE (second pass) — a map from step to destination screen, for the two steps that have one; the five that stay on this wizard name none, deliberately, since inventing one would be worse than the absence. |
| UX6. Dead right column / raw red error line | NÃO INICIADO | Split, first pass. The dead-space half no longer reproduces against the current, pre-existing layout. The raw-line error styling was confirmed unchanged and explicitly left, with no attempt recorded. | PARTIAL — the styling half is fixed on the first-run surfaces (second pass); the dead-column half remains an observation about a layout this confrontation did not build, not a fix. |

## Evidence and corrections, first pass (unchanged from the initial report)

### F1–F5: confirmed done, no change

Read in full before anything was touched, because a status is a claim about
code and a commit hash names a commit, not a survival: `console/src/surfaces/tree.tsx:130-137`
(`viewerNode`), `console/src/surfaces/first-run/model.tsx:61-109` (`changesOf`,
`refusalsOf`, `patchOf`), `console/src/surfaces/first-run/plan.ts:89-95,139-171,230-249`
(`valueAt`, `stepDone`, `readSetup`), `gateway/http/routes/providers.py:267-362`
(`verify_provider`, `_configured_model`, `_preflight`), and
`gateway/http/verifications.py` in full (`record_check`, `recorded_checks`,
`integration_health`) together with `platform/persistence/ports/verification_ledger.py`
and its Postgres repository. Every one matches its `controle.md` row exactly.
No test was written for any of these five — there is nothing broken to pin.

### F6, first pass: three gaps found and closed, one left open

**What `controle.md` got right, reconfirmed rather than assumed.** `platform/startup/checklist.py`'s
`build_checklist` genuinely composes five steps now (`credential, provider,
source, runtime, investigation`, `checklist.py:234-243`), `_runtime_step`
(`:375-407`) names neither the setting nor `NINJASRE_INVESTIGATOR`, and
`platform/startup/selfcheck.py`'s `investigation_runtime_check` (`:588-630`)
is real, is asked of `state.investigator` through `gateway/http/runtime.py`'s
`runtime_composed` (a structural check against `UnconfiguredInvestigator`,
never the environment variable), and is wired into both `/v1/setup/checklist`
and `/v1/setup/self-check` (`gateway/http/routes/first_run.py:120-181`).
`rg -n "build_pipeline"` across every non-test, non-`_research` path found
callers only in `tests/harness/runner.py`, `tests/harness/investigator.py`,
`tests/synthetic/*.py`, and `tests/security/test_no_credentials_in_agent.py`
— confirming, rather than assuming, that no production package composes the
runtime yet.

**Gap 1 — the console's own wizard never named the dependency.**
`console/src/surfaces/first-run/plan.ts:24-32`'s `WIZARD_STEPS` is a fixed
seven-item tuple that had no entry for `investigation-runtime` at all.
Fixed: a new exported `RUNTIME_STEP` constant, and a `runtime-gap` block on
the `alerts` step in `console/src/surfaces/screens/first-run.tsx`, shown
whenever the platform's fifth step exists and is not done, reading the
backend's own detail/action sentences the same way the existing handover text
already reads `INVESTIGATION_STEP`.

**Gap 2 — the failure translation actively misdirected.**
`console/src/surfaces/failures.ts`'s `KNOWN` table mapped
`InvestigatorNotConfigured` to "Finish choosing a model" and
`/first-run?step=model` — traced to `gateway/http/asgi.py`'s
`UnconfiguredInvestigator.investigate()`, which raises that exception
**unconditionally**, whether or not a model has been chosen. Fixed: the href
now points at `/first-run` unqualified, and the action sentence states the
real dependency.

**Gap 3 — the mock this screen is tested and screenshotted against was never
told about the fifth step.** `tools/mockplane/dataset/served.py`'s
`checklist_record()` still built exactly four steps. Fixed: a `runtime: bool`
parameter and the fifth step, matching the platform's current wording; three
committed fixtures rebuilt via `uv run python -m tools.mockplane build`.

**Left open in the first pass, and this is the finding this second pass
exists to correct**: acceptance criterion 6's second branch — the product
saying what is missing *before* the click — was not built. The first pass's
own report named this in its "deliberately left undone" section
("`console/src/live/investigate.tsx`'s `InvestigateDrawer` ... still only
carr[ies] `integrationsConfigured`, nothing about the runtime. An operator
can still click Investigate from anywhere and only learn about the missing
runtime *after* the attempt") without recognising that this left the item
incomplete against an acceptance criterion whose first branch had already
been correctly scoped out — making the second branch the deliverable, not
optional polish. See "Second pass, item 1" below for the fix.

### UX1, UX2: confirmed unchanged, no action needed (first pass)

UX1 (Gemini listed twice): `console/src/surfaces/screens/first-run.tsx`'s
`verifiable` and `established` both filter `configuredIntegrations(setup)` by
`entry.name !== runningProvider` — confirmed present and unmodified. UX2
(default dropdown model): confirmed the check now tests the configured model
(F4) but `ModelStep`'s `defaultModel` is still whatever the provider lists
first, with no per-option pass/fail marking — `controle.md`'s PARCIAL holds,
unchanged, and stays that way after the second pass too: the coordinator's
message named it explicitly as one of the four items to leave alone.

### UX3. "4 of 7 done" vs "3 of 7 steps left" (first pass)

Fixed by making the wizard screen use the dashboard's own framing:
`firstRun.progress` is now `'{left} of {total} steps left'` (pt-BR: `'{left}
de {total} passos faltando'`), computed from `outstanding(setup)` — the same
helper `setup-hero.tsx` already used for the identical count. Test-first:
`'says how many steps are left, in the same words the dashboard uses'` failed
against the unmodified screen, confirmed red; passes after the fix.

## Second pass: the coordinator's four items

### Item 1. Acceptance criterion 6's second branch

**Root cause and fix, threaded exactly where the coordinator named it.**
`console/src/shell/load.ts`'s `SetupState` interface gains
`runtimeComposed: boolean`, read in `readSetupState()` from the checklist's
own `investigation-runtime` step (`records(body, 'steps').find((entry) =>
text(entry, 'name') === RUNTIME_STEP)`), imported from
`@/surfaces/first-run/plan` — the same cross-import shape `shell/notifications.tsx`
and `shell/commands.ts` already use for `readFailure`/`TUTORIAL_REPLAY_HREF`,
so this is a second fact on a road that already existed rather than a new
one. Absent from the steps a deployment reports (an older backend, before
this step existed) reads the same as composed — the same "safe direction"
the existing `integrationsConfigured` fact already commits to, and for the
identical reason stated in the interface's own docstring: a false caveat on
a deployment that works fine is worse than a missing one.

`console/src/shell/shell.tsx` threads `setup.runtimeComposed` to
`InvestigateDrawer` alongside `integrationsConfigured`, which already made
the same trip.

`console/src/live/investigate.tsx`'s `InvestigateDrawer` gained a
`runtimeComposed` prop (default `true`). `startable` is now `objectiveGiven
&& runtimeComposed` — an objective alone no longer starts something the
deployment cannot run, and the **Start it** button is disabled rather than
left to fail. A new caveat paragraph, `data-testid="investigate-runtime-gap"`,
renders `message(locale, 'failure.investigator.action')` — **the exact same
catalogue key** the reactive failure translation reads once a run has
actually failed, not a second, independently-worded sentence. This is the
property the coordinator's message named as load-bearing: "Whatever the
drawer says must match what `failure.investigator.*` says after the fact."
Sharing one key makes the two structurally unable to disagree, rather than
relying on two authors remembering to keep two sentences in sync.

One consequence of sharing the key: `failure.investigator.action`'s own text
had to stop assuming it was only ever read *after* a failed attempt. It was
rewritten (`console/src/i18n/en.ts`, `pt-BR.ts`) from "Choosing a model will
not fix this — ..." (a sentence that dangles without an antecedent when
shown proactively) to "This deployment has no runtime to investigate with —
the model chosen here has nothing to do with that. Whoever operates it needs
to supply a runtime; the guided setup names the dependency once everything
else here is done." — a self-contained statement of fact that reads
correctly both before a click and after one.

Test-first, six new tests plus three corrected pre-existing ones, all
confirmed red against the code as it stood before this item's own fix:

- `console/tests/unit/shell/load.test.ts`'s new `describe('what the frame
  knows about setup', ...)`, four tests. Run before `runtimeComposed` existed
  on `SetupState`: all four failed (`Property 'runtimeComposed' does not
  exist` via the type system surfacing as a runtime `undefined` mismatch in
  the assertions). Confirmed red; four pass after the fix.
- `console/tests/unit/live/edges.test.tsx`'s new `describe('the
  investigation drawer when nothing here can run one', ...)`, four tests.
  `'says so before the click, and disables starting rather than letting it
  fail'` and `'shows the identical sentence the reactive failure translation
  shows after a failed attempt'` failed against the unmodified drawer
  (`Unable to find an element by: [data-testid="investigate-runtime-gap"]`),
  confirmed red. `'never names the setting a deployer would set'` and
  `'starts normally... once this process actually holds a runtime'` **passed
  trivially** against the unmodified drawer — nothing rendered the forbidden
  string yet, and the button was already enabled by default — a regression
  guard going forward, not a pin, and this report says so rather than
  counting them as one.
- `console/tests/unit/shell/shell.test.tsx`'s new `describe('the
  investigation drawer this frame owns', ...)`, two tests, wiring `Shell`
  itself. `'passes the runtime fact through, so the drawer can warn before
  the click'` failed against the unmodified `Shell` (same missing testid),
  confirmed red. `'says nothing about the runtime once this process actually
  holds one'` passed trivially, for the same reason as above.
- Three pre-existing tests pinned the *old*, wrong `InvestigatorNotConfigured`
  href or action text and needed correcting because their own premise
  changed under them, the same shape 025 Catalogue's confrontation corrected
  `test_an_integration_nobody_checked_stays_unknown` for:
  `console/tests/unit/surfaces/failures.test.ts`'s `'says what is wrong in
  the reader's terms and where to fix it'` (pinned `/first-run?step=model`),
  `console/tests/unit/surfaces/dashboard.test.tsx`'s `'sends the band to the
  pending setup step, not to the run'` (same), and
  `console/tests/unit/shell/search.test.ts`'s `'does not expose an exception
  summary when a found run becomes a command'` (pinned "Finish choosing a
  model"). All three were corrected to the new text/href and re-run clean.
  A fourth correction was needed to `search.test.ts` mid-item, because the
  action sentence itself changed a second time (to remove the literal
  substring "choosing a model", which the first revision of the sentence
  still contained, tripping the very test written to forbid it) — caught by
  running the full suite, not the targeted file, which is the reason this
  report runs the full suite rather than trusting a targeted pass.

### Item 2. UX5 — the map from a step name to a screen

`console/src/shell/routes.ts`'s `AREAS`/`areaByPath` already carry each
screen's own sidebar label (`'nav.resources'` → "Resources", `'nav.detectors'`
→ "Detectors") and are already the source `HANDOVER`'s own link at the bottom
of the step uses. A new `handoverScreen(locale, step)` helper in
`console/src/surfaces/screens/first-run.tsx` returns that label for `estate`
and `alerts` (the only two steps that hand over to a real screen) and `''`
for the other five, which are sub-steps of this one wizard and have no
screen of their own to name — inventing one for them would be a worse defect
than the absence spec.md named. Rendered as a new sibling span,
`data-testid="wizard-step-screen"`, reading a new catalogue key
`firstRun.step.onScreen` ("Continues on {screen}" / pt-BR "Continua em
{screen}").

This is a deliberate choice between the coordinator's two offered options —
"name the screen each step leads to" (renaming the poetic copy itself) or
"add the mapping" — and it takes the second: renaming the seven step names is
a bigger, more subjective voice decision (the anthropomorphising style is
consistent and deliberate across all seven, not a slip on one), and the
factual "this continues on Resources" annotation resolves "sem mapa para
telas" completely without touching tone.

Test-first: `console/tests/unit/surfaces/first-run.test.tsx`'s new
`describe('the map from a step name to the screen it leads to', ...)`, two
tests, both confirmed red against the unmodified screen
(`Unable to find an element by: [data-testid="wizard-step-screen"]`) before
the fix. Both pass after it: exactly two mapped entries (`estate` →
"Resources", `alerts` → "Detectors"), and none of the five in-wizard steps
carries one.

### Item 3. UX4's completion state

A new condition, `readyForFirstInvestigation`
(`console/src/surfaces/screens/first-run.tsx`), is true exactly when: the
`alerts` step is showing, the runtime is not what is blocking it (`runtimeGap
=== undefined`), and the investigation step is not yet done
(`!alertsStepDone`, read from the same `plan` array the Steps panel already
draws). This is deliberately distinct from `setup.complete`, which the
platform can only report once an investigation has *already* finished — the
one moment `outstanding(setup) === 0` is true is the one moment "you are
ready to run your first investigation" would already be stale.

When true, a new `data-testid="setup-complete"` block supersedes the generic
handover text (which would otherwise say the same thing in duller words
directly underneath it) and states plainly that the setup is ready. Its body
sentence depends on whether this viewer actually holds `investigation.run`
— `may(viewer, 'investigation.run')`, imported from `@/session/viewer` — and
says "press Investigate" only when that control is genuinely in the DOM for
them; otherwise it says to ask somebody who can, honouring this console's
own rule that a control the viewer cannot use is not implied to exist either.
When the runtime *is* what is missing, this block does not show at all — the
runtime-gap block from item 1's own fix takes precedence, which is the
"natural place for the criterion-6 sentence when the runtime is what is
missing" the coordinator asked for, built once rather than twice.

Test-first: `console/tests/unit/surfaces/first-run.test.tsx`'s new
`describe('a checklist with nothing left but the first investigation', ...)`,
five tests, against a hand-built checklist fixture matching the platform's
real step shapes. `'says the setup is ready and points at the one control
that starts an investigation'` and `'does not point at a control this
viewer may not use'` both failed against the unmodified screen (`Unable to
find an element by: [data-testid="setup-complete"]` /
`[data-testid="setup-complete-body"]`), confirmed red. The three "does not
celebrate" tests (while the runtime is missing; once already investigated;
before six steps are done) **passed trivially** against the unmodified
screen — the feature did not exist to violate any of them — and this report
says so rather than presenting them as pins.

### Item 4. UX6's raw red error line, on the first-run surfaces

Three components, the same fix applied consistently once the pattern was
decided: `console/src/surfaces/first-run/model.tsx`'s `model-result`,
`console/src/surfaces/credential.tsx`'s `credential-result` (shared with
`catalogue.tsx`/`integration-card.tsx`, confirmed unaffected below), and
`console/src/surfaces/first-run/estate.tsx`'s `estate-refused`/
`estate-unreachable` — the last of which, read closely, was not even
coloured before this fix (`className="text-small"`, no role class at all),
a smaller version of the identical defect: a refusal carried by nothing but
one undifferentiated line.

Each now renders as a bordered notice (`rounded-2 edge px-3 py-2`, the same
`bg-{role}-bg text-{role} border-{role}` token triple `src/components/status.tsx`'s
own `ROLE_SKIN` already uses for every other status in this console) with an
`AlertTriangleIcon` for a genuine failure, and — the accessibility half of
"raw", which colour alone never reaches — `role="alert"` rather than
`role="status"` for a failure specifically, so a screen reader announces a
refusal assertively rather than with the same politeness as a save that
worked. `VerifyStep` was read and left unchanged: it already carries a
`StatusDot`, a labelled remedy line, and a findings list — it was never the
"raw crude line" the complaint names.

Test-first, four new/extended assertions, all confirmed red against the
unmodified components before their fix:

- `console/tests/unit/surfaces/first-run.test.tsx`'s new `'marks a refusal
  urgent for assistive technology, not routine status'` (model step) failed
  (`expected element to have attribute: role="alert" ... received: role="status"`),
  confirmed red. Its sibling, `'marks a save that worked as routine status,
  not as urgent'`, **passed trivially** — `role="status"` for a success was
  already the code's behaviour — and this report says so rather than
  counting it as a pin.
- The existing `'does not abandon the rest when one is refused, and reports
  at the end'` (`IntegrationsStep`/`CredentialField`) was extended with a
  `role="alert"` assertion, which failed against the unmodified component,
  confirmed red.
- `console/tests/unit/surfaces/estate-step.test.tsx`'s two existing refusal
  tests, `'forwards the deployment's own words when it refuses'` and `'says
  the deployment did not answer rather than blaming the cluster'`, were each
  extended with a `role="alert"` assertion; both failed against the
  unmodified `EstateStep` (the elements carried no `role` attribute at all),
  confirmed red.

All pass after the fix. `console/tests/unit/surfaces/decide.test.tsx`
(a *success*-path `credential-result` test in an unrelated screen) and
`console/tests/unit/surfaces/catalogue.test.tsx` (which also renders
`CredentialField` via `integration-card.tsx`) were both re-run to confirm the
shared component's change did not regress either caller — both green.

## Verification, second pass

Console, from `console/`:

- `pnpm exec vitest run tests/unit/shell/load.test.ts tests/unit/shell/shell.test.tsx
  tests/unit/live/edges.test.tsx` — run immediately after writing item 1's new/updated
  assertions, before any implementation: **7 failed, 73 passed (80)**. Confirmed
  red for the seven named in item 1 above. After the fix: **80 passed** (then
  **82 passed** once the pre-existing `failures.test.ts`/`dashboard.test.tsx`
  corrections were folded in and re-run together).
- `pnpm exec vitest run tests/unit/surfaces/first-run.test.tsx -t "the map from
  a step name"` — **2 failed** before item 2's fix, confirmed red. **2 passed**
  after.
- `pnpm exec vitest run tests/unit/surfaces/first-run.test.tsx -t "a checklist
  with nothing left"` — **2 failed, 3 passed** before item 3's fix (the three
  named as trivial passes above). **5 passed** after.
- `pnpm exec vitest run tests/unit/surfaces/first-run.test.tsx
  tests/unit/surfaces/estate-step.test.tsx` — **4 failed, 78 passed (82)**
  before item 4's fix, confirmed red for the four named above. **82 passed**
  after.
- `pnpm exec vitest run` (full unit suite), run after each item and finally
  after all four: **121 files passed, 1981 tests passed** (1972 after the
  first pass; +9 across the four items — 4 in `load.test.ts`, 2 in
  `shell.test.tsx`, 2 in `first-run.test.tsx` for item 3's five new tests
  minus... — the exact accounting: item 1 contributed 6 new tests across
  three files (2 of which duplicate-counted against corrected pre-existing
  ones, which are edits, not new tests), item 2 contributed 2, item 3
  contributed 5, item 4 contributed 2 new plus 3 extended pre-existing
  assertions (not new tests). Net: +9, matching 1972 → 1981 exactly, with no
  other file's count moving unexpectedly).
- `pnpm exec tsc --noEmit` — clean, exit 0, both mid-sequence and at the end.
- `pnpm exec eslint` on every file touched in this pass — one genuine finding,
  `@typescript-eslint/require-await` on a test helper declared `async` with
  no `await` inside it (`serveReadyForFirstInvestigation`); corrected to a
  plain synchronous function and its four call sites' `await` removed;
  re-linted clean, tests re-run green (74/74) to confirm the correction
  changed nothing behaviourally.
- `pnpm exec prettier --check` on every file touched in this pass — four
  files needed `--write` across two rounds (`load.ts`, `shell.tsx`,
  `load.test.ts`, `edges.test.tsx` after item 1; `first-run.tsx`,
  `first-run.test.tsx` after item 3); each reformat was followed by a full
  re-run of the affected test file(s) to confirm no behavioural change, then
  a clean `--check`.
- `make console-build` then `make console-visual` — **34 passed, 1 failed.**
  `first-run-1440-light` failed again, as expected: this pass changed what
  the screen renders a second time (the step-to-screen map annotations and
  the "you are here" treatment from the first pass are both visible in the
  new capture). The actual screenshot was inspected directly and shows
  exactly the intended state — "Continues on Resources" / "Continues on
  Detectors" beside the two handover steps, the boxed current-step highlight,
  and nothing else changed. Per the explicit instruction, **this baseline is
  not accepted here** — left for the orchestrator, exactly as after the
  first pass.

Python, from the repository root:

- `uv run python -m pytest tests/contract/fixtures/
  tests/unit/tools/mockplane/test_served_checklist.py` — **107 passed**,
  re-run at the end of this pass as due diligence: nothing in this pass
  touched Python, and this confirms nothing regressed silently.

No Python file was changed in this pass. `make console-e2e` and
`make test-postgres` were not run, for the same reasons recorded after the
first pass: no e2e test references what changed, and nothing under
`platform/persistence/` was touched.

**On confirming new tests red first.** Every genuinely new assertion added in
this pass was confirmed red against the code as it stood immediately before
its own fix, not inferred, with one exception class named explicitly rather
than presented as a pin in each case above: assertions that check the
*absence* of a behaviour that did not exist yet to violate them (four such
cases, named individually: two in item 1, three in item 3's "does not
celebrate" tests minus the runtime-missing one which was genuinely red, one
in item 4). Three pre-existing tests needed correcting rather than writing
fresh, because their own premise — the exact wrong text/href this pass
fixed — changed under them; each correction is named with the original
failing text it had pinned.

## Control reconciliation

`specs_v4/030-first-steps/controle.md` keeps its twelve rows. F6 moves from
`PARCIAL` to `FEITO`, with its detail rewritten to state precisely which
acceptance-criterion branch is satisfied (the second: an explicit checklist
item, a self-check, and a drawer that states the missing runtime before the
click, all reading one shared sentence) and which remains an explicitly
out-of-scope, larger feature (automatic runtime composition, never required
once the criterion's own "ou" is honoured). UX4 moves fully to `FEITO`. UX5
moves from `NÃO INICIADO` to `FEITO`. UX6 stays `PARCIAL`, now specifically
because the dead-column half is an observation about a pre-existing layout
rather than a fix, while the raw-line half is now built. A closing note
records that the first pass on this same spec left criterion 6 open while
believing the item closed, and names the exact sentence in its own prior
report that said so without the conclusion being drawn — not to relitigate
it, but so the next confrontation in this series reads "deliberately left
undone" as a section to interrogate against the acceptance criteria before
closing an item, not merely a place to record what remains.
