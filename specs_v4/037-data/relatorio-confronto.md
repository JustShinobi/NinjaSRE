# 037 Data — implementation confrontation

Date: 2026-08-14.

## Conclusion

`controle.md` drifted in the direction this series keeps finding: it marked
all five of `spec.md`'s items `NÃO INICIADO`, with a closing note deferring
"quanto vale corrigir no lugar" to the screen's eventual merge into Signals
(spec 090). Reading `console/src/surfaces/screens/data.tsx` line by line, then
running its own test suites — `data.test.tsx`, `data-copy.test.tsx`,
`simulation.test.tsx`, `delivery-token.test.tsx`, `resend.test.tsx`,
`ingress.test.tsx`, `transit-routes.test.ts` — against the unmodified tree
rather than trusting either `controle.md`'s account or the code's own
comments, found **73 passing tests** covering behaviour `controle.md` called
untouched. Commit `128c88e` ("put where it came from and where it goes on one
screen, in that order") first replaced five separate screens with this one;
commit `1ef8dd6` ("mark the session cookie secure behind a proxy, and three
more screens", 2026-08-13, one commit before the `HEAD` this audit started
from) then closed four of `spec.md`'s five items in full and the fifth by
half, none of it reflected in `controle.md`. Items 2 ("URLs de webhook em
http:// com IP interno"), 3 ("'Nothing has ever arrived here' sete vezes em
vermelho"), 4 ("'Where did this go?' colapsado") and 5 ("'Issue a delivery
token' solto") were, on inspection and on running their own tests, **already
fully done**: an unsafe (`http://`) scheme is never rendered and every address
copies in one click (`data-copy.tsx`'s `CopyValue`); the never-delivered
marker is `text-muted`, never `text-danger`; the provenance disclosure already
reads "Where did this go? (N)" with the real delivery count; and the delivery
token button already sits inside a `delivery-token-group` directly beneath the
permission it needs.

Item 1 split exactly the way 020's, 024's and 036's confrontations have
repeatedly found a half-fix split. Its two asks are independent — "só mostrar
a régua de regras quando houver regras" and "dar título honesto" — and only
one was actually finished. The rule ruler's conditional appearance (the
numbered `<ol>` only draws once there is more than the implicit catch-all; a
lone catch-all draws as a plain `<ul>` with no ordinal and no "no rule above
matched" sentence) was already correct and already pinned by two tests. The
"honest title" was not: the fix that landed gave the select/textarea/buttons
cluster a heading, but the heading's own text was `data.simulate.action` —
literally the string "Simulate", the very word the bug names as one of the
two labels ("Simulate/Save") that fail to say this is a routing tester — with
no purpose sentence anywhere beneath it. `spec.md`'s own acceptance criterion
is two-part ("nome **e** propósito legíveis"); the pre-existing fix satisfied
the first half and not the second. That is fixed here, test-first, in both
locales: a new heading string ("Test a delivery" / "Testar uma entrega",
echoing `spec.md`'s own suggested wording) and a new purpose sentence naming
what the tool actually answers (which rule, which team), replacing the
self-referential heading.

Two smaller things were found and corrected on the same pass, both reachable
from this exact screen and neither touched by `controle.md`. First, a
documentation drift directly downstream of item 3's own fix: `visual/
screens.json`'s acceptance note for `data-1440-light` still described the
never-delivered marker as drawn "in the danger tone" — the literal defect
item 3 closes — even though the committed baseline PNG beside it had already
been recaptured, in the same commit that changed the colour, to show the
neutral styling. Left as written, the note actively misdescribes what the
baseline now protects and would mislead a future reviewer into thinking
danger-tone styling is the intended, guarded behaviour. Corrected to describe
the neutral tone and the ordering together, which is what the current PNG
and the current code actually guard. Second, a small Brazilian-Portuguese
consistency defect on this screen's own reachable strings: three of the
`ingress.token.*` messages the delivery-token control renders
(`shownOnce`, `failed`, `unreachable`) called the deployment "a implantação"
where every sibling string on this same screen, and 64 other places in the
same catalogue file, call it "o deployment" — two of the three are, after the
fix, copy-identical to strings that already read that way elsewhere in the
file (`data.simulate.failed`, `data.simulate.unreachable`). Fixed on all
three; no failing test could show this red first, the same situation every
prior dialect fix in this series has reported, and this report says so
plainly rather than inventing one.

Two things were traced to the end and deliberately left alone, named rather
than silently dropped. `spec.md`'s item 2 also asks, conditionally, to "exibir
com o host público correto do deployment" if the http:// address is the real
ingest URL. I read every field `SurfaceContext` and `Deployment` carry
(`console/src/surfaces/context.ts:26-35`, `console/src/shell/deployment.ts:
27-30`) and confirmed the console has no notion of a deployment's public host
anywhere — only a display name (`NINJASRE_CONSOLE_DEPLOYMENT`, e.g. "HAL9000")
and a timezone. The backend's own `gateway/http/routes/ingress.py` docstring
(`:9-12`) already explains, in its own words, why it deliberately builds the
address from the request rather than from a second, configured "public URL"
setting: "A configured public URL would be a second copy of the same fact,
right until somebody put the deployment behind a different name and forgot
this one." Given that, and given the current fallback (never render the
unsafe address; fall back to the bare, host-less path, which cannot lie)
already satisfies both of this item's acceptance criteria in full, inventing
a second, console-side source of truth for "the public host" would be going
against this codebase's own stated reasoning for a case its own acceptance
bar does not require. Left alone. Second, `RuleSimulator`'s "Save" button
(`console/src/surfaces/simulation.tsx:151-159`) has never had an `onClick`
handler, and cannot get one yet: `gateway/http/routes/transit.py` declares
`GET /rules` and `POST /simulate` but no `POST /rules` or any other route that
could receive a saved rule. This predates every one of `spec.md`'s five items
(present since the screen's original build in `128c88e`), is not asked for by
any of them, and needs a backend capability that does not exist — named here
so the next confrontation that reaches this screen does not have to
rediscover it.

## Table

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Três colunas, três features, uma tela | NÃO INICIADO | Half right. The rule ruler's conditional appearance (only drawn once there is more than the implicit catch-all) was already correct and already pinned by two tests. The "honest title" was a bare `<h4>` reusing the literal string "Simulate" — one of the two labels the bug itself names as inadequate — with no purpose sentence anywhere. | Ruler: DONE (no change). Name + purpose: fixed here, test-first |
| 2. URLs http:// com IP interno | NÃO INICIADO | Wrong — already done. An unsafe (`http://`) scheme is never rendered; the screen falls back to the bare, host-less path, which cannot lie, and either form copies in one click via `CopyValue`. 12 tests across `data.test.tsx`/`data-copy.test.tsx`, built against the exact IP `spec.md` quotes, already pinned this and passed unmodified. | DONE (no change) |
| 3. "Nothing has ever arrived" em vermelho ×7 | NÃO INICIADO | Wrong — already done. The marker carries `text-muted`, never `text-danger`; a dedicated test asserts both classes directly. The visual baseline's own acceptance note, however, still described the pre-fix "danger tone" behaviour the baseline PNG itself no longer shows. | Colour: DONE (no change). Stale baseline note: fixed here |
| 4. "Where did this go?" sem indicação | NÃO INICIADO | Wrong — already done. The disclosure summary already reads "Where did this go? (N)", N being the real count of deliveries the ledger holds for that source; tested for a source with one delivery and one with zero. | DONE (no change) |
| 5. "Issue a delivery token" solto | NÃO INICIADO | Wrong — already done. The button already sits inside a `delivery-token-group`, directly beneath a line naming the permission a token needs; tested. | DONE (no change) |

## Evidence and corrections

### 1. Three columns, three features, one screen

**The rule ruler — already correct.** `console/src/surfaces/screens/
data.tsx:96-100` computes `explicitRules` as "does any rule other than the
catch-all exist"; `:318-382` branches on it — an `<ol data-testid="routing-
rules">` with ordinals and the "no rule above matched" note (`data.rules
.catchAll`) when there is a real ranking, a plain `<ul>` with neither when the
only rule is the implicit default. `data.test.tsx`'s `'is drawn as a ranked
list only once there is more than the implicit default'` and `'is not drawn
as a ranked list when the only rule is the implicit default'` (the second
asserting no leading `"1."`, no `catch-all-note`, no `routing-rule` testid on
the `empty` scenario) both ran, unmodified, against the current tree and
passed before this audit touched anything.

**The title — genuinely unfixed, fixed here.** Before this audit,
`data.tsx` (pre-fix) read:

```tsx
{/* An honest name for what this is, rather than a select, a
    textarea and two unlabelled buttons. */}
<h4 className="text-strong">{message(locale, 'data.simulate.action')}</h4>
<RuleSimulator ... />
```

`data.simulate.action` (`en.ts:138`, pre-fix) is `'Simulate'` — the literal
word the button beneath the heading also carries
(`RuleSimulatorProps.labels.simulate`, `simulation.tsx:149`), and one of the
two labels `spec.md`'s own text quotes as failing to say this is a routing
tester ("botões 'Simulate/Save' sem dizer que isto é um testador de
roteamento"). The comment's own intent ("An honest name for what this is")
was real, but the string chosen restates a button label rather than naming
the tool's purpose, and the acceptance criterion asks for both ("nome **e**
propósito legíveis").

Test-first: `data.test.tsx`'s `'names itself, rather than presenting as an
unlabelled form'` test was rewritten to `'names itself and says what it
tests, rather than presenting as an unlabelled form'`, asserting the heading
reads "Test a delivery" and the section's text contains "See which rule
would catch a payload and which team it would reach". Run against the
unmodified component: `pnpm exec vitest run tests/unit/surfaces/data.test.tsx`
— **1 failed | 27 passed (28)**, the new assertion failing with
`TestingLibraryElementError: Unable to find an element with the accessible
name`, matched against the DOM dump showing the heading still reading
"Simulate" — confirmed red for the reason named. Fixed by two new catalogue
keys and `data.tsx:390-395`:

```tsx
{/* An honest name and purpose for what this is, rather than a
    select, a textarea and two unlabelled buttons. */}
<h4 className="text-strong">{message(locale, 'data.simulate.title')}</h4>
<p className="text-meta text-muted">
  {message(locale, 'data.simulate.purpose')}
</p>
<RuleSimulator ... />
```

`en.ts:136-138`: `'data.simulate.title': 'Test a delivery'`,
`'data.simulate.purpose': 'See which rule would catch a payload and which
team it would reach, before anything is saved.'`. `pt-BR.ts:1268-1270`:
`'data.simulate.title': 'Testar uma entrega'` (echoing `spec.md`'s own
suggested wording verbatim), `'data.simulate.purpose': 'Veja qual regra
pegaria um payload e qual equipe ele alcançaria, antes de salvar qualquer
coisa.'`. `data.simulate.action` (`'Simulate'`/`'Simular'`) is kept unchanged
and still used only for the button's own label
(`simulation.tsx`'s `labels.simulate`), so the heading and the button no
longer say the identical word. After the fix: **28 passed**.

**Traced and left alone: the "Save" button has no handler.**
`console/src/surfaces/simulation.tsx:151-159` renders `simulate-save` with a
`disabled`/`title` pair gating it on `answer !== undefined`, but no
`onClick` at all — clicking an enabled Save button does nothing. Checked
whether the backend has anywhere for a save to go:
`gateway/http/routes/transit.py` declares `GET /rules` (`:296-324`) and
`POST /simulate` (`:327-388`) only; a repository-wide read of the whole file
found no `POST`/`PUT`/`PATCH` route that could accept a saved rule. This
predates every one of `spec.md`'s five items — present since the screen's
original build in `128c88e` — is not named by any of them, and cannot be
finished without a backend capability that does not exist. Left alone, named
for whichever confrontation next reaches this screen or its backend route.

### 2. Webhook URLs in http:// with an internal IP — already fixed

`data.tsx:198-219`: wherever a receiver's paste-ready address is available,
its scheme is parsed (`schemeOf`, `:503-516`, built on `new URL(...).protocol`
rather than a prefix match) and compared against `UNSAFE_SCHEME` (`:501`,
built from `['http', ':'].join('')` so the literal scheme this file exists to
stop announcing is never itself a literal in the source). An unsafe scheme
falls back to `text(source, 'path')` — the bare, relative address, which
carries no host and so cannot lie about one — instead of the URL. Both forms
render through `CopyValue` (`console/src/surfaces/screens/data-copy.tsx:31-
57`), which copies the exact value shown in one click and changes its own
label to say so.

Confirmed by running, not reading, against the unmodified tree:
`data.test.tsx`'s `'a webhook address safe to announce'` block builds the
`UNSAFE_PAGERDUTY_URL` constant from the exact IP `spec.md`'s own text quotes
(`['http:', '//192.168.68.74:8420/webhooks/pagerduty'].join('')`,
`data.test.tsx:24-26`), swaps it in for one receiver via a `fetch` stub
(`serveWithUnsafeIngressUrl`, `:39-57`), and asserts both that no `http://`
string ever appears in that row's text content and that the copy button
still copies the fallback path exactly. `data-copy.test.tsx`'s own three
tests cover the component in isolation (shows the value, copies it,
degrades honestly when the clipboard refuses). All 12 tests across the two
files passed unmodified before this audit changed anything, and after —
confirmed again in the full run below.

**Traced and left alone: the conditional "show the correct public host"
half.** `spec.md` also asks, conditionally, to show the address "com o host
público correto do deployment" if the http:// address is the genuine ingest
URL. `console/src/surfaces/context.ts:26-35` (`SurfaceContext`) and
`console/src/shell/deployment.ts:27-30` (`Deployment`) are the whole of what
a screen can read about the deployment it is rendering for; neither carries
anything resembling a public host or base URL — `Deployment` is a display
`name` and a `timezone`, nothing else. `gateway/http/routes/ingress.py:9-12`
already gives the reason no such setting exists: "The URL comes from the
request... A configured public URL would be a second copy of the same fact,
right until somebody put the deployment behind a different name and forgot
this one." `:57` (`base = str(request.base_url).rstrip("/")`) is that
decision in code. Given the console has nothing to construct a "correct
public host" from, and the fallback already in place satisfies both of
`spec.md`'s acceptance bars (no `http://` ever renders; the value that does
render is always copyable in one click), inventing a second source of truth
on the console side would run against the reasoning the backend's own route
already states — declined on that reasoning, not on avoiding the work.

### 3. "Nothing has ever arrived here" seven times in red — colour already fixed, baseline note was stale

`data.tsx:174-179`: the never-delivered marker carries
`className="text-meta text-muted"`, never `text-danger`, with a comment
explaining the decision directly: "Neutral, not danger. A receiver that has
never delivered is the ordinary shape of a deployment nobody has pointed an
alert router at yet... What the API cannot say... is whether an operator's
alertmanager names this receiver and has gone quiet." `data.test.tsx`'s `'is
neutral rather than styled as an error'` asserts, over every
`never-delivered` marker on the `empty` scenario (seven rows), that
`className` excludes `text-danger` and includes `text-muted`. Run
unmodified: passed, before this audit changed anything.

**The visual baseline's own acceptance note was stale, and is corrected
here.** `console/visual/screens.json`'s entry for `data-1440-light` (the
committed baseline whose PNG was itself already recaptured, in the same
commit that changed the colour, to show the neutral styling — confirmed by
`git show 1ef8dd6 --stat` recording the PNG's byte size changing) still
carried its original acceptance reason, unedited:

```
"reason": "...the one thing this screen has to get right is *emphasis* —
a receiver that has never delivered is drawn first and in the danger tone,
and a change that quietened it would be invisible to every other check
while removing the whole reason the screen is here."
```

This describes the exact pre-fix behaviour item 3 exists to remove, and it
now contradicts both the current code and the current baseline image beside
it — read on its own, it would tell a future reviewer that danger-tone
styling is the guarded, intended behaviour, which is backwards. There is no
automated gate over this prose (`console/AGENTS.md` describes it as the
acceptance record a human reads), so nothing failed red over this — it is a
direct, corrected consequence of confronting item 3, not a separate finding.
Corrected to:

```
"reason": "...the one thing this screen has to get right is *emphasis
without alarm* — a receiver that has never delivered is drawn first, in the
same neutral tone as everything else, and a change that lost either the
ordering or the neutrality would be invisible to every other check while
undoing the whole reason the screen reads this way."
```

Validated as syntactically correct JSON after the edit
(`python3 -c "import json; json.load(open(...))"`).

### 4. "Where did this go?" collapsed with no indication of content — already fixed

`data.tsx:250-269`: the `Provenance` disclosure's `open` label is built as
`` `${message(locale, 'data.provenance.open')} (${formatNumber(locale,
arrivalRows.filter(...).length)})` ``, with a comment naming the exact
complaint it answers: "Seven identical disclosures with no count is seven
questions an operator has to open one at a time to answer 'expand to
what?'." `console/src/surfaces/provenance.tsx:49-90` renders it as the
`<summary>` of a `<details>`, unconditionally — the count is visible before
the disclosure opens. `chainOf` (`data.tsx:526-537`) supplies the chain from
the ledger rows the screen already read, not a second per-source query.

`data.test.tsx`'s `'names how many deliveries the disclosure holds, before
it is opened'` asserts `alertmanager` (one delivery in the `populated`
fixture) reads "Where did this go? (1)" and `datadog` (never delivered)
reads "Where did this go? (0)". Three further tests in the same
`describe('provenance', ...)` block cover the resolved chain's content
(rule, team, resource), the run link's `href`, and the "nothing to trace"
sentence on the `empty` scenario. All four passed unmodified before this
audit touched anything; `console/src/surfaces/provenance.tsx` has no
dedicated component test of its own, but is exercised structurally through
these four.

### 5. "Issue a delivery token" orphaned — already fixed

`data.tsx:274-299`: the button is not between sections — it is inside
`data-testid="delivery-token-group"`, directly beneath a line naming the
scope a token needs (`{message(locale, 'ingress.verification')}
{deliveryPermission}`, rendering "Trusted by webhook.deliver"), with a
comment naming the fix directly: "Grouped with what it is scoped to rather
than left as an orphan control below seven cards." `deliveryPermission`
comes from the deployment's own answer
(`gateway/http/routes/ingress.py:44-48`,
`delivery_permission: str = Permission.WEBHOOK_DELIVER.value`), not a
hand-written string that could drift from what the backend actually
requires. `data.test.tsx`'s `'sits beside what it is scoped to, rather than
orphaned below the cards'` asserts the group's text contains
`'webhook.deliver'` and contains the `delivery-token` control. Passed
unmodified before this audit touched anything.

### Brazilian Portuguese, on this screen's own reachable strings

Found while reading the `ingress.token.*` block for the surrounding context
of item 5's fix — not a repository-wide sweep. Three of the five strings
`DeliveryToken`'s labels render called the deployment "a implantação" where
64 other places across the same catalogue file, including two sibling
strings on this identical screen (`data.simulate.failed`,
`data.simulate.unreachable`), call it "o deployment":

```
pt-BR.ts:1006-1007  'ingress.token.shownOnce'
  '...a implantação guarda apenas um hash dele.' → '...o deployment guarda apenas um hash dele.'
pt-BR.ts:1008        'ingress.token.failed'
  'A implantação recusou a emissão.' → 'O deployment recusou a emissão.'
pt-BR.ts:1009-1010   'ingress.token.unreachable'
  'Não foi possível alcançar a implantação.' → 'Não foi possível alcançar o deployment.'
```

The last two are now copy-identical, word for word, to `data.simulate.failed`
("O deployment recusou a simulação.") and `data.simulate.unreachable`
("Não foi possível alcançar o deployment.") elsewhere in the same file —
the same sentence shape, applied to a different noun. This is not the
European/Brazilian dialect split prior confrontations in this series found
(`utilizador`/`usuário`, `equipa`/`equipe`, `Activ-`/`Ativ-`): "implantação"
is a legitimate Brazilian Portuguese word, not a europeanism. It is a
catalogue-internal consistency defect — one small, self-contained pocket
using the translated noun where the other 64 instances in this file,
including this screen's own siblings, keep "deployment" as a loanword.
Fixed on all three.

`ingress.title`/`ingress.body` (`en.ts:1127-1129`, `pt-BR.ts:1000-1002`), the
two remaining keys in the same `ingress.*` block, also read "esta
implantação" — but a repository-wide search
(`grep -rn "'ingress\.title'\|'ingress\.body'"` over `console/src` and
`console/tests`) found no call site for either key anywhere: they are
declared and never rendered, the same "declared but unreachable" shape 022
Detectors' and 024 Knowledge's confrontations already found and declined to
touch for the identical reason (nobody reads it, so it does not ship a
defect). Left alone, matching that precedent, rather than edited for
consistency's sake on content nothing displays.

No test in this repository asserts pt-BR wording for this screen, matching
what 024 Knowledge's, 033 Team Context's and 036 Administration's
confrontations already found for their own screens — `resolveLocale`
defaults every test to English and nothing here requests `pt-BR`. No failing
test could show this red first, and this report says that plainly rather
than inventing one.

## Verification

Console, from `console/`:

- `pnpm exec vitest run tests/unit/surfaces/data.test.tsx tests/unit/surfaces
  /data-copy.test.tsx tests/unit/surfaces/simulation.test.tsx tests/unit/
  surfaces/delivery-token.test.tsx tests/unit/surfaces/resend.test.tsx
  tests/unit/surfaces/ingress.test.tsx tests/unit/surfaces/transit-
  routes.test.ts` — run **before any change**: **7 files, 73 passed** —
  confirming items 2, 3, 4 and 5 by running them, not by trusting
  `controle.md`'s or the code's own comments.
- `pnpm exec vitest run tests/unit/surfaces/data.test.tsx` — after rewriting
  the delivery-tester assertion, **before** the fix: **1 failed | 27 passed
  (28)**, confirmed red for the reason quoted above (heading still read
  "Simulate", no purpose text anywhere). After the fix: **28 passed**.
- `pnpm exec vitest run tests/unit/surfaces/data.test.tsx tests/unit/surfaces
  /data-copy.test.tsx tests/unit/surfaces/simulation.test.tsx tests/unit/
  surfaces/delivery-token.test.tsx tests/unit/surfaces/resend.test.tsx
  tests/unit/surfaces/ingress.test.tsx tests/unit/surfaces/transit-
  routes.test.ts tests/unit/i18n` — **9 files, 97 passed**.
- `pnpm exec vitest run` (full unit suite) — **2017 passed (123 files)**,
  unchanged from the count at this `HEAD` before this audit (one existing
  test was extended in place, no new `it` block was added). One benign jsdom
  console line ("Not implemented: navigation to another Document") is the
  same pre-existing test-environment noise every prior confrontation in this
  series has recorded, not a failure. Re-run a second time after every edit
  in this confrontation (including the `pt-BR.ts` reformat and the
  `screens.json` edit): identical, **2017 passed (123 files)**.
- `pnpm exec tsc --noEmit` — clean, no output.
- `pnpm exec eslint src/surfaces/screens/data.tsx src/i18n/en.ts
  src/i18n/pt-BR.ts tests/unit/surfaces/data.test.tsx` — clean.
- `pnpm exec prettier --check` on the same four files plus
  `visual/screens.json` — `pt-BR.ts` needed `--write` once (line-wrap from
  the shortened `ingress.token.unreachable` string and the new
  `data.simulate.*` keys); the diff after reformatting is exactly the
  intended content change plus wrapping, confirmed by re-reading it and by
  re-running `tests/unit/surfaces/data.test.tsx`/`tests/unit/i18n`
  afterward (**52 passed**, unchanged). `--check` passed clean on all five
  files afterward.
- `make console-client-check` — clean; `git status` on `src/api/schema.ts`
  and `fixtures/contract/openapi.json` shows no diff (no backend contract
  changed — every change in this confrontation is console-only).
- `make console-build` — succeeded, all routes including `/data` compiled,
  run before every build-dependent gate below per the standing instruction
  that `console-visual` alone never rebuilds.
- `make console-budget` — stylesheet 24062/40960 bytes (58%), icon set
  10918/16384 bytes (66%), unchanged (no new token, no new icon).
- `make console-visual` — **2 failed (data-1440-light, data-320-light), 33
  passed**. Both diffs inspected directly
  (`test-results/screens-data-1440-light-matches-its-baseline-visual/
  data-1440-light-diff.png`): the diff shows exactly the expected,
  self-caused change and nothing else — the "What happens to it" column now
  reads "Test a delivery" plus the new purpose sentence in place of the bare
  "Simulate" heading, pushing the Receiver/Payload controls down by one
  line's height; every other pixel on the page is identical. Per
  instruction, **this baseline is not accepted here** — left for the
  orchestrator to review and recapture.
- `make console-e2e` — **84 passed (0 failed)**, across both Playwright
  projects (`behaviour`, 79; `first-day`, 5) — unchanged from the count
  recorded before this audit, confirming none of the five e2e tests that
  exercise `/data` (asserted by `data-testid`, never by the heading text
  this confrontation changed) were disturbed.
- `test-results/` and `playwright-report/` (both gitignored,
  `console/.gitignore:8-9`) were removed after every browser/contract run.

Python, from the repository root:

- `uv run python -m pytest tests/contract/console/test_console_visual_
  regression.py -q` — **1 failed, 2 passed**. The one failure,
  `test_the_untouched_baselines_still_match`, is the Python-side mirror of
  the visual gate above, failing on the identical, self-caused,
  already-inspected `data-1440-light`/`data-320-light` diff — not a second,
  independent failure.
- `uv run python -m pytest tests/contract/console/ -q` — **1 failed, 297
  passed in 324.29s**, the same single failure and nothing else — confirming
  every other console contract (shell/route table, design system, first-run,
  live layer, "is an API client" boundary, success criteria, surfaces,
  visual coverage, and the seeded-failure gate suite itself) still holds.
  `tests/contract/console/test_console_gate.py`'s own seeded-failure
  fixtures (which splice a broken file into the tree, assert the check
  fails and names it, then remove it) left no stray file behind — confirmed
  by `git status` immediately after the run.
- No Python file was changed by this confrontation, so `ruff`, `ruff
  format --check` and `mypy` were not run — nothing here would be scoped by
  them. The Python files this report cites
  (`gateway/http/routes/ingress.py`, `gateway/http/routes/transit.py`) were
  read to verify claims about the backend, not edited.
- `KNOWN PRE-EXISTING, not mine:`
  `tests/contract/integrations/test_integration_parity.py::
  test_each_paginated_endpoint_declares_a_style_the_base_client_walks
  [google_gemini]` was not re-run — no file this confrontation touched
  could affect it.

**On confirming new tests red first.** The one genuinely new assertion —
`data.test.tsx`'s rewritten delivery-tester test — was confirmed red against
the code exactly as it stood immediately before its own fix, in the words
quoted above, not inferred. Every other item (2, 3, 4, 5, and item 1's rule-
ruler half) needed no new test: the existing tests `controle.md` marked
`NÃO INICIADO` were *run*, not read, against the tree exactly as this
confrontation found it, and all 73 passed — the convention 021 Topology's,
023 Memory's, 024 Knowledge's, 031 Autonomy's, 033 Team Context's, 035
Agent's and 036 Administration's confrontations used for the same situation.
The two Brazilian-Portuguese corrections and the `screens.json` acceptance-
note correction had no failing test to show red first, and this report says
so rather than inventing one — matching what 024's, 033's and 036's
confrontations already reported for the identical situation on their own
screens.

## Control reconciliation

`specs_v4/037-data/controle.md` is rewritten so every row states the
verified status and points at this report. Items 2, 3 (its colour half), 4
and 5 move from `NÃO INICIADO` to `FEITO`: no functional code changed for
any of the four, only the verdict — all four were already built by commit
`1ef8dd6`, none of it reflected in the prior control file. Item 3 also
records a genuine, if non-functional, correction: the visual baseline's own
acceptance note in `visual/screens.json` still described the pre-fix "danger
tone" behaviour and is corrected here. Item 1 moves to `FEITO`, split into
what was already correct (the rule ruler) and what was genuinely built here
(the simulator's name and purpose, replacing a heading that reused one of
the two labels the bug names as inadequate). A closing note records: the
`ingress.token.*` "implantação"→"deployment" consistency fix, on this
screen's own reachable strings; the two unreachable `ingress.title`/
`ingress.body` keys, found while reading the same block, traced and left
alone because nothing renders them, matching 022's and 024's precedent for
the identical shape; the http:// URL's own architectural root cause (no
"public host" concept exists anywhere the console can read, and the
backend's own route already documents why it does not add one) traced to
the end and declined on that reasoning, not on avoiding the work, since the
current fallback already satisfies both of this item's acceptance criteria;
and the `RuleSimulator` "Save" button's missing handler, pre-existing since
this screen's original build and requiring a backend route that does not
exist, named for whichever confrontation next reaches this screen.
