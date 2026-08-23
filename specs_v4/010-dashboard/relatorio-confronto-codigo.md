# 010 Dashboard — Code Confrontation Report

Date: 2026-08-13  
Repository revision: `c512fae`  
Scope: [`controle.md`](/srv/workspaces/NinjaSRE/specs_v4/010-dashboard/controle.md:1), [`spec.md`](/srv/workspaces/NinjaSRE/specs_v4/010-dashboard/spec.md:1), the current console implementation, its tests, and the relevant API/data contracts.

## Executive verdict

The control file is directionally accurate, but it is too generous as a completion record. The current code contains the intended work; it is not a case where the items were merely checked off. However, four of the seven items still have material gaps or over-broad wording:

| Item | Verdict | Short conclusion |
|---|---|---|
| 1. Raw error as first reading | **Partially confirmed** | The raw exception is translated and hidden from the dashboard, but not every recognized failure has a First steps destination. |
| 2. Incomplete setup as the hero | **Confirmed, with coverage caveat** | The hero, seven-step plan, current step, single CTA, and removal after completion are implemented and tested. The first-load tutorial still overlays the page before dismissal, and there is no incomplete-state visual baseline. |
| 3. Numbers with a consistent story | **Partially done** | The visible drill affordance and detector explanation exist, but the healthy/degraded links point to a filter the Resources screen ignores, and the degraded number can use a different state vocabulary from its explanation. |
| 4. Agent KPIs | **Partially done** | Success rate is real, but the “last day” period is not enforced; MTTD and period cost/tokens are still absent. Not fabricating cost is correct, but it does not close the whole requirement. |
| 5. Vague quick actions | **Confirmed** | The active replacement uses each destination page’s title and context. |
| 6. “Estate health” is not health | **Confirmed** | The standalone inventory panel was removed, which is one of the two solutions explicitly allowed by the spec. |
| 7. Pluralisation and caps | **Partially done** | Pluralisation and the non-caps label are implemented, but “Waiting longest” is selected by array position rather than by the oldest timestamp. |

No item is wholly fictitious. The main problem is that “done” currently mixes a visible UI change with acceptance criteria that the code does not actually guarantee.

## Item-by-item confrontation

### 1. Raw error as the first reading

**What is genuinely implemented**

`readFailure` maps known configuration failures to operator-facing text and a First steps URL, and converts an otherwise raised camel-case exception into a generic operator message while retaining its technical text for the run-detail surface. The dashboard uses the translated title and action for a raised failure instead of putting the summary in the row title. See [`failures.ts`](/srv/workspaces/NinjaSRE/console/src/surfaces/failures.ts:67) and [`dashboard.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/dashboard.tsx:159).

The dashboard regression test verifies that `InvestigatorNotConfigured` and `NINJASRE_INVESTIGATOR` do not reach the dashboard DOM and that the row links to `/first-run?step=model` ([`dashboard.test.tsx`](/srv/workspaces/NinjaSRE/console/tests/unit/surfaces/dashboard.test.tsx:80)). The failure unit tests also cover an unknown `ZeroDivisionError` and the preservation of technical text ([`failures.test.ts`](/srv/workspaces/NinjaSRE/console/tests/unit/surfaces/failures.test.ts:34)).

**What the control overstates**

The statement “a recognized failure links to the pending First steps item” is broader than the implementation. `StoreUnavailable` and `MigrationsPending` are recognized by `failures.ts`, but deliberately have no `href`; the dashboard therefore falls back to `/runs/{id}` ([`failures.ts`](/srv/workspaces/NinjaSRE/console/src/surfaces/failures.ts:87), [`dashboard.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/dashboard.tsx:164)). The accurate claim is: *configuration failures with a known console remedy link to First steps; recognized operational failures without a console remedy link to the run*.

**Verdict: partially confirmed.** The acceptance requirement “no raw stack in the incomplete dashboard” is met, but the control should narrow its routing claim.

### 2. Incomplete setup as the hero

The implementation matches the stated behavior. `SetupHero` returns nothing once the checklist is ready and has no outstanding steps; otherwise it renders the complete seven-step plan, marks one current step, and exposes one CTA to that step ([`setup-hero.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/setup-hero.tsx:41)). The dashboard places it before the figures and explicitly removes the old side checklist ([`dashboard.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/dashboard.tsx:297)).

