# 025 Catalogue — implementation confrontation

Date: 2026-08-13

## Conclusion

Unlike several prior confrontations in this series, `controle.md` here was not
stale in the direction of understating finished work — reading
`console/src/surfaces/screens/catalogue.tsx` line by line, then running the
screen in a real browser, confirmed every one of its five `NÃO INICIADO` rows
and its one `PARCIAL` row before anything was changed. There was genuinely no
search box, no domain anchor, and no "N of Y enabled" count anywhere on the
page (item 2, correctly `PARCIAL` — the domain grouping it credits to earlier
work was real and unchanged, and it correctly named search and anchors as the
missing half). The literal string "Blocked by needs the" genuinely rendered,
traced to a two-layer construction: `platform/config_service/catalogue.py`'s
`refusal_for` composes a clause that already reads as a sentence
(`"needs the {integration} integration"`), and the console's own
`'catalogue.blocked': 'Blocked by {integration}'` template concatenated a
second phrase in front of it without knowing that (item 3). Every one of the
eighty-five credential forms genuinely rendered fully expanded, with "Every
required field needs a value" visible before any field had been touched,
because `CredentialField`'s own `missing` check is `true` at mount for any
form whose values start empty (item 4). And every integration's `health`
field genuinely could only ever be `healthy`, `degraded`, or `unknown` —
confirmed by reading `platform/observation`'s sibling package
`integrations/_catalogue/health.py` and the gateway route — with `unknown`
covering both "nobody has connected this" and "somebody connected this and
nobody has checked it" indistinguishably, which is exactly what `controle.md`
itself diagnosed for item 6 ("Depende do F5 — store de verificação — para ter
o que mostrar"). That diagnosis was correct: the fix needed new backend
plumbing, which this confrontation built.

All four of `spec.md`'s acceptance criteria hold now, each verified against
the rewritten screen rather than merely against the reading of the source
that produced it: a client-side search finds a tool or skill by name or
domain; every one of the eighty-five credential forms starts collapsed behind
a card that already says its real state without expanding anything, using a
new fourth value on the deployment's own health vocabulary
(`HealthStatus.UNCONFIGURED`) that distinguishes "no credential" from
"credential stored, never checked" for the first time; the string "Blocked by
needs the" no longer renders anywhere, confirmed by first reproducing it
verbatim against the unmodified code and catalogue string together, then
watching the fix remove it; and each integration's state — absent, stored,
verified, failing — is legible on the collapsed card. Item 5 (skills as a
"parede de prosa") is satisfied through the second of the two alternatives
`spec.md`'s own text offers ("Agrupar por domínio... **ou** tabela com
filtro"): skills are now a proper table section with one heading instead of a
repeated "Skills —" prefix on every row, and the same search box that finds a
tool finds a skill. The first alternative — grouping a skill under the same
domain heading as its matching tools — is not built, because
`gateway/http/routes/capabilities.py`'s `SkillView` does not expose a skill's
`domain` over the wire at all (only `name` and `description`); that is a
separate, undone backend gap, named below rather than silently worked around.
Item 1's own full fix — extracting Integrations into its own screen under
Settings, and "Not covered, and why" into a linked documentation page — is
not built either, and `spec.md`'s acceptance criteria explicitly accept that:
"Credenciais não aparecem na rota de catálogo (**ou, na correção mínima**,
ficam colapsadas com estado real por integração)" is satisfied by the second
branch, which items 4 and 6 now deliver. `controle.md`'s own note that the
full split "é a peça central da onda 3" already scoped this correctly as
later work, distinct from spec 090's redesign — it is named here again so it
is not lost, not re-litigated.

Two cross-tier root causes were chased and fixed at their actual source
rather than papered over in the console. Item 3's fix stays entirely in the
console: `console/src/surfaces/capability-rows.ts`'s own
`CapabilityRow.requiredIntegrations` already carries the structured list of
missing integrations, and `agent.tsx`'s `ToolGroup` — the *other* screen this
exact shared module's docstring says reads the same join — already prefers
that structured field over the raw `reason` clause
(`console/src/surfaces/screens/agent.tsx:879-883`). Catalogue never adopted
that pattern; it now does. Item 6's fix genuinely crosses tiers: a new
`HealthStatus.UNCONFIGURED` member
(`integrations/_catalogue/entry.py`), a new `configured` parameter on
`catalogue()` (`integrations/_catalogue/discovery.py`) that overrides the
verification ledger's answer when a credential was never even stored, and one
new line in `gateway/http/routes/integrations.py`'s `list_integrations` that
joins in `gateway/http/configured.py`'s `configured_integrations` — a
bulk vault read already used by the estate route for exactly this question,
reused rather than reinvented. Because `IntegrationView.health` was already
typed as a plain `str` rather than a constrained enum, this needed no
`openapi.json` regeneration and no client regeneration — confirmed by an
empty `git diff` on both after the change.

