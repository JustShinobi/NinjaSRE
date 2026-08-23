# 038 Audit — implementation confrontation

Date: 2026-08-14.

## Conclusion

`controle.md` drifted the same direction this series keeps finding: all five of
`spec.md`'s items were marked `NÃO INICIADO`, with no detail at all, and running
(not reading) `audit.test.tsx` against the unmodified tree showed **11 passing
tests** already covering behaviour the control file called untouched. Items 1
(burst grouping and the system/person split), 3 (single-option filters
suppressed) and 4 (the "SORT, SMALLEST FIRST" header leak, already fixed
screen-wide by `rows.tsx`'s `sortAction`, confirmed for this screen specifically)
were, on inspection, **already fully built**. Item 2's suggested fix — "Filtro de
período + paginação/virtualização" — was also already built in full: the period
presets exist, and `console/AGENTS.md`'s own documented architecture ("A long
list is windowed and a transcript is paged... Both say how many there are;
neither truncates silently") is exactly what `RowList` already does for this
screen, confirmed directly in its source. Item 5's `humanize()` for the action
column was likewise already built and tested.

The starting point this confrontation was handed by name — `AUDIT_EVENTS`'s
`actor_kind` serving `"person"`/`"machine"` against the real `ActorKind` enum's
`"user"`/`"token"`/`"agent"`/`"system"` — was verified directly against
`platform/persistence/ports/audit_repository.py:28-38`, confirmed real, and
fixed the way 036's confrontation fixed the identical shape for principals:
corrected at the one place it is declared (`tools/mockplane/dataset/served.py`),
every committed scenario rebuilt, and a new contract test
(`test_every_actor_kind_is_one_the_backend_actually_declares`) added beside the
principal-kind test it mirrors. The console was checked for branching on the
old strings and does not — `actor_kind` is not read anywhere in
`audit.tsx`, so no second half of that particular fix was needed on the
console side.

Tracing the real mapping for that fix (reading `platform/credentials/proxy/
audit.py`, `platform/approvals/appliers.py` and eleven other call sites that
construct a real `AuditEvent`) surfaced a **second, independent vocabulary
divergence in the exact same table**, not named by anyone before this: every
mock audit event's `outcome` field read `"succeeded"` — a word the real
`AuditOutcome` enum has never declared (its three values are `"allowed"`,
`"denied"`, `"failed"`). That divergence was not cosmetic. Investigating why
item 5's outcome column looked unstyled led to the two real defects the rest of
this report treats as its most substantial findings, both worse than anything
`spec.md`'s own text names:

- **Every real load of this screen would fail.** `audit.tsx`'s own
  `EVENT_LIMIT` was `500`, sent as the gateway's `limit` query parameter — but
  the real backend's `MAX_QUERY_PAGE_SIZE` is `200`, enforced by a repository
  method that *raises* rather than silently shortening the page
  (`platform/persistence/postgres/repositories/common.py:41-52`, mirrored in
  the in-memory fake, both already covered by an existing persistence contract
  test at `tests/contract/persistence/test_audit_repository.py:107-108`). A
  request for `500` is a `400 Bad Request` on every deployment this console
  will ever run against — this screen was not merely missing a "load more"
  affordance, it did not load at all. Fixed here, test-first, by capturing the
  actual outgoing request URL and pinning its `limit` to the gateway's own
  bound.
- **Every outcome badge on this screen rendered with the wrong colour.**
  `audit.tsx` fed the *humanised* outcome text into the shared status `Badge`,
  whose vocabulary lookup (`console/src/design/status.ts`'s `DECLARED` map) is
  case-sensitive and keyed by the raw, lower-case value every other screen's
  own status cell already passes unmodified (confirmed by reading
  `resources.tsx`, `runs.tsx`, `incidents.tsx` ×2 and `memory.tsx` — none of
  the other five humanises before a `kind: 'status'` cell). Combined with the
  mock's own invalid `"succeeded"` value and `DECLARED` never having entries
  for `allowed`/`denied` at all, every audit event's outcome — allowed, denied
  or failed alike — rendered as the generic, neutral "status this console has
  never heard of" chip, losing the exact colour distinction (danger red for a
  denial or a failure, success green for an allowed action) the design system
  exists to guarantee. Fixed here, test-first, in three places that all had to
  move together for the fix to actually be visible against the committed
  dataset: the screen (pass the raw value), the shared vocabulary (declare
  `allowed`/`denied`), and the mock data (`"succeeded"` → `"allowed"`, the
  identical defect shape as the `actor_kind` fix, in the identical table).

Two things were traced to the end and deliberately left alone, named rather
than silently dropped: item 1's own suggestion to record `credential.resolve`
as a counter rather than one event per call (a backend write-side change,
explicitly phrased as "review," and already substantially mitigated at the
read layer by burst grouping and the audience split); and item 5's fuller
"resolveu a credencial X para chamar Y" sentence composition, which would need
an open-ended, per-action translation catalogue this codebase has no
foundation for and which nothing in the stated acceptance criteria tests for.
A third, deeper question — whether a legal, `200`-row page can always contain
a human action from earlier today under genuinely extreme, sustained polling —
was traced to an architectural gap (`/audit/events` has no "exclude this
principal" query, only "match exactly this one") that only a new backend
capability, or the write-side volume reduction item 1's own text already
names, could close; building a bespoke pagination mechanism for this one
screen would run against this console's own documented convention that a long
list is windowed, not paginated, and is not demanded by the stated acceptance
bar. Three small Brazilian-Portuguese dialect corrections were made on this
screen's own catalogue block (`Acção`→`Ação` ×2, `acções`→`ações`); two wider,
cross-screen patterns found in the same block — `registado`/`registrado` (a
repeated empty-state heading idiom spanning about six screens) and the
`estar a + infinitivo` continuous construction 036's confrontation already
traced and declined to sweep even for its own screen — were named and left for
a dedicated catalogue-wide pass, for the same reason 036 gave.

## Table

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Ruído de máquina afoga ação humana | NÃO INICIADO | Wrong — already done. Consecutive identical events already collapse into one row with a count and a window (`groupBursts`); the system principal (`default`) is already excluded from the default reading, with a link naming how many events it hides. Both mechanisms were already tested and passed unmodified. | DONE (no change); the write-side "counter instead of event" idea considered and declined |
| 2. Sem período, sem paginação | NÃO INICIADO | Half wrong, half a genuine, more severe defect than named. Period presets and virtualisation (`RowList`'s windowing — this console's own documented answer to "a long list") were already built and tested. But `EVENT_LIMIT` (500) exceeded the gateway's own hard page bound (200): every real request to `/audit/events` would be refused with `400 Bad Request`, so the screen did not load at all against any real backend. | DONE — the pre-existing severe bug fixed here, test-first |
| 3. Filtros de única opção | NÃO INICIADO | Wrong — already done. A filter offering only one value is already left out of the filter bar entirely, tested for both the absent and the present case. | DONE (no change) |
| 4. Vazamento "SORT, SMALLEST FIRST" | NÃO INICIADO | Wrong — already fixed screen-wide, confirmed specifically for this screen's own sortable columns and catalogue entries. The same defect 020 Resources' own confrontation already found fixed for the whole console. | DONE (no change) |
| 5. Slugs por extenso | NÃO INICIADO | Half right, hiding a worse defect. The action column's `humanize()` was already built and tested. The outcome column fed that same humanisation into the shared `Badge`, breaking its case-sensitive vocabulary lookup — every outcome badge rendered as an unrecognised, neutral chip regardless of its real meaning, compounded by the shared vocabulary never declaring `allowed`/`denied` and the mock data itself carrying an outcome value (`"succeeded"`) the real `AuditOutcome` enum has never declared. | DONE — fixed test-first, across the screen, the shared design-system table and the mock data; the deeper "full sentence per action" idea considered and declined |

## Evidence and corrections

### The `actor_kind` divergence named by the prior confrontation — verified and fixed

Verified directly rather than taken on trust: `platform/persistence/ports/
audit_repository.py:28-38` declares `ActorKind` as exactly `USER = "user"`,
`TOKEN = "token"`, `AGENT = "agent"`, `SYSTEM = "system"`. `tools/mockplane/
dataset/served.py`'s `AUDIT_EVENTS` (pre-fix) spelled every one of its eight
records' `actor_kind` as `"machine"` (four records, all `AUTOMATION`'s) or
`"person"` (four records, `OPERATOR`'s and `REVIEWER`'s) — neither of which the
real enum has ever declared. Traced the correct mapping from real call sites
rather than guessed: `platform/credentials/proxy/audit.py:102` records every
`credential.resolve` line — the exact noisy action `spec.md`'s own text
names — as `ActorKind.AGENT`; `platform/approvals/appliers.py:241,301` and
`platform/guardrails/audit.py:106` likewise use `AGENT` for the autonomous
pipeline's own actions; `gateway/http/routes/identity.py:227`, `config.py:485`
and eleven further call sites use `ActorKind.USER` for a signed-in person's own
action. Given that, `AUTOMATION`'s four events (`investigation.start`,
`approval.request`, `investigation.finish` ×2 — all things the pipeline itself
does) map to `"agent"`; `OPERATOR`'s and `REVIEWER`'s four (`config.write`,
`approval.reject`, `token.create`, `identity.grant` — all things a signed-in
person does) map to `"user"`.

