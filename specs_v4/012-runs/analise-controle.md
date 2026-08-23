# Implementation audit — 012 Runs / Investigations

## Conclusion

The initial audit found that `specs_v4/012-runs/controle.md` overstated
completion in four places: the product vocabulary was still mixed, the subject
had no tooltip, the trigger was rendered as a raw slug, and the translated
failure title was repeated on the detail page.

A follow-up correction has now implemented those four gaps. The original audit
evidence below is retained as a before-correction snapshot; the closure status
and validation are recorded in the next section.

The audit treats the status in controle.md as a claim to verify. It compares
the current working tree based on c512fae with both spec.md and the actual
tests. Uncommitted changes from another, unrelated shell/tutorial workstream
appeared while the audit was running; they are called out separately and are
not credited to item 012.

| Item | Control status | Audit verdict at initial audit |
|---|---|---|
| 1. One name for Runs / Investigations | FEITO | **Partial** |
| 2. Subject before the hex ID | FEITO | **Partial** |
| 3. Subject is not an exception stack | FEITO | **Confirmed for the runs list and detail** |
| 4. Sort-label leakage | FEITO | **Confirmed for the reported defect** |
| 5. Trigger: interactive | FEITO | **Not implemented** |
| 6. Detail page header | FEITO | **Confirmed structurally; affected by item 5** |
| 7. Repeated error on the detail page | FEITO | **Not implemented** |
| 8. Browser-tab title | FEITO | **Confirmed** |
| 9. Empty right-hand panels | FEITO | **Confirmed for the covered scenario** |

## Closure after correction

| Gap | Correction | Verification |
|---|---|---|
| Mixed Runs / Investigations vocabulary | Aligned the visible English and Portuguese catalogue copy across the Runs page, palette, search label, dashboard attention copy, live controls, and supporting detail text. | Catalogue and UI tests pass. |
| Missing subject tooltip | Added an optional complete-value title to the shared first-cell renderer and populated it from the translated investigation subject. | `rows.test.tsx` and `runs.test.tsx` assert the tooltip. |
| Raw trigger slugs | Added `console/src/surfaces/run-trigger.ts`, mapping current and legacy API values to localized labels in list cells, filters, and detail metadata while preserving raw filter values in the URL. | `run-trigger.test.ts`, `runs.test.tsx`, and `run-detail.test.tsx` assert the mapping. |
| Repeated translated failure title | Kept the subject in the page heading, changed the breadcrumb leaf to the run identifier, and omitted the summary headline when only technical failure text is available. | `run-detail.test.tsx` asserts exactly one translated headline and one raw technical value. |

Final validation after the correction:

- full console suite: 120 files, 1,926 tests passed;
- TypeScript typecheck passed;
- ESLint passed;
- Prettier check passed.

The unrelated working-tree changes described below remain separate and were not
used as evidence for this correction.

## Evidence by item

### 1. One name for Runs / Investigations — Partial

The main navigation and area title use **Investigations**, and the detail
breadcrumb is built from that area. However, the visible catalogue is still
mixed. The English palette says **Matching runs** and **Recent runs**, while the
runs catalogue still says **Every run** and **No runs yet**. The Portuguese
catalogue has the equivalent mixture of **Investigações** and **Execuções**.

