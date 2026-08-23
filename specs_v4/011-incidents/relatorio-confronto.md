# 011 Incidents — implementation confrontation report

Audit date: 2026-08-13
Specification: `specs_v4/011-incidents/spec.md`
Control list: `specs_v4/011-incidents/controle.md`

## Executive conclusion

| Item | State in control list | Evidence-based result | Conclusion |
|---|---|---|---|
| 1. Empty state explains why there are no incidents | **DONE** | The incidents screen reads detector coverage and setup state, distinguishes unknown coverage from zero coverage, and chooses the more specific cause first. A direct failed-detector-read regression test now covers the unknown branch. | **PASS**. |
| 2. Filters that only offer `Any` | **DONE** | State and severity choices are derived from actual incident values, blank values are discarded, and empty choices are removed before rendering. | **PASS**. |
| 3. Duplicate CTA in the accessibility tree | **DONE** | Both the `Panel` path and the shell's `EmptyStateLink` now render one real link for navigation actions. | **PASS as a console-wide invariant**. |
| 4. Preview of what an incident looks like | **DONE (wave 4)** | The empty incidents screen now exposes a “See an example incident” link to an in-console, explicitly static example showing status, detector, subject, and evidence. | **PASS**. |

The control-list snapshot was accurate about the missing preview before this
correction. The code and tests now support all four items; the preview is
deliberately illustrative and does not create or mutate a live incident.

## Item 1 — “The empty state does not explain the empty state”

### What the specification requires

With no enabled detector, the empty state must say that nothing is watching and
point to continuous observation. With enabled detectors and no incidents, it must
retain the normal reassurance. If setup is unfinished, setup should be named;
however, zero detector coverage is more specific and must win when both facts are
true. A detector-read failure must not be interpreted as zero detectors.

### Code evidence

- `console/src/surfaces/screens/incidents.tsx:102-110` reads incidents,
  `/v1/detectors`, and `readSetupState` in parallel.
- `console/src/surfaces/screens/incidents.tsx:122-126` counts only records with
  `enabled === true`; a detector read in `error` state becomes `null`, not `0`.
- `console/src/surfaces/screens/incidents.tsx:128-135` calls the watching cause
  before the setup cause. This implements the required specificity rule.
- `console/src/surfaces/emptiness.ts:63-69` returns the “nothing is being
  watched” cause only when the live count is zero, and links to `/detectors`.
- `console/src/surfaces/emptiness.ts:96-98` returns the first non-null cause.
- `console/src/surfaces/read.ts:43-55` converts an API or network failure into a
  panel error state; the incidents screen consequently does not turn a failed
  detector request into a false zero count.
- The supporting endpoints exist in the gateway: `/v1/detectors` is implemented
  at `gateway/http/routes/incidents.py:419-432`, and `/v1/setup/checklist` at
  `gateway/http/routes/first_run.py:120-145`.

### Tests and verification

`console/tests/unit/surfaces/incidents.test.tsx:144-245` covers:

- zero enabled detectors with unfinished setup: the watching cause wins;
- enabled detectors with unfinished setup: the setup cause wins;
- enabled detectors with completed setup and no incidents: the feature’s normal
  reassurance remains.

The same file now makes `/v1/detectors` return `503` and asserts that the empty
state keeps the neutral reassurance instead of saying “no detector is switched
on.” This pins the `unknown` branch directly to the feature rather than relying
only on the generic `panelRead` contract.

**Verdict: PASS.**

## Item 2 — “Filters that filter nothing”

### Code evidence

- `console/src/surfaces/screens/incidents.tsx:113-120` derives distinct,
  non-blank state and severity values from the incidents actually returned.
- `console/src/surfaces/screens/incidents.tsx:176-187` drops a filter choice when
  its options list is empty.
- `console/src/surfaces/filters.tsx:46-64` renders only the supplied choices;
  `Any` is added only alongside at least one real option.

This also preserves useful controls when there is one incident: the single state
or severity value is still actionable, so the control is not incorrectly removed.

### Tests and verification

`console/tests/unit/surfaces/incidents.test.tsx:247-278` verifies both sides:

- an empty incident list renders zero filter controls;
- one incident renders both `state` and `severity` controls.
- blank state and severity fields cannot manufacture a filter with no meaningful
  option.

**Verdict: PASS.**

## Item 3 — duplicate CTA in the accessibility tree

### Code evidence for the incidents flow

- `console/src/surfaces/panel.tsx:36-43` models a panel empty action as a
  navigation (`href`), not as a callback that has to be supplemented elsewhere.
- `console/src/surfaces/panel.tsx:173-187` passes that navigation to `EmptyState`
  as one `href` action.