One thing surfaced by running the visual gate is worth stating plainly
because it looked, at first, like a false pass: `make console-visual` initially
reported the catalogue screen matching its baseline even though the screen
had been substantially rewritten. That was not a real pass — `scripts/visual.mjs`
serves a pre-built `.next/standalone/server.js`, which `console-visual` does
not rebuild, so the first run compared the *old* build against the baseline
and coincidentally matched it. Running `make console-build` first and
re-running the gate produced a genuine, expected failure on
`catalogue-1440-light`, and a real diff image confirming the new search box,
domain nav, count, "Requires the X integration … Connect it" link, and
collapsed integration cards render correctly. That same run also failed
`knowledge-1440-light` on a 466-pixel diff — traced to the diff image itself,
which shows the *exact* sentence 024 Knowledge's confrontation added to
`knowledge.proposals.lead` ("...in the same queue as every other proposed
change.") missing from the committed baseline PNG. That text is already in
`en.ts` at the current `HEAD`; nothing in this session touched
`knowledge.tsx` or any `knowledge.*` catalogue key. This is pre-existing
baseline drift from an already-accepted, already-committed confrontation
whose screen was never recaptured, not something this session caused —
confirmed reproducible on two separate runs with an identical 466-pixel
count, and left for the orchestrator exactly as instructed, alongside the
catalogue diff that is this session's own.

## Table

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Quatro telas numa rota | NÃO INICIADO — "peça central da onda 3" | Confirmed accurate: one route, two panels (Tools+Skills, Integrations), no separate `/integrations` screen, no linked doc page for "Not covered, and why". | PARTIAL — full structural split still not done (named, deferred, matches control's own scoping); the acceptance criterion's "correção mínima" alternative is now met via items 4 and 6 |
| 2. Sem busca/âncoras/sumário | PARCIAL (`bbd74a0`) — grouping done, search/anchors pending | Confirmed accurate: `groupedByDomain` existed and worked; no search input, no anchor, no count anywhere in the file. | DONE (fixed) |
| 3. "Blocked by needs the X integration" | NÃO INICIADO | Confirmed accurate. Reproduced the literal string against the unmodified component and the unmodified catalogue string together. Root cause traced to two tiers: `platform/config_service/catalogue.py`'s `refusal_for` clause and the console's own `'Blocked by {integration}'` template. | DONE (fixed, console-side only) |
| 4. 85 formulários sempre abertos | NÃO INICIADO | Confirmed accurate. `CredentialField` rendered unconditionally per integration with no collapse mechanism; `missing` is `true` at mount, so "Every required field needs a value" showed before any interaction on every one of them. | DONE (fixed) |
| 5. Skills como parede de prosa | NÃO INICIADO | Confirmed accurate. Skills rendered as `{name} \| "Skills — " + summary` rows, appended after every tool domain, ungrouped, unsearchable. | DONE via the "tabela com filtro" alternative; the "agrupar por domínio" alternative is not built (named, needs a backend field) |
| 6. Badge UNKNOWN sem explicação | NÃO INICIADO — "depende do F5" | Confirmed accurate, and the control's own diagnosis was correct: `health` could only ever be `healthy`/`degraded`/`unknown`, with `unknown` covering "never connected" and "connected but never checked" identically. No legend, no verify action on this screen. | DONE (fixed, genuinely cross-tier) |

## Evidence and corrections

### 1. Four screens on one route

`console/src/surfaces/screens/catalogue.tsx` (pre-session, read in full before
any change) rendered exactly two `Panel`s: one titled `catalogue.tools`
holding both the tools table and the skills rows, and one titled
`catalogue.integrations.title` holding, for every installed integration, an
always-open `CredentialField` plus the "Not covered, and why" essay at the
bottom of the same panel. No route named `/integrations` exists in
`console/src/shell/routes.ts`, and no documentation page carries the "known
gaps" prose. `controle.md`'s own note — "É a peça central da onda 3" — is
accurate: this is a genuinely larger restructuring (a new area, a new nav
entry under Settings, a permission boundary already partially expressed via
`may(viewer, MANAGE)`) than a polish pass, and `spec.md`'s problem statement
itself frames the full split as "detalhada na spec 090", not this one.

That said, `spec.md`'s own acceptance criterion for the credential half of
this problem is explicit about accepting less: "Credenciais não aparecem na
rota de catálogo (**ou, na correção mínima**, ficam colapsadas com estado
real por integração)." That second branch is what items 4 and 6 build below,
and it is fully met: credentials still live on `/catalogue`, but nothing
about a form is visible until an operator asks for it, and the real state is
legible before that. The row above is marked `PARTIAL` rather than `DONE`
because the *screen-split* itself — what problem 1 is actually about — is
still not done; conflating "the acceptance criterion's alternative is
satisfied" with "the item is done" would be exactly the kind of overstatement
this confrontation is supposed to avoid.

No test was written for this item specifically — there is nothing to pin
about an absence of a route that both `spec.md` and `controle.md` agree is
future work.

### 2. No search, no anchors, no summary

Confirmed absent before any change: `console/src/surfaces/screens/catalogue.tsx`
(pre-session) had no `Input`, no `<nav>`, and no computed enabled/total count
anywhere in its 326 lines — the whole interactive surface was
`groupedByDomain(tools)` rendered once, server-side, into a static table.

Fixed by extracting the whole tools-and-skills table into a new client
component, `console/src/surfaces/capability-browser.tsx`, which holds the
search query in local component state (`useState`, matching the same pattern
`console/src/surfaces/first-run/integrations.tsx`'s `IntegrationsStep` and
`console/src/surfaces/payload.tsx`'s `BoundedPayload` already use for a
filter or a disclosure that is not itself an address's own view — this is a
page-local interaction, not a "detail panel, filter, or sort" that the URL is
supposed to carry) and recomputes both the grouped table and the domain jump
list from the filtered set on every keystroke
(`capability-browser.tsx:104-133`). The count
(`catalogue.tsx:155-159`, `'catalogue.count': '{enabled} of {total} enabled'`,
pt-BR `'{enabled} de {total} habilitadas'` — matching `spec.md`'s own quoted
example, "14 de 233 habilitadas", almost verbatim) is computed once,
server-side, over the *whole* catalogue rather than the filtered view, so
typing into the search box narrows the table without the summary figure
moving underneath it — confirmed by
`catalogue.test.tsx`'s `'says how many of the whole catalogue are enabled,
unaffected by the filter'`.

Domain anchors: each domain heading row now carries an `id`
(`capability-browser.tsx:210`, `anchorId(domain)`, e.g. `#domain-estate`),
and a `<nav aria-label="Jump to a domain">` above the table lists one link
per domain still matching the filter, plus one for Skills when any remain
(`capability-browser.tsx:143-160`).

Test-first: `console/tests/unit/surfaces/catalogue.test.tsx`'s `'finding a
tool by name or domain'` block (6 tests) was run against the *unmodified*
`catalogue.tsx` (temporarily restored from `HEAD`, see Verification) before
any implementation existed: 5 of 6 failed —
`'narrows to the rows a search matches, by name'`,
`'…by domain'`, `'says how many…'`, `'offers an anchor per domain…'`, and
`'says plainly when nothing matches…'` all failed with
`TestingLibraryElementError: Unable to find a label with the text of: Find a
tool or skill by name or domain` or equivalent — confirmed red. The sixth,
`'shows every tool and skill with nothing typed'`, passed trivially against
the unmodified code, because rendering everything with no filter applied is
what the old, filter-less table already did; it is a regression guard going
forward, not a red-then-green pin, and this report says so rather than
counting it as one. After the fix, all 6 pass.

### 3. "Blocked by needs the X integration"

Root cause, traced across tiers rather than assumed: `tool.reason` is
`text(entry, 'reason')` off `/v1/config/{node_id}/catalogue`'s response,
which is `platform/config_service/catalogue.py:171-179`'s
`CatalogueView.of`:

```python
missing = tuple(
    required
    for required in description.required_integrations
    if required not in connected
)
if missing:
    reason = f"needs the {', '.join(missing)} integration"
```

That clause already reads as a sentence. The console's own catalogue entry,
`'catalogue.blocked': 'Blocked by {integration}'`
(`console/src/i18n/en.ts:1062`, pre-session), interpolated `tool.reason`
directly into `{integration}`, producing exactly "Blocked by needs the
datadog integration" for any blocked tool — the literal bug report. I did
not change `platform/config_service/catalogue.py`'s clause: it is also read
by `blocked_by_integration()` in the same file via a
`reason.startswith("needs the ")` check
(`platform/config_service/catalogue.py:209`), and changing the sentence's
shape there would have meant touching that check in the same edit — the
exact "check its siblings before declaring it done" risk this confrontation
was warned about — for a fix that does not need it.

The fix instead mirrors a pattern already shipped on the *other* screen that
reads this same join. `console/src/surfaces/screens/agent.tsx:879-883`'s
`ToolGroup` already prefers the structured `row.requiredIntegrations` over
the raw `reason` string:

```tsx
{message(locale, 'agent.tools.blocked', {
  integration:
    row.requiredIntegrations.join(', ') ||
    (row.reason === '' ? none : row.reason),
})}
```

`capability-rows.ts`'s own docstring says this directly: "the catalogue lists
it as a table and the agent screen groups it by risk" — two callers of one
join, and catalogue had simply never adopted the agent screen's own
resolution of the identical defect shape. `catalogue.tsx`'s new
`browsableTools` (`catalogue.tsx:63-104`) does the same: when
`row.requiredIntegrations.length > 0`, it renders
`catalogue.blocked` — now `'Requires the {integration} integration'`
(`en.ts:1066`), pt-BR `'Requer a integração {integration}'`
(`pt-BR.ts`, matching `spec.md`'s own suggested Portuguese wording verbatim)
— with a link, `catalogue.blocked.action` ("Connect it" / "Conectar"),
pointed at this node's own Configuration screen
(`configurationHref`, `catalogue.tsx:120-125`), the same
"link to where this is controlled, never a field-level anchor" idiom
`autonomy.tsx` and `agent.tsx` already use (named in 022 Detectors'
confrontation). When a tool is unavailable for a different reason — a team
disable, a disabled tag, neither of which starts with "needs the" — the raw
`reason` renders as-is, with no link
(`capability-browser.tsx:230-247`), since a general "go fix this in
Configuration" link is not obviously correct for every refusal shape and
`spec.md`'s fix is specifically about the missing-integration case.

The colour half of this item was already correct before this confrontation:
the blocked cell was already `text-meta text-muted`
(neutral), never a warning colour, so "reservar cor de alerta para
integração configurada que falha" was already true; only the grammar needed
fixing.

Test-first: `catalogue.test.tsx`'s `'why a tool is not available here'`
block. `'never renders the broken sentence the bug report quotes'` needed a
*double* revert to prove genuinely red — the first attempt (component
reverted, catalogue string left at its already-fixed value) passed trivially,
because the catalogue string itself had already been edited; reverting
`en.ts`'s `catalogue.blocked` line back to `'Blocked by {integration}'` *as
well* and re-running produced the actual reported bug —
`Blocked by needs the chat integration` in the failure output — confirmed
red for the right reason, not a confound. `'names the missing integration…
with a link…'` and `'shows a refusal that is not about a missing
integration…'` both failed against the unmodified component with
`Unable to find an element with the test id: capability-blocked` (the old
markup had no such test id at all). After the fix, all 3 pass, and the
double-revert / restore was itself verified byte-identical
(`diff` against a backup, see Verification).

### 4. Eighty-five always-open credential forms

Confirmed before any change: `console/src/surfaces/credential.tsx`'s
`CredentialField` (unchanged by this confrontation) computes
`missing = fields.some((field) => field.required && (values[field.name] ??
'').trim() === '')` — and `values` starts as `{}` on every mount, so
`missing` is `true` the instant the form renders, before a single keystroke.
`catalogue.tsx` (pre-session) rendered one `CredentialField` per installed
integration inside a plain `<li>`, unconditionally, with no expand
mechanism — so every one of the eighty-five forms an operator with three real
integrations would see was fully open with "Every required field needs a
value" visible on load, exactly `spec.md`'s complaint.

Fixed with a new client component, `console/src/surfaces/integration-card.tsx`'s
`IntegrationCard`: a collapsed `<li data-testid="integration">` showing the
name, a state `Badge`, and a toggle (`integration-card.tsx:55-105`); the
`CredentialField` and a `VerifyStep` (see item 6) render only inside a
`{expanded ? (...) : null}` block, with `expanded` held in local `useState` —
the same "disclosure widget, not a URL-addressable filter or detail panel"
category `BoundedPayload`'s own expand/collapse already establishes
elsewhere in this console.

Test-first: `catalogue.test.tsx`'s `'a credential form is collapsed until
asked for'` block. `'renders no credential form and no verify control before
anything is expanded'` and `'reveals the form and the verify control for one
card, and only that one, once expanded'` both failed against the unmodified
`catalogue.tsx` — the first because `screen.queryAllByTestId('credential')`
found four (one per integration, all open) instead of zero, the second
because there was no `integration-toggle` control to click at all
(`Unable to find an element by: [data-testid="integration-toggle"]`).
Confirmed red. After the fix, both pass, and expanding one card leaves the
other three collapsed (asserted by length, not just presence).

### 5. Skills as a wall of prose

Confirmed before any change: `catalogue.tsx`'s skill rows
(pre-session) rendered `{message(locale, 'catalogue.skills')} — {skill.summary}`
inside every skill's second cell — literally "Skills — " repeated on every
one of roughly a hundred rows, appended after every tool domain group with no
heading of their own, no domain relation, and no way to search them.

`spec.md`'s own fix offers two alternatives: "Agrupar por domínio junto às
tools correspondentes, **ou** tabela com filtro." The second is what is
built: skills are now their own table section, one heading
("Skills (N)") instead of a per-row repeated prefix
(`capability-browser.tsx:262-291`), and the *same* search box that filters
tools by name or domain also filters skills by name or summary
(`capability-browser.tsx:112-121`).

The first alternative — grouping a skill under the same domain heading as
its matching tools — is **not built**, and the reason is a genuine backend
gap rather than a console choice: `gateway/http/routes/capabilities.py`'s
`SkillView` (`capabilities.py:26-28`) declares only `name` and `description`;
`core.capability.metadata.CapabilityMetadata`'s shared `domain` field is
never read onto it, so `/v1/capabilities` never tells the console what
domain a skill belongs to at all, unlike a tool. `console/src/surfaces/capability-rows.ts`'s
`capabilityRows` (unchanged) reflects this honestly — it hard-codes
`domain: ''` for every skill rather than inventing one. Exposing a skill's
domain would mean adding a field to `SkillView` and reading it through, a
change to a third backend surface beyond the two already made for items 3
and 6; it is named here, not made, because nothing in `spec.md`'s acceptance
criteria requires the *domain-grouping* branch specifically once the
*table-with-filter* branch is delivered.

Test-first: `catalogue.test.tsx`'s `'skills are searchable and grouped, not a
wall of prose'` block. `'groups skills under their own heading rather than
repeating "Skills —" on every row'` failed against the unmodified code with
`no domain heading for skills` (there was no `data-testid="capability-domain"`
row for skills at all, only per-row repetition). `'is found by the same
search that finds a tool'` failed for the same reason item 2's search tests
did — no search input existed. Confirmed red for both. After the fix, both
pass.

### 6. UNKNOWN badge with no explanation

Confirmed before any change, across tiers rather than assumed:
`integrations/_catalogue/entry.py`'s `HealthStatus` (pre-session) declared
exactly three members — `HEALTHY`, `DEGRADED`, `UNKNOWN` — and
`integrations/_catalogue/discovery.py`'s `catalogue()` set `health` from the
verification ledger alone, defaulting to `UNKNOWN` whenever nothing had been
checked, *regardless of whether a credential existed at all*. Reproduced
directly: `tests/unit/gateway/http/test_verification_persistence.py`'s
`test_an_integration_nobody_checked_stays_unknown` (pre-session name) served
`health: "unknown"` for `prometheus` with **no credential ever stored** in
that test — the exact "todas dizem UNKNOWN" defect `spec.md` names, proven
by a test that was already in the repository asserting it as correct
behaviour. `catalogue.tsx` (pre-session) rendered `<Badge status={health}
/>` with no legend and no "Check it" action anywhere on this screen — the
verify control existed only on First Steps
(`console/src/surfaces/first-run/verify.tsx`'s `VerifyStep`).

Fixed across three files, joined by an already-existing helper rather than a
new one:

- `integrations/_catalogue/entry.py`: `HealthStatus` gains `UNCONFIGURED =
  "unconfigured"`.
- `integrations/_catalogue/discovery.py`: `catalogue()` and `entry()` gain an
  optional `configured: frozenset[str] | None` parameter. When given, an
  integration outside the set reports `UNCONFIGURED` with a fixed detail
  sentence, regardless of what the ledger holds; left unset (every existing
  caller), behaviour is unchanged — confirmed by
  `test_leaving_configured_unset_keeps_every_existing_caller_seeing_what_it_always_saw`.
- `gateway/http/routes/integrations.py`'s `list_integrations` now calls
  `gateway/http/configured.py`'s `configured_integrations(state, auth)` — a
  bulk, one-query vault read already used by the estate route for the
  identical question ("which integrations does this tenant hold a
  credential for") — and threads the result into `catalogue(...,
  configured=...)`.

Because `IntegrationView.health` was already typed `str` rather than a
constrained enum, this needed no OpenAPI regeneration: `git diff --stat
fixtures/contract/openapi.json console/src/api/schema.ts` is empty both
before and after.

Console side: `console/src/design/status.ts`'s `DECLARED` map gains
`unconfigured: { role: 'neutral', shape: 'dash' }`, its own shape rather than
reusing `absent`'s, so the Badge component renders it with a real role
instead of falling back to "unknown status" neutral text.
`IntegrationCard` shows, without expanding anything: the raw `Badge`, a
fixed legend sentence per state (`catalogue.credential.state.unconfigured` /
`.unknown` / `.healthy` / `.degraded`, `en.ts`, `pt-BR.ts`) that is the
"legenda" `spec.md` asks for, and the specific `health_detail` text when the
deployment supplied one (e.g. "verified 3 hours ago"). The verify action
`spec.md` asks for ("O teste de credencial deveria estar aqui também") is
built by *reusing* `VerifyStep` rather than inventing a second verify
control — one `<VerifyStep things={[{kind: 'integration', name, ...}]}
labels={...} />` per expanded card, sharing the exact `/api/verify` courier
and vocabulary First Steps already uses. That sharing needed
`labels.ts` to gain a `verifyLabels(locale)` builder (extracted from
`first-run.tsx`'s previously-inline object, same "one builder for both call
sites" pattern `credentialLabels` already documents for itself) —
`first-run.tsx` was refactored to call it too, so the two screens cannot
drift on the same sentence; `first-run.test.tsx`'s full 60 tests were run
after that refactor and stayed green.

Test-first, backend: `tests/unit/integrations/test_catalogue_configured.py`
(new file, 7 tests) run against the unmodified `catalogue()`: 5 of 6
substantive tests failed with `TypeError: catalogue() got an unexpected
keyword argument 'configured'`; the 6th
(`test_leaving_configured_unset_keeps_every_existing_caller_seeing_what_it_always_saw`)
passed trivially, as noted above — a regression guard, not a pin. The
7th (`test_the_single_entry_lookup_carries_the_same_parameter_through`) was
added after the fix to close a gap in symmetry (`entry()`'s new parameter had
no direct test); it did not need a red state because it was written after
the implementation existed, and this report says so rather than presenting
it as one. Test-first, route:
`tests/unit/gateway/http/test_integrations_credential_state.py` (new file, 3
tests): `test_an_integration_nobody_has_connected_reads_unconfigured` failed
against the unmodified route with `AssertionError: assert 'unknown' ==
'unconfigured'`, confirmed red; the other two
(store-then-read, verify-then-read) passed trivially against the unmodified
route, because storing and verifying a credential were already correctly
wired before this confrontation — only the *absence* case was wrong, and
this report says so rather than counting all three as pins.

A pre-existing test needed correcting rather than merely re-running, because
its own premise changed under it:
`tests/unit/gateway/http/test_verification_persistence.py`'s
`test_an_integration_nobody_checked_stays_unknown` served no credential at
all and asserted `health == "unknown"` — which was true under the old,
coarser vocabulary and is now correctly `"unconfigured"` under the new one.
Renamed to `test_a_configured_integration_nobody_checked_stays_unknown` and
given a credential first, so it now tests what its own docstring already
claimed to test ("a ledger that answered for everything would report a
guess as a measurement") rather than the different, more basic fact the new
vocabulary separates out; a new sibling,
`test_an_integration_nobody_has_connected_reads_unconfigured_not_unknown`,
covers the case the old test's name implied but its body never set up.

Test-first, console: `catalogue.test.tsx`'s `'a credential form is collapsed
until asked for'` block's `'shows every integration state without expanding
anything'` failed against the unmodified `catalogue.tsx` with
`TestingLibraryElementError: Unable to find an element with the text: /No
credential is stored/` (no legend existed at all). Confirmed red. After the
fix, it passes, asserting all four states (`unconfigured`, `unknown`,
`healthy`, `degraded`) render their own legend, and that `healthy`'s
specific `health_detail` ("verified 3 hours ago") renders alongside the
fixed legend rather than instead of it.

## Verification

Backend (Python), from the repository root:

- `uv run python -m pytest tests/unit/integrations/test_catalogue_configured.py
  tests/unit/gateway/http/test_integrations_credential_state.py` — run
  **before** the implementation existed: **6 failed, 3 passed (9)**,
  confirmed red for the six named above. After the fix: **9 passed**, then
  **10 passed** once the symmetry test for `entry()` was added.
- `uv run python -m pytest tests/unit/gateway/http/test_verification_persistence.py`
  — after correcting the pre-existing test and adding its sibling: **9
  passed**.
- `uv run python -m pytest tests/unit/gateway/http/` — **408 passed.**
- `uv run python -m pytest tests/unit/integrations/` — **526 passed.**
- `uv run python -m pytest tests/unit/platform/config_service/` — **340
  passed** (run separately from `gateway/http`; the two directories collide
  on an unqualified `conftest` import when collected in one invocation —
  confirmed pre-existing and unrelated by running each alone, both green).
- `uv run python -m pytest tests/architecture/` — **179 passed, 3 warnings**
  (a pre-existing `pytest.mark.parametrize` deprecation warning, unrelated).
  One run mid-session failed
  `test_exactly_one_fictional_deployment_exists_in_the_repository`, naming
  `console/playwright-report/` and `console/test-results/` — both gitignored
  artefacts this session's own `make console-visual` run had just written
  and which the check's exclusion list does not cover, the same shape of gap
  022 Detectors' confrontation already found for `specs_v4/`. Removed (`rm
  -rf`, both directories are listed in `console/.gitignore`, confirmed via
  `git check-ignore`), and the suite passed clean afterwards. Not fixed in
  the check itself: outside this spec's surface, named rather than silently
  worked around, same as 022's precedent.
- `uv run ruff check` and `uv run ruff format --check` on every changed
  Python file (`integrations/_catalogue/entry.py`,
  `integrations/_catalogue/discovery.py`,
  `gateway/http/routes/integrations.py`, and all three touched/added test
  files) — clean.
- `uv run mypy` on the same three source files — clean, no issues.
- `PYTHONPATH="$(pwd)" uv run lint-imports` — 7 contracts kept, 0 broken.
- `uv run python tools/check_constants.py` — clean.
- `uv run python tools/check_console_boundary.py` — clean.
- `git diff --stat fixtures/contract/openapi.json console/src/api/schema.ts`
  — empty both before and after the backend change, confirming no contract
  or client regeneration was needed (the field that changed shape is a
  plain `str`, not a constrained enum, in the Pydantic model).

Console, from `console/`:

- `pnpm exec vitest run tests/unit/surfaces/catalogue.test.tsx` — the whole
  file was run against the unmodified `catalogue.tsx` (temporarily restored
  from `HEAD` via `git show HEAD:... > catalogue.tsx`, with the new version
  backed up first and byte-diffed back afterward to confirm an identical
  restore): **12 failed, 2 passed (14)**. One of the two passes
  (`'never renders the broken sentence...'`) was itself re-checked with the
  catalogue string *also* reverted (see item 3), which flipped it to failing
  with the literal reported bug text, confirming the first pass was
  confounded rather than a real regression guard; the corrected red-check is
  what is reported above. After restoring the implementation: **14 passed**.
- `pnpm exec vitest run tests/unit/surfaces/first-run.test.tsx` — after the
  `verifyLabels` refactor: **60 passed**, matching the pre-refactor count.
- `pnpm exec vitest run tests/unit/i18n tests/unit/design tests/unit/gallery.test.tsx
  tests/unit/surfaces/first-run.test.tsx tests/unit/surfaces/agent.test.tsx`
  — **13 files passed, 328 tests passed.**
- `pnpm exec vitest run` (full unit suite) — **121 files passed, 1957 tests
  passed** (1943 before this session per 024 Knowledge's confrontation, +14
  — exactly `catalogue.test.tsx`'s own count, with no other file's test
  count changing). One benign jsdom console line ("Not implemented:
  navigation to another Document") is the same pre-existing
  test-environment noise every prior confrontation in this series recorded.
- `pnpm exec tsc --noEmit` — clean, exit 0.
- `pnpm exec eslint` on every changed/added file (`status.ts`, `en.ts`,
  `pt-BR.ts`, `labels.ts`, `catalogue.tsx`, `first-run.tsx`,
  `capability-browser.tsx`, `integration-card.tsx`, `catalogue.test.tsx`) —
  clean, including `no-untranslated-strings` and `no-design-literals`.
- `pnpm exec prettier --check` on the same files — four needed `--write`
  once (`en.ts`, `catalogue.tsx`, `integration-card.tsx`,
  `catalogue.test.tsx`); reformatted, then the full unit suite and the
  catalogue test file were re-run to confirm the reformat changed nothing
  behaviourally (both green), and `--check` passed clean on all files
  afterward.
- `make console-build` — a fresh standalone production build, run because
  `make console-visual` does not build for itself (see below).
- `make console-visual` — run **twice**. The first run, before rebuilding,
  reported **35 passed (35)**, which is not trustworthy evidence: traced to
  `console/scripts/visual.mjs:43` serving a pre-built
  `.next/standalone/server.js` that predates this session's changes, so the
  comparison was old-build-against-baseline, not new-code-against-baseline.
  After `make console-build`: **33 passed, 2 failed.**
  `catalogue-1440-light` failed as expected — this session substantially
  changed what the screen renders — and the diff image was inspected
  directly and shows exactly the intended new UI (search box, "4 of 5
  enabled", domain jump list, "Requires the metrics-store integration
  Connect it" with a real link, and three collapsed integration cards
  showing UNCONFIGURED/HEALTHY/DEGRADED with their own explanations and no
  open form). Per the explicit instruction, this baseline is **not**
  accepted here — left for the orchestrator to review and recapture.
  `knowledge-1440-light` also failed, on a 466-pixel diff reproduced
  identically on a second run; the diff image shows the exact sentence 024
  Knowledge's confrontation added to `knowledge.proposals.lead`, already
  present in the current `en.ts`, missing from the committed baseline PNG —
  pre-existing drift from an already-accepted confrontation, not caused by
  anything touched here (no file this session changed is imported by, or
  affects, `knowledge.tsx`). Also left for the orchestrator, named rather
  than silently worked around or accepted.

Not run: `make console-e2e`. A repository-wide search of
`console/tests/e2e/` for any reference to "catalogue" found none — no
existing browser test exercises navigation into or out of this screen, so
there is nothing this confrontation's changes could regress there, matching
the precedent 022 Detectors' and 024 Knowledge's confrontations set for the
same reasoning. `make test-postgres` — no file under `platform/persistence/`
was touched.

**On confirming new tests red first.** Every genuinely new behaviour in
items 2 through 6 was confirmed red by running its test against the code as
it stood immediately before that change, not inferred — including, for item
3, correcting an initially-confounded check by reverting a second file once
the first revert alone proved insufficient. The exceptions are named
individually above, in these words, rather than presented as pins: the
"shows everything with nothing typed" test (item 2), the "leaving
`configured` unset" backward-compatibility test and two of the three new
gateway-route tests (item 6, all three named explicitly), and the
`entry()`-symmetry test added after its implementation (item 6). Item 1
needed no test — nothing was built to pin an absence both `spec.md` and
`controle.md` already agree is future work.

## Control reconciliation

`specs_v4/025-catalogue/controle.md` is rewritten with six rows, one per
`spec.md` problem — the same count `controle.md` already had, so no row was
missing here the way 024 Knowledge's confrontation found one. Every row's
verdict changes from `NÃO INICIADO`/`PARCIAL` to `FEITO`, except item 1's,
which is corrected to `PARCIAL` with a precise account of what remains (the
route split itself) against what the acceptance bar's own alternative
already accepts (satisfied via items 4 and 6). A closing note records: the
`SkillView.domain` backend gap traced but not closed for item 5's first
alternative; the pre-existing Knowledge visual-baseline drift found while
verifying this confrontation's own catalogue baseline, left for the
orchestrator; and the stale-build false-pass this confrontation caught in
`make console-visual` itself, so the next confrontation in this series does
not have to rediscover that `console-build` has to run first.