Checked, before touching anything, whether the console branches on the old
strings anywhere — it does not. `actor_kind` is declared on the wire type
(`console/src/api/schema.ts:2884`) but is never read by `audit.tsx`'s
`groupBursts`/`AuditGroup`, confirmed by reading the whole file: no field named
`actor_kind` appears anywhere in the row-building logic. The screen's own
`audience`/system-exclusion mechanism keys on `actor_id === 'default'`
(`SYSTEM_PRINCIPAL`, `audit.tsx:77`), not on `actor_kind`, so this vocabulary
fix changes no rendering path — no second half of the fix was needed on the
console side.

Fixed at the one place it is declared, the way 036's confrontation fixed the
identical shape for principals: `tools/mockplane/dataset/served.py:2022-2027`
(comment) and the eight records' `actor_kind` fields, now `"agent"` (four) and
`"user"` (four). Test-first: a new test,
`test_every_actor_kind_is_one_the_backend_actually_declares`
(`tests/contract/fixtures/test_dataset_contract.py:129-150`), mirroring
`test_every_principal_kind_is_one_the_backend_actually_declares`'s shape
exactly — reading the live `ActorKind` enum rather than a second, copied list
of allowed strings. Run against the unmodified generator, before `served.py`
was touched: **1 failed**, naming 40 offending records across the five
scenarios that carry non-empty audit data (`populated`, `degraded`,
`incident-live`, `restricted`, `scale` — eight records × five scenarios).
Confirmed red for the exact reason named. After the fix and
`uv run python -m tools.mockplane build`: **1 passed**, and only
`fixtures/scenarios/populated/audit-events.json` changed on disk — the other
four scenarios inherit `populated`'s data, matching 036's own note about this
exact fixture set.