Evidence: [English palette labels](../../console/src/i18n/en.ts#L251-L256),
[English runs strings](../../console/src/i18n/en.ts#L540-L560),
[Portuguese palette labels](../../console/src/i18n/pt-BR.ts#L328-L334),
[Portuguese runs strings](../../console/src/i18n/pt-BR.ts#L460-L479).

Therefore the top-level labels were aligned, but the claim that the vocabulary
was fixed “in the whole catalogue” is false. The identifiers runs and run in
routes and message keys are implementation details and are not, by themselves,
a defect.

### 2. Subject before the hex ID — Partial

The list now puts the translated subject in the first cell and moves the ID to
an eight-character value in a later cell:
[row construction](../../console/src/surfaces/screens/runs.tsx#L81-L113).
The subject column is deliberately not sortable, as requested.

The remaining gap is in the acceptance text from spec.md: the subject is
truncated with CSS but has no tooltip or title exposing the complete value.
The shared row component only renders a plain truncated span:
[row rendering](../../console/src/surfaces/rows.tsx#L264-L281). There is also
no direct RunsScreen unit test for this behavior; the existing row tests test
the generic component with synthetic rows.

### 3. Subject is not an exception stack — Confirmed for runs list and detail

readFailure translates known failures, converts unknown raised exceptions to a
generic operator-facing headline, and keeps the raw text as technical detail:
[failure reader](../../console/src/surfaces/failures.ts#L67-L148). The list uses
the translated title for its subject
[here](../../console/src/surfaces/screens/runs.tsx#L89-L97), and the detail
keeps the raw value behind a disclosure
[here](../../console/src/surfaces/screens/run-detail.tsx#L184-L200).
The failure unit tests cover known, unknown, raw, and localized cases
([tests](../../console/tests/unit/surfaces/failures.test.ts#L20-L108)).

This conclusion is scoped to the runs list and detail. At HEAD, the command
palette also accepted raw run summaries as hints. The current worktree now has
an uncommitted safeRunHint path in
[commands.ts](../../console/src/shell/commands.ts#L76-L88) and
[searchCommands](../../console/src/shell/commands.ts#L112-L138), so that
palette path is currently sanitized when assembled. That separate change is
not part of item 012 and is not credited to it.

### 4. Sort-label leakage — Confirmed for the reported defect

The generic list now substitutes the column name into the accessible sort
action, exposes the direction through aria-sort, and shows an arrow for the
currently sorted column:
[sort implementation](../../console/src/surfaces/rows.tsx#L186-L237).
The catalogue uses sort by {column} / ordenar por {column} rather than the
previous column-independent announcement:
[English labels](../../console/src/i18n/en.ts#L286-L297),
[Portuguese labels](../../console/src/i18n/pt-BR.ts#L355-L365).

The exact reported SORT, SMALLEST FIRST leakage is gone. A residual wording
quality issue remains: “smallest/largest first” is not a particularly precise
description for lexical columns such as Status or Trigger, but it does not
invalidate the specific fix recorded in the control.

### 5. Trigger vocabulary — Not implemented

The list derives trigger options and cell contents directly from the API value,
with no display mapping:
[list trigger handling](../../console/src/surfaces/screens/runs.tsx#L59-L62)
and [row/filter rendering](../../console/src/surfaces/screens/runs.tsx#L98-L137).
The detail does the same in both its subtitle and metadata line:
[detail trigger rendering](../../console/src/surfaces/screens/run-detail.tsx#L130-L137)
and [summary metadata](../../console/src/surfaces/screens/run-detail.tsx#L202-L207).

The fixture data contains values such as alert, schedule, and manual
([runs fixture](../../fixtures/scenarios/populated/runs.json#L10-L55)). A
deployment returning interactive would therefore display interactive; a
deployment returning schedule displays schedule, not the requested
operator-facing “scheduled” label. The filter choices are raw as well.

There is no formatter or test asserting the requested mapping. This is a
concrete implementation gap, not merely missing documentation.

### 6. Detail page header — Confirmed structurally; affected by item 5

The detail no longer renders the list AreaHeader. It creates its own subject,
breadcrumb, and metadata subtitle, including relative start time, trigger,
duration, and cost:
[detail header construction](../../console/src/surfaces/screens/run-detail.tsx#L122-L167).
The list subtitle is therefore not reused. The trigger portion of that subtitle
is still raw because item 5 is missing.

### 7. Repeated error — Not implemented

The change removed the synthetic transcript report for a technical exception,
which is why the existing tests pass. It did not remove the other duplicate:
the same title is passed into the breadcrumb and the page header, and the
summary panel renders said.title again. The relevant paths are
[title and breadcrumb](../../console/src/surfaces/screens/run-detail.tsx#L122-L137),
[page header](../../console/src/surfaces/screens/run-detail.tsx#L152-L167), and
[summary panel](../../console/src/surfaces/screens/run-detail.tsx#L172-L200).

For InvestigatorNotConfigured, all of those values resolve to the same
translated headline. The raw exception appears once, but the acceptance
criterion is about the error text, not only the raw stack. The current test
only asserts that the raw value occurs once and that the transcript has no
synthetic report:
[existing regression tests](../../console/tests/unit/surfaces/run-detail.test.tsx#L80-L113).
It never asserts that the translated headline occurs once.

### 8. Browser-tab title — Confirmed

generateMetadata fetches the run, passes its summary through readFailure, and
uses the resulting subject in documentTitle, falling back to the run ID only
when the summary cannot be read:
[run metadata](<../../console/src/app/(shell)/runs/[runId]/page.tsx#L28-L54>).
This satisfies the browser-tab requirement and avoids exposing the raw
exception in the tab.

### 9. Empty right-hand panels — Confirmed for the covered scenario

The detail computes failedBeforeStart from a settled run with technical failure
text and no transcript events. In that case the cost and links panels stay in
the ready state and render one line without a navigation CTA:
[cost panel](../../console/src/surfaces/screens/run-detail.tsx#L307-L330) and
[links panel](../../console/src/surfaces/screens/run-detail.tsx#L444-L462).
The four detail tests cover raw-text uniqueness, no synthetic report, and both
collapsed panels
([test file](../../console/tests/unit/surfaces/run-detail.test.tsx#L80-L137)).

The evidence is scenario-specific: it does not establish behavior when the
replay read itself fails, but it does establish the requested early-failure
shape.

## Validation performed during the initial audit

The 012-related code was validated with:

- targeted Vitest run: 4 files, 24 tests passed;
- baseline full console coverage run: 118 files, 1,893 tests passed;
- coverage: 97.21% lines, 94.88% statements, 90.36% branches;
- TypeScript check: passed;
- ESLint over src and tests: passed.

The full-suite result is a baseline result. During the audit, unrelated shell
and tutorial source files plus six test files became modified in the shared
worktree; I did not edit or discard them. Re-running those six files in the
resulting worktree produced 26 failed and 134 passed tests, including failures
for unrelated tour, search, stop, and navigation changes. That state is
preserved and is not attributed to item 012.

At that green baseline, tests did not close the gaps above because there was
no direct RunsScreen test and the detail regression tests do not count the
translated headline.

## Closure work applied

1. Added one central trigger formatter and used it in list cells, filters,
   detail metadata, and tests for supported API slugs.
2. Made the page heading the sole owner of the translated failure headline and
   asserted its single occurrence in the rendered page.
3. Finished the visible vocabulary pass in the palette and supporting run copy.
4. Added a title for truncated subjects and a RunsScreen test covering subject
   translation, trigger labels, raw filter values, and the tooltip.

The untracked `.claude/` tree and unrelated implementation changes remain
preserved. Two existing test files also received the expectation updates
required by the vocabulary rename (`chrome.test.tsx` and `live/edges.test.tsx`);
no unrelated behavior was changed.
