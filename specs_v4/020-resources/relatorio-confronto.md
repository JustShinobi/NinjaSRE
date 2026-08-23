# 020 Resources — implementation confrontation

Date: 2026-08-13

## Conclusion

The control file was almost entirely stale. It marked one item done and seven
as not started; reading the current source showed four of those seven already
satisfied their acceptance bar (the detail panel's position, the utilisation
column's conditional presence, the header/badge/filter/dashboard health
vocabulary, and the name filter), one was half done (the divergence mark had
already moved into its own column but explained nothing), and the sort
header's raw-word leak had already been fixed screen-wide by a shared
component. Two items were genuinely untouched: the malformed signal key and
the unexplained "Unplaced"/"Ungraded" jargon.

The malformed key (`lxc/HAL9000/unknown/111`) turned out not to be a console
bug at all. The console renders exactly what the gateway sends; the defect was
one property of a Proxmox guest's *internal* reconciliation identity —
`native_id`, which deliberately embeds the placeholder word `unknown` when a
guest's creation time cannot be read — leaking into a `SignalSource` field
declared as `keyed_by: "name"`. `_resolve_up` used the raw identity string
instead of the same name-resolution helper every other name-keyed entry uses.
Fixed at the source, in `platform/estate/signal_map.py`.

| Item | What the control claimed | What the code proved before this audit | Final status |
|---|---|---|---|
| 1. Click looks like it does nothing | FEITO (`bf5f055`) | Confirmed. Detail renders above the table, named, with a way back that preserves filters. Fully covered by `resource-detail.test.tsx`. | DONE (no change) |
| 2. Detail shows another resource's key (`lxc/HAL9000/unknown/111`) | NÃO INICIADO | Correct — untouched. Root cause traced to `platform/estate/signal_map.py`'s `_resolve_up`, not the console. | DONE (fixed) |
| 3. Dead Utilisation column | NÃO INICIADO | Wrong — already fixed. The column and its header are only drawn when at least one row in view has a reading (`resources.tsx:278`, `:339`, `:674`). Covered by `resources.test.tsx`. | DONE (no change) |
| 4. Health vocabularies that don't close | NÃO INICIADO | Wrong — already fixed. Header, badges, filter and dashboard all read `healthy`/`degraded`/`unhealthy` from the same `by_health`/`problems` breakdown; the dashboard tile is explicitly labelled "Degraded and unhealthy" so the union is named rather than implied. Covered by `resources.test.tsx` and `dashboard.test.tsx`. | DONE (no change) |
| 5. "(not in the inventory)" concatenated to the name | NÃO INICIADO | PARTIAL. Already its own column, no longer appended to the name cell — but plain muted text, no explanation of what the declared inventory is or what to do. | DONE (hint added) |
| 6. "Unplaced" / "Ungraded" jargon | NÃO INICIADO | Correct — untouched. No tooltip, no link. | DONE (fixed) |
| 7. No name search | NÃO INICIADO | Wrong — already fixed. A GET form with a `q` field, folded to lower case, round-tripped through the address like every other filter. Global search (spec 001) is a separate surface and stays out of scope. | DONE (no change) |
| 8. Orphaned "Worst first" / header leak | NÃO INICIADO | PARTIAL. The header leak ("SORT, SMALLEST FIRST") was already fixed screen-wide by `rows.tsx`'s `sortAction`, which interpolates the column name into the accessible label — nothing in this repository still emits the raw sentence. The "Worst first" label itself was still an orphan: no connection to the sortable columns beside it. | DONE (hint added) |

## Evidence and corrections

### 1. Click looks like it does nothing

Already correct. `console/src/surfaces/screens/resources.tsx:442-452` renders
the detail heading and back-link immediately after the filter bar and before
the table; `console/tests/unit/surfaces/resource-detail.test.tsx:58-69` asserts
the document-order relationship directly (`precedes(header, firstRow)`) rather
than trusting layout to imply it. No client state is involved — the panel's
presence is entirely a function of the `selected` query parameter, read by
`readViewState`. No change made.

### 2. Malformed signal key