The tests verify seven rows, one current step, one CTA, absence after completion, and absence of the old duplicate checklist ([`dashboard.test.tsx`](/srv/workspaces/NinjaSRE/console/tests/unit/surfaces/dashboard.test.tsx:112), [`first-run.test.tsx`](/srv/workspaces/NinjaSRE/console/tests/unit/surfaces/first-run.test.tsx:927)).

There are two qualification points:

- On a fresh deployment, the tutorial is rendered before the dashboard content and is visible until skipped. The browser test explicitly checks that state, then checks the setup hero after dismissal ([`first-day.spec.ts`](/srv/workspaces/NinjaSRE/console/tests/first-day/first-day.spec.ts:60)). Thus “the hero is the first visual reading” is proven after the tutorial, not on the literal first paint.
- The four registered shell baselines cover `/` at 1440 dark/light, 320 light, and 768 light, but they are shell baselines rather than a dedicated incomplete-setup/hero baseline ([`screens.json`](/srv/workspaces/NinjaSRE/console/visual/screens.json:313)).

**Verdict: confirmed for the tested post-tutorial behavior; visual coverage is narrower than the control wording suggests.**

### 3. Numbers with a consistent story

**What is genuinely implemented**

`Figure` requires a destination and renders a visible arrow, not just the previous screen-reader-only affordance ([`figure.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/figure.tsx:48)). The degraded card explains the detector relationship in its context, and the focused test verifies the visible “14 of 14” bridge ([`dashboard.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/dashboard.tsx:328), [`dashboard.test.tsx`](/srv/workspaces/NinjaSRE/console/tests/unit/surfaces/dashboard.test.tsx:159)).

**Concrete acceptance failure**

The healthy and degraded cards emit `/resources?health=healthy` and `/resources?health=degraded` ([`dashboard.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/dashboard.tsx:317)). The Resources screen declares only `zone`, `criticality`, and `q` as filters ([`resources.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/resources.tsx:73)) and reads only those values. The shared URL-state parser drops undeclared parameters ([`url-state.ts`](/srv/workspaces/NinjaSRE/console/src/surfaces/url-state.ts:50)). Therefore those two links are clickable, but they do not lead to an already-filtered list. This directly fails the acceptance criterion in [`spec.md`](/srv/workspaces/NinjaSRE/specs_v4/010-dashboard/spec.md:78).

**State-vocabulary inconsistency**

The dashboard value called “Degraded and unhealthy” is `problems + unknown + stale`, while its explanatory context reports only `problems` ([`dashboard.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/dashboard.tsx:216)). The persistence contract deliberately defines only `DEGRADED` and `UNHEALTHY` as `is_problem`, excluding `UNKNOWN` and `STALE` ([`estate_repository.py`](/srv/workspaces/NinjaSRE/platform/persistence/ports/estate_repository.py:75)). With unknown or stale resources, the card value and its “open findings” explanation can disagree. This also leaves the dashboard vocabulary inconsistent with the health vocabulary called out in the resources specification ([`spec.md`](/srv/workspaces/NinjaSRE/specs_v4/020-resources/spec.md:30)).

**Verdict: partially done.** The presentation improvement is real; the drill-down contract and state arithmetic are not closed.

### 4. Agent KPIs

The dashboard now has a real success-rate figure calculated from settled and succeeded runs ([`dashboard.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/dashboard.tsx:234)); the test verifies the populated fixture’s 50% result ([`dashboard.test.tsx`](/srv/workspaces/NinjaSRE/console/tests/unit/surfaces/dashboard.test.tsx:178)). This satisfies the minimum acceptance requirement of having at least one agent indicator.

The control is correct that the list response does not carry cost or token totals: `InvestigationSummary` contains timestamps, status, summary, trigger, and ID, while `total_cost` and `total_tokens` exist on `RunReplayView` ([`schema.ts`](/srv/workspaces/NinjaSRE/console/src/api/schema.ts:4525), [`schema.ts`](/srv/workspaces/NinjaSRE/console/src/api/schema.ts:5761)). Avoiding one replay request per run is a sound reason not to manufacture a cost KPI in the dashboard.