### A second, independent vocabulary divergence in the same table — found and fixed

Tracing the real call sites above to confirm the `actor_kind` mapping also
surfaced `AuditOutcome` (`platform/persistence/ports/audit_repository.py:
41-46`): exactly three values, `ALLOWED = "allowed"`, `DENIED = "denied"`,
`FAILED = "failed"`. `AUDIT_EVENTS` (pre-fix) carried `"outcome": "succeeded"`
on seven of its eight records and `"outcome": "failed"` on the eighth —
`"succeeded"` is not a member of `AuditOutcome` at all; it is a `RunStatus`
value (`console/src/design/status.ts:24`, `succeeded: { role: 'success', ... }`
under "Runs"), copied onto the wrong record type. This is the same defect
shape as the `actor_kind` divergence, in the identical table, and it directly
undermines the outcome-badge fix described next: fixing only the console's
rendering would have left the committed dataset still serving a value neither
the old nor the new rendering logic could style correctly.

Fixed the same way: `tools/mockplane/dataset/served.py:2028-2030` (comment)
and the seven `"succeeded"` records' `"outcome"` fields, now `"allowed"`
(`"failed"` on the one already-correct record is untouched). The nested
`"detail": {"status": "succeeded"}`/`{"status": "failed"}` payloads on two of
these records were deliberately left alone — they describe the *investigation
run's own* status, a genuine `RunStatus` value, not the audit event's outcome,
and changing them would have introduced a defect rather than fixed one.
Test-first: a new test,
`test_every_audit_outcome_is_one_the_backend_actually_declares`
(`tests/contract/fixtures/test_dataset_contract.py:153-174`), mirroring the
same two tests above. Run against the unmodified generator: **1 failed**,
naming 35 offending records (seven `"succeeded"` records × five scenarios).
Confirmed red for the exact reason named. After the fix and a rebuild:
**1 passed**.

### 1. Machine noise drowns out a human action

Already correct, confirmed by running rather than reading. `groupBursts`
(`audit.tsx:144-178`) collapses a run of consecutive events sharing actor,
action, resource and outcome into one row carrying a count and the window it
spans — `audit.test.tsx`'s `'collapses consecutive identical events into one
row with a count'` and `'does not collapse events that are not actually
identical'` (both pre-existing) passed unmodified. The system principal
(`SYSTEM_PRINCIPAL = 'default'`, `audit.tsx:77`) is excluded from the default
reading unless an explicit `actor` filter is set or `audience=all` is chosen
(`audit.tsx:209-212`), with a link naming how many events it is hiding
(`audit-audience-toggle`, `:322-344`) — `audit.test.tsx`'s whole `'a human
action buried in polling noise'` block (5 tests, pre-existing) passed
unmodified.