Traced with `codegraph_explore` from the console's signal rendering
(`resources.tsx:477-486`, which renders `${keyed_by} ${key}` verbatim from the
API) back through the gateway to `platform/estate/signal_map.py`.

The "up" question's `SignalSource` was built with:

```python
keyed_by=SIGNAL_KEY_NAME,
key=resource.native_id or resource.resource_id,
```

`SIGNAL_KEY_NAME` (`config/constants/signals.py:82`) is documented as "the
resource's own name in the platform" — but `resource.native_id` is not a name.
It is the internal identity string a Proxmox discovery source builds for
cross-sweep reconciliation, in `integrations/proxmox/identity.py:56-58`:

```python
def guest_identity(cluster: str, kind: str, vmid: int, *, created_at: str) -> str:
    return f"{kind}/{cluster}/{created_at or NO_DISCRIMINATOR}/{vmid}"
```

`NO_DISCRIMINATOR` (`identity.py:38`) is the literal string `"unknown"`,
substituted when a guest's Proxmox configuration carries no creation
timestamp — which is common, not exceptional. For a container named `signoz`,
cluster `HAL9000`, vmid `111`, with no recorded creation time, this produces
exactly `lxc/HAL9000/unknown/111` — the string in the bug report. Reproduced
directly:

```
>>> signal_map_for(guest, configured=EVERYTHING).source_for(SIGNAL_QUESTION_UP)
SignalSource(question='up', integration='proxmox', keyed_by='name',
             key='lxc/HAL9000/unknown/111', ...)
```

This is deliberate design *for the identity string* — the docstring at
`identity.py:21-27` explains why a stable placeholder is preferable to an
invented one for reconciliation — but `native_id` was never meant to be shown
as a resource's "name". Every other name-keyed entry in the same module
resolves through `_key_for(SIGNAL_KEY_NAME, resource)`
(`signal_map.py:379-388`), which returns `resource.display_name or
resource.resource_id`; `_resolve_up` alone bypassed that helper and used the
internal identity string directly. That inconsistency is the actual defect —
the "either the panel shows the wrong binding or the key is malformed"
alternative the problem statement raised, and it is the second one.

Fixed in `platform/estate/signal_map.py:311` by resolving `_resolve_up`'s key
through the same `_key_for(SIGNAL_KEY_NAME, resource)` helper every other
name-keyed rule uses, instead of the raw `native_id`. `resource.native_id` is
never read again in that function.

Test-first: `tests/unit/platform/estate/test_signal_map.py:188-208`
(`test_up_is_keyed_by_the_resource_s_own_name_not_its_internal_identity`)
constructs a guest whose `native_id` carries the placeholder and asserts the
"up" signal's key is the resource's `display_name` and contains no `unknown`.
Confirmed red before the fix (`AssertionError: assert
'lxc/HAL9000/unknown/111' == 'signoz'`), green after. The existing
`test_up_is_answered_by_whatever_declares_the_resource_exists` only asserted
the integration name, so no prior test locked in the old behaviour.

No console file needed a change: it already renders whatever key the API
supplies, faithfully, per the "nothing here computes what the server
computes" rule in `console/AGENTS.md`.

### 3. Dead Utilisation column

Already correct, unrelated to the control's claim. `hasUtilisation`
(`resources.tsx:278`) is computed over the rows actually in view; both the
column header (`:674-681`) and the per-row cell (`:339-349`) are conditional
on it. `resources.test.tsx:149-179` covers both the absent-column case and the
present-with-a-real-reading case, including that an unread row inside a column
that does exist still reads "Not recorded" rather than a blank. No change
made.

### 4. Health vocabulary that doesn't close

Already correct, unrelated to the control's claim.

- Header: `resources.tsx:346-360` reads `by_health.healthy`,
  `by_health.degraded`, and `by_health.unhealthy` as three independent
  numbers (`resources.summary` in `i18n/en.ts:701-702`), rather than folding
  degraded and unhealthy into one figure.
- Badges: `{ kind: 'status', text: text(record, 'health') }` at
  `resources.tsx:338` renders the same raw health word the header counts —
  one source, not a second vocabulary.