- `console/src/components/state.tsx:32-34` makes `href` and `onSelect` mutually
  exclusive through `EmptyStateAction`.
- `console/src/components/state.tsx:72-93` renders exactly one anchor for an
  `href` action and exactly one button for an `onSelect` action.
- `console/src/surfaces/screens/incidents.tsx:202-222` uses the `Panel` path for
  the incidents empty state; it does not add a second CTA of its own.
- `console/src/shell/empty-link.tsx:28-33` now uses the same `href` action branch
  for the not-found screen, removing its previous hidden duplicate anchor.

### Tests and verification

- `console/tests/unit/components/state.test.tsx:165-203` verifies link-vs-button
  selection and the absence of the alternate role.
- `console/tests/unit/surfaces/incidents.test.tsx:281-291` verifies that the
  incidents empty state exposes the watching action once.
- Approvals and memory also use the shared `Panel` empty-state path, at
  `console/src/surfaces/screens/approvals.tsx:249-254` and
  `console/src/surfaces/screens/memory.tsx:149-167,201-212`.

`console/tests/unit/shell/session-route.test.tsx:255-271` now asserts that the
not-found helper exposes a link and no same-labelled button. The shared state
tests continue to cover the mutually exclusive `href`/`onSelect` action union.

**Verdict: PASS as a console-wide invariant.**

This also exposes checklist drift outside this feature: `specs_v4/013-approvals/controle.md:7`
still says its identical CTA item is **NOT STARTED**, even though the approvals
screen uses the corrected `Panel` path. `specs_v4/023-memory/controle.md:8` has
already recorded the shared fix as done. The code therefore contradicts the 013
control entry in the direction the audit was asked to check: an unmarked item is
actually implemented through shared infrastructure.

## Item 4 — preview of what an incident will look like

### What the specification requires

The operator in pre-alpha should be able to see an example through a link such as
“how an incident looks,” an example/screenshot in operator documentation, or a
demonstration incident.

### What exists

- The product has a real incident-detail screen at
  `console/src/surfaces/screens/incident-detail.tsx:38-85`, and the route is wired
  at `console/src/app/(shell)/incidents/[incidentId]/page.tsx`.
- The repository contains populated incident responses under
  `fixtures/scenarios/populated/incidents.json` and
  `fixtures/scenarios/populated/incident-detail.json`.
- The visual suite has an incident detail capture declared in
  `console/visual/screens.json:214-221`, plus visual assets under
  `console/visual/mockups/` and `console/visual/baselines/`.
- The backend can explicitly seed a demonstration deployment through
  `gateway/http/routes/first_run.py:256-279`; the seeder writes incident rows and
  timeline entries in `platform/startup/demo/seeder.py:568-623`.

### Correction now present

- `console/src/surfaces/screens/incidents.tsx:188-210` adds a discoverable link
  from the empty panel to the example, and `:260` renders it only when the
  incidents request is ready and contains no records.
- `console/src/surfaces/screens/incidents.tsx:52-95` renders the example with
  critical/open status, detector, subject, evidence, and a clear explanatory
  sentence that it is not live.
- The English and Brazilian Portuguese catalogues add the preview copy at
  `console/src/i18n/en.ts:614-624` and `console/src/i18n/pt-BR.ts:527-537`.
- `console/tests/unit/surfaces/incidents.test.tsx:215-226` verifies both the
  anchor target and the example content.

The existing fixture and demo-seeder artifacts remain useful for development and
visual testing, but the user-facing requirement is now satisfied without
creating a real incident or requiring a write-capable demo action.

**Verdict: PASS after correction.**

## Verification performed

The following checks were run after the correction:

- Incident and shell regression tests: 2 files, 29 tests passed.
- Shared state/panel/screen/catalogue tests: 4 files, 116 tests passed.
- Console TypeScript check: `pnpm exec tsc --noEmit` passed.
- Relevant console ESLint checks passed, including the catalogue literal rule.
- Incident gateway route tests: 14 tests passed with
  `uv run pytest -q tests/unit/gateway/http/test_incident_routes.py`.

At the first worktree inspection, `.claude/` was the only untracked path and was
not modified. During the audit, unrelated modifications appeared in the console
shell, first-run/tutorial, dashboard, and their tests. They are outside this
audit and were preserved without edits or reverts; the final worktree status is
the authority for their exact paths.

## Remaining notes

1. The preview is intentionally a static, non-live example. A future product
   decision could expose a supported demo deployment with persisted timeline data,
   but that is separate from this empty-state requirement and would need an
   explicit write/rollback policy.
2. The shared CTA correction also resolves the identical stale item in the
   approvals flow; `specs_v4/013-approvals/controle.md` should be reconciled with
   that evidence in its own audit.