Two material gaps remain:

- The run figure is labelled “Investigations in the last day”, but its value is simply `runRecords.length` and the success rate uses the same unwindowed collection ([`dashboard.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/dashboard.tsx:344)). The list contract says “recent runs”, not “runs from the last 24 hours” ([`schema.ts`](/srv/workspaces/NinjaSRE/console/src/api/schema.ts:2211)). No dashboard code compares `started_at` or `finished_at` to `now`.
- The original spec also asks for MTTD/time to diagnosis. There is no dashboard figure or computation for it. The control mentions only cost/tokens, so it understates the residual KPI debt.

The runs figure does at least provide a `/runs` destination, and the success-rate figure routes failures to `/runs?status=failed`; the Runs screen declares `status` as a supported filter ([`runs.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/runs.tsx:34)).

**Verdict: partially done.** Success rate is implemented and defensible; the complete period/KPI claim is not.

### 5. Vague quick actions

The active `DashboardQuickActions` component is a typed map of destination paths to each destination’s canonical title and context: `/knowledge`, `/autonomy`, and `/memory` ([`quick-actions.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/quick-actions.tsx:20)). The dashboard renders it, and tests verify three valid area links plus title/context content ([`dashboard.test.tsx`](/srv/workspaces/NinjaSRE/console/tests/unit/surfaces/dashboard.test.tsx:195)).

This item is **confirmed**. One naming detail matters for the later cleanup claim: the old vague component may be gone, but the current `quick-actions.tsx` file and `DashboardQuickActions` export are not dead code.

### 6. “Estate health” is not health

There is no standalone Estate health panel or `dashboard.estate.title` in the current dashboard test, and the dashboard no longer renders a by-kind side card ([`dashboard.test.tsx`](/srv/workspaces/NinjaSRE/console/tests/unit/surfaces/dashboard.test.tsx:210)). The summary remains legitimately used by the numeric figures, so this is removal of the misleading panel, not removal of estate data.

The original spec explicitly allowed the panel either to gain state information or to be removed ([`spec.md`](/srv/workspaces/NinjaSRE/specs_v4/010-dashboard/spec.md:67)).

**Verdict: confirmed.** Removal is a valid implementation of the requirement.

### 7. Pluralisation and caps

The dashboard passes the attention count through `formatCount`, and `AttentionBlock` displays the new `Waiting longest: {age}` wording without the old uppercase treatment ([`dashboard.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/dashboard.tsx:266), [`attention.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/attention.tsx:62)). The focused test verifies the badge’s casing, but not the source of its age ([`dashboard.test.tsx`](/srv/workspaces/NinjaSRE/console/tests/unit/surfaces/dashboard.test.tsx:227)).

The calculation is currently:

```ts
const oldest = attention[attention.length - 1];
```

It does not compare `requested_at`, `proposed_at`, `opened_at`, or `started_at`. Because attention rows are appended in groups by source, the label is correct only when the last appended row also happens to be the oldest. The populated fixture can make that look correct without proving the invariant.

There is a second, lower-severity coupling: the dashboard does not filter proposals by state, whereas approvals and incidents are filtered locally. The current gateway makes this safe by returning `queue.pending(...)` from `/v1/proposals` ([`proposals.py`](/srv/workspaces/NinjaSRE/gateway/http/routes/proposals.py:239)), so this is not an observed current mismatch; it is an implicit API dependency rather than a complete local guarantee.

**Verdict: partially done.** The copy and pluralisation are fixed; the semantic “oldest” calculation still needs a test and timestamp comparison.

## Acceptance criteria cross-check

| Acceptance criterion from `spec.md` | Current result |
|---|---|
| Incomplete setup is dominated by completion path and no raw stack is verbatim | **Mostly passes.** Unit and browser tests cover the hero after tutorial dismissal and absence of the raw exception. Literal first paint is covered by the tutorial overlay, not by a hero baseline. |
| Every numeric card has visible affordance and reaches an explanatory, pre-filtered list | **Fails.** Visible arrows and links exist, but `health=healthy/degraded` is discarded by Resources. |
| At least one agent indicator exists | **Passes.** Success rate is calculated and displayed. |
| Complete/healthy page shows recent activity and starter actions | **Partial/ambiguous.** The activity feed and `/runs` figure are present; the Quick actions panel itself offers knowledge, autonomy, and memory, not an explicit “Investigate” action. |

## Work implemented but not cleanly represented by the control

The current tree confirms the integration cleanup outcome described below the table, but not every historical detail in that narrative:

- The dashboard no longer imports or renders the old duplicate checklist. The current test asserts that `setup-checklist` is absent while the hero exists ([`first-run.test.tsx`](/srv/workspaces/NinjaSRE/console/tests/unit/surfaces/first-run.test.tsx:927)).
- `NoProviderNotice` now lives in `first-run/no-provider.tsx`, and its module comment records that the old checklist/quick-action contents were replaced and deleted ([`no-provider.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/first-run/no-provider.tsx:15)). Its current behavior is tested, including removal after setup ([`first-run.test.tsx`](/srv/workspaces/NinjaSRE/console/tests/unit/surfaces/first-run.test.tsx:940)).
- The old component name `QuickActions` should not be read as meaning that the current quick-actions file is dead. `DashboardQuickActions` is actively imported and rendered by the dashboard ([`dashboard.tsx`](/srv/workspaces/NinjaSRE/console/src/surfaces/screens/dashboard.tsx:14)).
- The exact historical count of “13 orphaned i18n keys” cannot be independently reconstructed from the current tree alone. The resulting absence of the old panel and its old catalog entry is supported; the number is historical evidence, not a current-code fact.
- Four shell baseline artifacts are present, including the four stated viewport/theme combinations, but they do not establish a dedicated first-run visual comparison ([`screens.json`](/srv/workspaces/NinjaSRE/console/visual/screens.json:313)).