- Filter: `resources.tsx:423-432` offers exactly `problem` (the union) plus
  every distinct health word the estate actually carries, via the same
  `PROBLEM_HEALTH = new Set(['degraded', 'unhealthy'])` (`resources.tsx:97`)
  the dashboard drill-down also targets.
- Dashboard: `dashboard.tsx:243` reads `summary.problems`, which the
  persistence contract already defines as degraded-or-unhealthy, and the tile
  is labelled `'dashboard.stat.degraded': 'Degraded and unhealthy'`
  (`i18n/en.ts:354`) — the union is named in the label rather than left for
  the reader to infer from arithmetic.

`resources.test.tsx:181-198` asserts the header's "degraded" count matches the
badges' breakdown rather than the combined `problems` figure. No change made.

### 5. "(not in the inventory)" concatenated to the name

Partially correct before this audit: the name cell already carries only the
name (`resources.tsx:294`, tested at `resources.test.tsx:200-213`), and the
divergence mark already has its own column (`resources.tsx:295-308`,
`:643-650`). What was missing was the "tooltip explaining what the declared
inventory is and what to do" the problem statement asks for — the cell was
plain muted text with no explanation.

Corrected by adding an optional `hint` to the shared `Cell` type
(`console/src/surfaces/rows.tsx:44-58`), rendered as a native `title`
attribute on the cell's content (`rows.tsx:126-158`) — the same mechanism the
first column already used for its truncation tooltip, extended to every
column rather than invented locally. The divergent cell now carries
`hint: message(locale, 'resources.divergent.hint')` when the resource
diverges (`resources.tsx:300-305`), whose text says what the declared
inventory is and states the two available actions — add it or ignore it —
without requiring a link, per the problem statement's own phrasing.

New keys: `resources.divergent.hint` in `console/src/i18n/en.ts:706-707` and
`console/src/i18n/pt-BR.ts:611-612`.