`spec.md`'s third bullet — "review whether `credential.resolve` needs to be an
audit event per call, or a counter" — is a backend write-side question, framed
as a review rather than a requirement, and traced to
`platform/credentials/proxy/audit.py:97-113`'s `ResolutionAuditor.record`,
which writes one `AuditEvent` per resolution by design (its own module
docstring: "A refusal is audited as loudly as a success... a trail that
recorded only what worked would be a trail of the least interesting events").
Given the read-layer mitigations above already satisfy this item's own
acceptance bar ("rajadas idênticas não geram uma linha por evento"), changing
how often the platform *writes* this record is a distinct engineering decision
belonging to `platform/credentials/proxy/`, not to this screen — declined on
that reasoning, not to avoid the work.

No test was written for this item: every mechanism `controle.md` marked
`NÃO INICIADO` was run, not read, against the unmodified tree, and all of it
passed.

### 2. No period, no visible paging — mechanisms present, the screen itself was broken

**The period filter and virtualisation — already correct.** `PERIOD_PRESET_DAYS
= [7, 30]` (`audit.tsx:103`) builds two bounded-window tab links plus "Any"
(`audit.tsx:266-320`), tested by `'the period filter'`'s `'offers presets,
each pointing at a bounded window'`. `RowList` (`console/src/surfaces/
rows.tsx:162-199`) windows every long list this console has — `windowFor`,
`scrollTop`, `drawn = rows.slice(window.first, window.first + window.count)` —
and this is not a screen-local choice: `console/AGENTS.md:146-148` documents it
as the console's one answer to volume, in these words: "A long list is
windowed and a transcript is paged, and they differ because a row is a fixed
height by contract and a transcript entry is not. Both say how many there are;
neither truncates silently." The "how many there are" half is
`audit-truncated` (`audit.tsx:358-365`), reading `surface.showing` — the
identical mechanism `runs.tsx:170` already uses, not an audit-specific
invention. Given both halves of `spec.md`'s own suggested fix
("paginação/virtualização") are satisfied by this documented, shared
architecture, building a second, bespoke "load more" control for this one
screen would be inconsistent with the console's own stated convention rather
than an improvement on it.

**The screen's own request was illegal, and every real load would fail.**
`audit.tsx`'s `EVENT_LIMIT` (pre-fix) was `500`, sent verbatim as `?limit=500`
to `GET /audit/events` (`audit.tsx:190`). The real bound,
`MAX_QUERY_PAGE_SIZE` (`config/constants/persistence.py:87`), is `200`.
`platform/persistence/postgres/repositories/common.py:41-52`'s `check_limit`
and its in-memory-fake twin (`platform/persistence/fakes/state.py:87-102`)
both raise `BoundExceeded` — not clamp — for anything over that bound, with
their own comments naming why: "a caller that asked for 500 and received 200
has no way to tell that from there being 200." `gateway/http/errors.py:108`
maps `BoundExceeded` to HTTP `400`. This is not a theoretical gap:
`tests/contract/persistence/test_audit_repository.py:107-108`, an existing,
pre-audit test, already proves `uow.audit.query(limit=MAX_QUERY_PAGE_SIZE + 1)`
raises. A request for `500` is `301` over the bound — every real load of this
screen against a real deployment, or against the in-memory fakes any Python
test uses, would receive a `400` and render the panel's own error state rather
than the table. The mock server this console's own visual and end-to-end
suites run against does not replicate this validation, which is why nothing
caught it before.

Test-first: `audit.test.tsx`'s `'the period filter'` describe block gained
`'never asks the gateway for more events than its own page bound allows'`
(`audit.test.tsx:246-259`), capturing every address the test's `fetch` stub
was asked for and asserting the `/audit/events` call's `limit` parameter is
`≤ 200`. Run against the unmodified component:
`pnpm exec vitest run tests/unit/surfaces/audit.test.tsx` — **1 failed | 11
passed (12)**, `AssertionError: expected 500 to be less than or equal to 200`.
Confirmed red for the exact reason. Fixed at `audit.tsx:91` — `EVENT_LIMIT =
200`, with the comment explaining the bound rather than leaving a bare number
for the next person to raise again. After the fix: **12 passed**.

The residual question — whether a legal `200`-row page reliably contains a
human action from anywhere in the current day, against a deployment whose
polling volume is genuinely extreme and sustained — was traced to the end
rather than assumed answered. `/audit/events` (`gateway/http/routes/
audit.py:76-101`) filters *for* exactly one `actor_id`; it has no "exclude this
one" query, which is the same absence `audit.tsx`'s own docstring already
names ("there is no 'not this principal' query"). Closing that gap fully needs
either a new backend query capability or the write-side volume reduction
`spec.md`'s own item 1 already names as an option — both outside this screen's
own file, and neither demanded by the stated acceptance bar, which asks that a
human action be findable "mesmo com polling ativo," not that it survive an
unbounded volume with no period filter applied. Named here for whoever next
touches `/audit/events`'s own query capabilities.

### 3. Filters populated with a single value

Already correct, confirmed by running rather than reading. `audit.tsx:252-263`
filters the `actor` and `action` choices down to nothing when either offers
only one distinct value across the fetched page — `.filter((choice) =>
choice.options.length > 1)`. `audit.test.tsx`'s `'a filter populated with a
single value'` block (2 tests, pre-existing) — `'does not render Principal or
Action when neither offers a real choice'` and `'renders once there is a real
choice to make'` — passed unmodified. No change made.

### 4. The "SORT, SMALLEST FIRST" header leak

Already fixed, screen-wide, before this confrontation reached it — the same
defect 020 Resources' own confrontation already found fixed for the whole
console. `rows.tsx:95-97`'s `sortAction` interpolates the column name into the
accessible sort label (`surface.sort.ascending`/`.descending`,
`en.ts:313-314`, `'sort by {column}, smallest first'`/`'...largest first'`),
so the raw, columnless sentence `spec.md` quotes cannot recur on any screen
using `RowList` — confirmed this screen's own two sortable columns
(`occurred_at`, `action`, `audit.tsx:372-382`) are wired through the identical
`rowLabels()` builder (`labels.ts:96-103`) every other screen uses, with no
audit-specific override. No change made.

### 5. Slugs written out in full — action fixed already, outcome was worse than named

**The action column — already correct.** `humanize()` (`audit.tsx:113-119`)
turns `credential.resolve` into "Credential Resolve" and is applied to the
action cell (`audit.tsx:238`). `audit.test.tsx`'s `'shows the action and the
outcome as words rather than as machine slugs'` already asserted the action
half and passed unmodified.

**The outcome column — genuinely broken, worse than `spec.md`'s own
complaint.** `audit.tsx` (pre-fix) applied the identical `humanize()` to the
outcome and passed it to a `kind: 'status'` cell (`{ kind: 'status', text:
humanize(group.outcome) }`), which `rows.tsx:129-137`'s `CellValue` renders as
`<Badge status={cell.text} />`. `Badge` (`console/src/components/status.tsx:
90-106`) resolves that text through `statusPresentation`
(`console/src/design/status.ts:206-218`), which looks the value up in
`DECLARED` — a plain object literal keyed by the *raw, lower-case* strings
every other screen's own status cell already passes unmodified, confirmed by
reading all five other `kind: 'status'` call sites in the console
(`resources.tsx:338`, `runs.tsx:102`, `incidents.tsx:171-172`,
`memory.tsx:85` — none of them transforms the value first). `humanize("
allowed")` produces `"Allowed"`; `DECLARED`'s key is `"allowed"`; the
case-sensitive lookup misses, every time, for every outcome. Worse, `DECLARED`
had no entry for `"allowed"` or `"denied"` at all before this fix — only
`"failed"` existed, shared with `RunStatus` — so even passing the raw value
would have left two of the audit trail's three real outcomes unstyled. The
combined effect, confirmed against the (then also wrong) mock data: every
outcome badge on this screen, allowed, denied or failed alike, rendered as the
generic `role: 'neutral', shape: 'hollow-circle', known: false` chip —
`Badge`'s own doc comment describes this as reserved for "a status the console
has never heard of," which an audit event's own outcome should never be.

Test-first, in two files. `audit.test.tsx`'s `'a slug written out in full'`
block gained `'colours the outcome by the role the design system already has
for it'` (`audit.test.tsx:277-288`), asserting the outcome badge's
`data-role`/`data-known` attributes. Run against the unmodified component:
**1 failed**, `data-role="neutral"` where `"success"` was expected — confirmed
red. `status.test.ts` gained `'recognises the outcomes an audit event can
carry'` (`console/tests/unit/design/status.test.ts:90-99`), pinning
`statusPresentation('allowed')`/`('denied')` directly at the shared component's
own boundary, independent of the screen. Confirmed red by temporarily
reverting the two new `DECLARED` entries and re-running: **1 failed | 11
passed (12)**, the same `AssertionError: expected false to be true`
(`known` was `false`); restored immediately after.

Fixed in three places that all had to move together for the fix to be visible
against the committed dataset — the same lesson the `actor_kind` fix's own
coordinator-review correction already taught this series:

1. `audit.tsx:240-245` — the outcome cell now reads `{ kind: 'status', text:
   group.outcome }`, the raw value, matching every other screen's own
   convention, with a comment naming why the humanised form was wrong rather
   than leaving a silent regression risk for the next reader.
2. `console/src/design/status.ts:187-190` — two new `DECLARED` entries,
   `allowed: { role: 'success', shape: 'filled-circle' }` (the same shape
   `succeeded`/`approved`/`healthy` already use for a success role) and
   `denied: { role: 'danger', shape: 'square' }` (the same shape `failed`/
   `rejected` already use for a danger role).
3. The mock's own `outcome` vocabulary, corrected above.

`audit.test.tsx`'s own fixtures (`systemEvent`, `humanEvent`) were also
carrying the wrong wire shape — `outcome: 'ALLOWED'` (shouted, matching no
real enum value either) and, on `humanEvent`, `actor_kind: 'human'` (not a
member of `ActorKind`). Neither was exercised as a bug by the tests that used
them, because — before this fix — nothing in the component read `actor_kind`,
and the outcome comparison the pre-existing test made
(`toHaveTextContent('Allowed')`) matched regardless of case. Corrected to the
real wire values (`'allowed'`, `'user'`) while fixing the two tests above, so
this file's own fixtures no longer model a shape the real gateway never sends
— and the pre-existing assertion was updated from `'Allowed'` to `'allowed'`
to match, with a comment explaining that `Badge`'s own CSS, not a
pre-capitalised string, is what puts it in upper case on screen.

Run after all three fixes: `pnpm exec vitest run tests/unit/surfaces/
audit.test.tsx tests/unit/design/status.test.ts` — **24 passed**.

**The deeper "full sentence per action" idea — considered and declined.**
`spec.md`'s own suggested wording ("legendas curtas por ação... tornariam a
tela legível") is phrased conditionally, tagged `[polimento]` (the lowest of
this spec's own two priority tiers), and is not covered by any of the three
stated acceptance criteria. Building it would mean an open-ended, per-action
translation catalogue — `action` is a free-form string written by any
capability anywhere in the platform, not a closed enum this console could
exhaustively declare labels for, unlike `outcome`. The row's own columns
already surface the fact such a sentence would restate (the resource
identifier, in the Subject column) as a discrete field rather than folded into
prose. Declined on that reasoning — the base ask this item's own title names
("Slugs por extenso") is satisfied by `humanize()`, already built and now
verified to actually colour correctly too.

### Two vocabulary fixes need three files to actually fire — checked, not just fixed

Following the exact lesson the `actor_kind` fix's own coordinator-review
correction already recorded for this series: a rendering fix and a shared
vocabulary fix are both provable in isolation while the fixture data that
every browser test, every Python contract test and every operator looking at
the mock-plane demonstration deployment actually reads remains wrong. Both
fixes in this confrontation — the outcome-badge colour and the `actor_kind`/
`outcome` mock vocabulary — were verified together: `make console-visual`'s own
diff (below) shows the exact, expected pixel change against the committed
`populated` scenario, not merely against a hand-built unit-test fixture,
confirming the fix reaches the data every other check reads.

### Brazilian Portuguese, on this screen's own reachable catalogue block

Found while reading `audit.*` for the lines items 3 and 5 needed — not a
repository-wide sweep, the same scope every prior confrontation in this series
used for its own screen.

```
pt-BR.ts:1109  'audit.column.action': 'Acção'   → 'Ação'
pt-BR.ts:1113  'audit.filter.action': 'Acção'   → 'Ação'
pt-BR.ts:1116  '...Todas as acções com...'      → '...Todas as ações com...'
```

`Ação`/`ação` (Brazilian, no silent `c`) was already the catalogue's own
established spelling in five other places before this fix touched anything;
`Acção`/`acção` (European) appeared four times total, two of them on this
screen. The other two — `transcript.kind.guardrail` and `palette.group.
actions`/`dashboard.quickActions.title`/`proposal.title` — belong to the
shared transcript component and to Dashboard/Proposals respectively, none of
them reachable from this screen (`audit.tsx` renders no transcript and no
palette/dashboard copy), and are named here, not touched.

Two wider, cross-screen patterns were found in the same block and
deliberately left alone. `audit.empty.heading`'s "Nada foi **registado**" and
`audit.empty.body`'s "...está a **ver**" both belong to patterns that repeat
identically across many other screens rather than being local to this one:
`registado` (European spelling, no `r` before the ending) appears **nine**
times across at least six screens' own empty-state headings (`surface.none`,
`run.usage.empty.heading`, `incident.derivation.empty.heading`,
`topology.empty.heading` among them), against **five** instances of
`registrado` (Brazilian) elsewhere — genuinely close to a coin flip rather
than a clear, locally-correctable outlier, and fixing only this screen's copy
would make its heading disagree with several siblings that currently agree
with each other on the same idiom. `está a ver` is the identical `estar a +
infinitivo` continuous construction 036 Administration's own confrontation
already traced to at least eight instances spanning five other screens and
explicitly declined to fix even for its *own* single instance
(`admin.tokens.revokeCancel`'s "Deixar a funcionar"), reasoning that fixing
one in isolation "risked creating exactly the inconsistency 033's confrontation
was corrected for treating a sibling screen as out of scope." The same
reasoning applies here without needing to be re-derived: this screen's own
instance is named, added to the running list, and left for the dedicated
catalogue-wide pass 036 already deferred to.

No test in this repository asserts pt-BR wording for this screen, matching
what 024 Knowledge's, 033 Team Context's, 036 Administration's and 037 Data's
confrontations already found for their own screens. No failing test could show
these three corrections red first, and this report says so rather than
inventing one.

## Verification

Console, from `console/`:

- `pnpm exec vitest run tests/unit/surfaces/audit.test.tsx` — run **before any
  change**: **11 passed**, confirming items 1, 3, 4, and the action half of
  item 5, and item 2's period-filter half, by running them rather than
  trusting `controle.md`'s account.
- `pnpm exec vitest run tests/unit/surfaces/audit.test.tsx` — after adding the
  page-bound assertion, **before** the `EVENT_LIMIT` fix: **1 failed | 11
  passed (12)**, `expected 500 to be less than or equal to 200`, confirmed red
  for the reason quoted above. After the fix (`EVENT_LIMIT = 200`):
  **12 passed**.
- `pnpm exec vitest run tests/unit/surfaces/audit.test.tsx` — after adding the
  outcome-badge-role assertion, **before** the `audit.tsx`/`status.ts` fix:
  **1 failed | 11 passed (12)**, `data-role="neutral"` where `"success"` was
  expected, confirmed red. After the fix: **12 passed**.
- `pnpm exec vitest run tests/unit/design/status.test.ts` — with the two new
  `DECLARED` entries temporarily reverted: **1 failed | 11 passed (12)**,
  confirmed red (`known` was `false`). Restored immediately; re-run:
  **12 passed**.
- `pnpm exec vitest run tests/unit/design/status.test.ts tests/unit/surfaces/
  audit.test.tsx` — **24 passed**, both files together, after every fix.
- `pnpm exec vitest run tests/unit/i18n tests/unit/surfaces/audit.test.tsx` —
  **36 passed**, confirming the catalogue completeness/fallback tests hold
  with the three pt-BR corrections in place.
- `pnpm exec vitest run` (full unit suite) — run three times across this
  confrontation as fixes landed: **2019 passed (123 files)** after the
  `audit.tsx`/`status.ts`/`audit.test.tsx` fixes (net +2 over the 2017/122
  recorded by 037 Data's own confrontation at the `HEAD` this audit started
  from), then **2019 passed** again after the pt-BR dialect edit (confirming
  it broke nothing), then **2020 passed (123 files)** after adding
  `status.test.ts`'s own pinning test — net +3 over 037's baseline, matching
  the three genuinely new tests (the page-bound test, the outcome-role test in
  `audit.test.tsx`, and the outcome-role test in `status.test.ts`). One benign
  jsdom console line ("Not implemented: navigation to another Document") is
  the same pre-existing test-environment noise every prior confrontation in
  this series has recorded, not a failure.
- `pnpm exec tsc --noEmit` — clean, no output.
- `pnpm exec eslint src/surfaces/screens/audit.tsx src/design/status.ts
  src/i18n/pt-BR.ts tests/unit/surfaces/audit.test.tsx
  tests/unit/design/status.test.ts` — clean.
- `pnpm exec prettier --check` on the same five files — clean.
- `make console-client-check` — clean; `git status` on `src/api/schema.ts` and
  `fixtures/contract/openapi.json` shows no diff, confirming no backend
  contract changed (no route or response model was touched — every backend
  change in this confrontation is inside the mock data plane, not the
  gateway).
- `make console-build` — succeeded, all routes including `/audit` compiled,
  run before every build-dependent gate below per the standing instruction
  that `console-visual` alone never rebuilds.
- `make console-budget` — stylesheet 24062/40960 bytes (58%), icon set
  10918/16384 bytes (66%), unchanged (no new token, no new icon — `DECLARED`'s
  two new entries reuse existing shapes and roles).
- `make console-visual` — **34 passed, 1 failed**: `audit-1440-light`, 3050
  pixels (0.01 ratio). The diff image was inspected directly and shows the
  change confined exactly to the Outcome column across all eight visible
  rows — seven badges widen and recolour from neutral grey "SUCCEEDED" to
  green "ALLOWED", the eighth recolours from neutral grey to red "FAILED" at
  the same width — and nothing else on the page moved. This is the expected,
  self-caused consequence of the outcome-badge fix landing together with the
  corrected mock data; per instruction, **this baseline is not accepted
  here** — left for the orchestrator to review and recapture.
- `make console-e2e` — **84 passed (0 failed)**, across both Playwright
  projects (`behaviour`, 79; `first-day`, 5) — unchanged from the count every
  recent confrontation in this series has recorded, confirming neither the
  `EVENT_LIMIT` fix nor the outcome-badge fix disturbed any flow the suite
  already walks (none of the 84 tests exercises `/audit` by name).
- `test-results/` and `playwright-report/` (both gitignored,
  `console/.gitignore:8-9`) were removed after every browser run.

Python, from the repository root:

- `uv run python -m pytest tests/contract/fixtures/test_dataset_contract.py::
  test_every_actor_kind_is_one_the_backend_actually_declares` — run **before**
  `served.py` was touched: **1 failed**, naming 40 offending records across
  five scenarios — confirmed red for the exact reason. After the fix and
  rebuild: **1 passed**.
- `uv run python -m pytest tests/contract/fixtures/test_dataset_contract.py::
  test_every_audit_outcome_is_one_the_backend_actually_declares` — run
  **before** `served.py`'s outcome fields were touched: **1 failed**, naming
  35 offending records — confirmed red. After the fix and rebuild:
  **1 passed**.
- `uv run python -m pytest tests/contract/fixtures/ -q` — **104 passed**
  (102 recorded at the end of 036 Administration's own confrontation, +2 for
  the two new tests here), including
  `test_rebuilding_the_dataset_reproduces_what_is_committed` and
  `test_two_builds_of_one_scenario_are_byte_identical`, confirming the rebuild
  this confrontation ran is itself stable and reproducible.
- `uv run python -m pytest tests/contract/persistence/
  test_audit_repository.py tests/contract/persistence/
  test_audit_append_only_trigger.py -q` — **7 passed, 4 skipped** (the skips
  need a real PostgreSQL instance, not present here — the append-only
  guarantee this confrontation's own `EVENT_LIMIT` finding leans on is
  database-enforced and untouched by anything in this change).
- `uv run python -m pytest tests/contract/console/ -q` — **1 failed, 297
  passed** (315.53s). The one failure,
  `test_console_visual_regression.py::test_the_untouched_baselines_still_match`,
  is the Python-side mirror of the visual gate above, failing on the
  identical, self-caused, already-inspected `audit-1440-light` diff — not a
  second, independent failure.
- `uv run ruff check`, `uv run ruff format --check` and `uv run mypy` on the
  two Python files this confrontation changed (`tools/mockplane/dataset/
  served.py`, `tests/contract/fixtures/test_dataset_contract.py`) — all
  clean.
- `KNOWN PRE-EXISTING, not mine:`
  `tests/contract/integrations/test_integration_parity.py::
  test_each_paginated_endpoint_declares_a_style_the_base_client_walks
  [google_gemini]` was not re-run — no file this confrontation touched could
  affect it.

**On confirming new tests red first.** Every genuinely new assertion — the
two new fixture-contract tests, `audit.test.tsx`'s page-bound test and its
outcome-role test, and `status.test.ts`'s outcome-role test — was confirmed
red against the code exactly as it stood immediately before its own fix, in
the words quoted above, not inferred; `status.test.ts`'s own test required
temporarily reverting the just-applied `DECLARED` entries to prove it
independently, which was done and then immediately restored. Items 1, 3 and 4,
the period-filter and virtualisation halves of item 2, and the action half of
item 5 needed no new test: the existing tests `controle.md` marked `NÃO
INICIADO` were *run*, not read, against the tree exactly as this confrontation
found it, and all of them passed — the convention every confrontation in this
series from 021 Topology onward has used for the same situation. The three
Brazilian-Portuguese corrections had no failing test to show red first, and
this report says so plainly rather than inventing one, matching what 024's,
033's, 036's and 037's confrontations already reported for the identical
situation on their own screens.

## Control reconciliation

`specs_v4/038-audit/controle.md` is rewritten so every row states the verified
status and points at this report. Items 1, 3 and 4 move from `NÃO INICIADO` to
`FEITO`: no code changed for any of the three, only the verdict. Item 2 moves
to `FEITO` with the detail that its own suggested mechanisms (period filter,
virtualisation) were already fully built, but the screen carried a severe,
independent bug — `EVENT_LIMIT` exceeding the gateway's own page bound, making
every real load fail with `400 Bad Request` — found and fixed in this pass,
test-first. Item 5 moves to `FEITO`, split into what was already correct
(spelling the action out) and what was genuinely broken and fixed here (the
outcome badge's colour, across the screen, the shared design-system
vocabulary, and the mock data). A closing note records the `actor_kind`
vocabulary fix handed to this confrontation by name, the second, independently
found `outcome` vocabulary divergence in the identical table, the two new
contract tests pinning both against the real backend enums, the three
Brazilian-Portuguese corrections made on this screen's own catalogue block,
and everything traced to the end and deliberately left alone: the write-side
"counter instead of event" idea for `credential.resolve` (item 1), the deeper
per-action sentence composition (item 5), the residual volume-adequacy
question for a legal `200`-row page (item 2, needing a backend capability that
does not exist), the `registado`/`registrado` split and the `estar a +
infinitivo` construction (both wide, cross-screen patterns matching what 036's
own confrontation already declined to sweep), and the four `Acção`/`acção`
instances left on other screens' own blocks.