## Verification performed

The following checks passed without modifying application source:

```text
pnpm exec vitest run tests/unit/surfaces/dashboard.test.tsx tests/unit/surfaces/failures.test.ts tests/unit/surfaces/first-run.test.tsx --config vitest.config.ts
3 files, 79 tests passed

pnpm exec vitest run tests/unit/surfaces/resources.test.tsx tests/unit/i18n/format.test.ts --config vitest.config.ts
2 files, 22 tests passed

pnpm exec tsc --noEmit
passed

pnpm exec eslint src/surfaces/screens/dashboard.tsx src/surfaces/setup-hero.tsx src/surfaces/quick-actions.tsx src/surfaces/figure.tsx src/surfaces/failures.ts src/surfaces/screens/resources.tsx
passed
```

These are focused checks, not a claim that the repository-wide `make verify` gate was run.

## Corrections applied after this audit

The following code corrections were applied after the audit was written:

- Resources now declares and applies a `health` filter. The dashboard’s combined problem figure uses `health=problem`, which matches both degraded and unhealthy resources.
- The dashboard problem count now uses the persistence contract’s `problems` value and no longer folds `unknown` or `stale` into a fault count.
- The attention band computes its oldest row from source timestamps rather than insertion order.
- The runs figure is now labelled “Recent investigations”, matching the API’s recent-record list instead of claiming an unimplemented 24-hour window.
- Regression coverage was added for all four behaviors above; the focused console suite, typecheck, ESLint, and formatting checks pass.

Cost/tokens and MTTD remain intentionally unimplemented because the list API still exposes neither aggregate cost/tokens nor a diagnosis timestamp. Adding either number without a batch-safe API field would recreate the evidence problem this audit was meant to catch.

## Recommended corrections to make the control honestly “done”

1. Add a real `health` filter to Resources, or change the dashboard links and values so they use filters that Resources actually supports.
2. Choose one health vocabulary and make the dashboard value, explanatory context, resource badges, and URL filter use it consistently. In particular, decide whether unknown/stale belong in the displayed problem count.
3. Either implement a named last-day window and an MTTD calculation, or rename the current figure to match the recent-records data it actually uses. Add period cost/tokens only when the API exposes an aggregate or batch-safe field.
4. Compute the oldest attention row from parsed timestamps and add a mixed-source regression test.
5. Add dashboard-level tests that assert the exact `href` semantics for every figure, including that the destination screen applies the intended filter.
6. Decide whether “starter actions” must include an explicit investigate/run action; if so, add it rather than relying on the Runs figure’s drill-down.