Test: `resources.test.tsx` (new `describe` block, "unexplained jargon gets a
tooltip and a way to fix it") asserts the divergent cell exposes a `title`
naming the inventory.

### 6. "Unplaced" / "Ungraded" jargon

Untouched before this audit, as the control claimed. Neither word had an
explanation or an action; `zoneOf`/`criticalityOf` in
`console/src/surfaces/screens/resources-view.ts` already correctly derive
"unplaced" (no declared network covers the address) and "" / ungraded
(nobody declared a criticality) — the gap was entirely in what the screen did
with those words.

Corrected using the same `hint` mechanism plus the new `href` field on `Cell`
(`rows.tsx:59-64`), which renders an anchor inside the cell independent of the
row's own link on the first column (`rows.tsx:140-150`) — so clicking
"Unplaced" or "Ungraded" no longer opens the resource, it goes to
`/configuration`, where zone and criticality attributes are declared, and
hovering explains why the word is there. Wired at
`resources.tsx:310-324` (zone) and `:325-337` (criticality); a declared zone
or criticality gets neither `hint` nor `href`, so the link only appears on the
placeholder value.

New keys: `resources.zone.unplaced.hint` and
`resources.criticality.ungraded.hint` in `en.ts:692-696` and
`pt-BR.ts:602-606`.

Test: the same new `describe` block in `resources.test.tsx` asserts both a
`role="link"` pointed at `/configuration` for the placeholder case and no
link at all when the value is declared.

### 7. No name search

Already correct, unrelated to the control's claim. `RESOURCE_FILTERS`
includes `'q'` (`resources.tsx:89-94`); the GET form at `resources.tsx:369-400`
carries every other filter as hidden fields so a typed name never drops a
zone or criticality already chosen; the query is folded to lower case at
`resources.tsx:238` and matched against `display_name` at `:255-256`.
`resources.test.tsx:235-259` covers narrowing, round-tripping the typed value,
and preserving other filters. No change made.

The other half of the problem statement — that the console's *global* search
does not find resources — belongs to spec 001 and is explicitly left alone:
it is a different surface (`src/shell/search.ts`), not this screen, and
touching it would be outside what spec 020 owns.

### 8. Orphaned "Worst first" / header leak

The header leak was already fixed, screen-wide, and unrelated to this
screen's own commits: `console/src/surfaces/rows.tsx`'s `sortAction`
(`:81-83`) interpolates the column's own header text into
`surface.sort.ascending` / `surface.sort.descending`
(`i18n/en.ts:302-303`: `'sort by {column}, smallest first'`), so the
accessible name reads "sort by Resource, smallest first" rather than the raw
sentence spec 012 flagged. A repository-wide search for the literal leaked
text (`SORT, SMALLEST FIRST` / `smallest first` in caps) found nothing outside
that one correctly-cased catalogue entry.

What remained was the "Worst first" label itself
(`resources.tsx:625-655`, `'resources.sorted'`): true to the problem
statement, it sat in the panel's action slot with nothing connecting it to
the sortable column headers beside it. Corrected by adding a `title` on the
same span, shown only while the default order is in effect, explaining that
it is the default and that a column heading changes it
(`resources.tsx:644-654`).

New keys: `resources.sorted.hint` in `en.ts:697-698` and `pt-BR.ts:608-609`.

Test: the same new `describe` block asserts the "Worst first" text carries a
`title` mentioning "column heading".

## Verification

Backend (Python):

- `uv run python -m pytest tests/unit/platform/estate/test_signal_map.py tests/unit/integrations/test_prometheus_resource_pressure.py tests/unit/gateway/http/test_resource_signals.py` — 37 passed. The new test was confirmed red
  (`AssertionError: assert 'lxc/HAL9000/unknown/111' == 'signoz'`) before the
  fix and green after.
- `uv run python -m pytest tests/unit/platform/estate/ tests/unit/gateway/http/test_estate_onboarding_routes.py tests/unit/gateway/http/test_resource_signals.py tests/unit/integrations/test_prometheus_resource_pressure.py tests/unit/integrations/test_proxmox_discovery.py` — 231 passed (blast-radius sweep of everything `signal_map_for` and `guest_identity` touch).
- `uv run ruff check platform/estate/signal_map.py tests/unit/platform/estate/test_signal_map.py` — clean.
- `uv run mypy platform/estate/signal_map.py` — clean.

Console:

- `pnpm exec vitest run tests/unit/surfaces tests/unit/screens` — 941 passed
  (70 files).
- `pnpm exec vitest run` (full unit suite) — 1931 passed (120 files). One
  benign jsdom console line ("Not implemented: navigation to another
  Document") is pre-existing test-environment noise, not a failure.
- `pnpm exec tsc --noEmit` — clean. One real error surfaced during this work:
  `exactOptionalPropertyTypes` rejected `hint?: string` assigned a value that
  could be `string | undefined`; fixed by typing both new `Cell` fields as
  `?: string | undefined`, matching the existing convention in
  `console/src/surfaces/changes.ts:48`.
- `pnpm exec eslint src/surfaces/rows.tsx src/surfaces/screens/resources.tsx src/i18n/en.ts src/i18n/pt-BR.ts tests/unit/surfaces/resources.test.tsx` — clean, including the project's `no-untranslated-strings` and `no-design-literals` rules.
- `pnpm exec prettier --check` on the same files — "All matched files use Prettier code style!"

Items 5, 6, and 8's new tests were written alongside their implementation
rather than confirmed red first. That gap was closed afterwards by the
orchestrator, independently: with `console/src/surfaces/screens/resources.tsx`
and `console/src/surfaces/rows.tsx` stashed back to their pre-change state and
the new tests left in place, `pnpm exec vitest run
tests/unit/surfaces/resources.test.tsx` reported **4 failed | 12 passed**. The
four failures are exactly the four new assertions — the inventory hint, the
zone hint and link, the criticality hint and link, and the sort label's
`title` (`Received: null` for each attribute). The implementation was then
restored and the file passes 16/16. Item 2's backend test was confirmed red
directly during the work, as required.

## Control reconciliation

`specs_v4/020-resources/controle.md` is updated so every row states the
verified status rather than the stale one, and points at this report. Five of
the seven rows the control marked NÃO INICIADO were wrong: three were already
fully done (3, 4, 7) and two were partially done (5, 8, header-leak half).
Only items 2 and 6 were genuinely untouched, and both are now DONE.
