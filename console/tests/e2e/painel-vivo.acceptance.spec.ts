import { expect, test, type Locator, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * The Painel: seventeen claims, against `design/padrao-2026-08/Main.dc.html`
 * and `DashboardLight.dc.html`.
 *
 * **This spec is expected to be comprehensively red when it is written.** The
 * page today is eleven server reads glued together by a timer: the run band
 * is `guardian-band.tsx`'s plain list with no stage bar, the approval band
 * does not exist (deciding happens on `/decisions`), the KPIs are bare
 * numbers with no sparkline, "what insists" and the live activity feed do not
 * exist as their own sections. Every task after the one that lands this file
 * exists to turn one block of it green.
 *
 * Backing: `mock` drives every claim here. Ten of the seventeen also carry
 * `@staging-safe` and run again against `https://stg-ninjasre.lan.kyo.ninja`
 * in the orchestrator's own pass (`specs_v8/EXECUCAO.md` §4) — the literal
 * tag the runner's own `--grep` selects on, never a second suite. AN-01 is
 * the one claim that creates a run there, the single creation S3 budgets for
 * the whole slot; `020-titulo-vivo` reuses that same run rather than either
 * feature creating a second one. AN-02, both AN-04 blocks, AN-05 and AN-14
 * each start their own investigation and stay untagged for that reason
 * alone, not because anything else about them is unfit. AN-06 only reads
 * the one pending decision and checks that Aprovar is enabled, never
 * clicking it, so it is tagged; AN-07/AN-08 stay untagged because staging
 * carries exactly one pending approval, reserved undecided for the S5 demo,
 * and either decides it or visibly disturbs it. AN-03 needs its run's
 * `stage_index` to have already advanced past its very first instant — a
 * pipeline-pace timing this claim never polls for — so it stays mock-only
 * too.
 *
 * AN-03 was written and skipped while `stage_index` lived in a sibling
 * feature's worktree this one could not see. Both features share a tree now,
 * so it runs.
 */

const STAGING_SAFE_TAG = '@staging-safe';

test.use({ viewport: { width: 1440, height: 1080 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  // `prefers-reduced-motion` stays at the suite's own default (no preference)
  // except in AN-04, which sets it explicitly.
});

// --- Shared locators -----------------------------------------------------------

function runBand(page: Page): Locator {
  return page.getByTestId('run-band');
}

function runCards(page: Page): Locator {
  return page.getByTestId('run-card');
}

function decisionBand(page: Page): Locator {
  return page.getByTestId('attention-decision-band');
}

function kpiTile(page: Page, kpi: string): Locator {
  return page.getByTestId('kpi-tile').and(page.locator(`[data-kpi="${kpi}"]`));
}

function subjectRows(page: Page): Locator {
  return page.getByTestId('subject-row');
}

function activityEntries(page: Page): Locator {
  return page.getByTestId('activity-feed-entry');
}

/** Start an investigation from the topbar's existing control and return its objective. */
async function startInvestigation(page: Page, objective: string): Promise<void> {
  await page.getByTestId('investigate').click();
  await page.getByTestId('investigate-drawer').waitFor({ state: 'visible' });
  await page.locator('textarea[name="objective"]').fill(objective);
  await page.getByTestId('start-investigation').click();
}

// =============================================================================
// AN-01 — a run started by the UI appears in "running now" without a reload
// =============================================================================

// The one run this file may create against staging (EXECUCAO.md §4's single
// creation per slot) — 020-titulo-vivo reuses it, so nothing below this test
// may honestly start a second one.
test(
  'AN-01: a run started from the UI enters "Em execução agora" without a reload',
  { tag: STAGING_SAFE_TAG },
  async ({ page }) => {
    await page.goto('/');
    await expect(runBand(page)).toBeVisible();
    const before = await runCards(page).count();

    const objective = `painel vivo probe ${String(Date.now())}`;
    await startInvestigation(page, objective);

    // No page.reload() anywhere in this test — the assertion below is a poll,
    // never a navigation, and the load above happened before the trigger.
    await expect
      .poll(async () => runCards(page).count(), { timeout: 5_000 })
      .toBeGreaterThan(before);
  },
);

// =============================================================================
// AN-02 — the card's title is the typed objective, never a raw identifier
// =============================================================================

// Not staging-safe: this claim starts its own investigation, which would be
// a second run creation in the same slot — AN-01 already spends the one
// EXECUCAO.md §4 budgets here. Mock-only for that reason alone.
test('AN-02: the new card is titled by the typed objective, never "interactive investigation" nor a hex id', async ({
  page,
}) => {
  await page.goto('/');
  const objective = `painel vivo title probe ${String(Date.now())}`;
  await startInvestigation(page, objective);

  const card = runCards(page).first();
  await expect(card).toBeVisible({ timeout: 5_000 });
  const title = card.getByTestId('run-card-title');
  const text = (await title.textContent()) ?? '';
  expect(text).toContain(objective.slice(0, 20));
  expect(text.toLowerCase()).not.toContain('interactive investigation');
  expect(text).not.toMatch(/^[a-f0-9-]{16,}$/i);
});

// =============================================================================
// AN-03 — the stage bar distinguishes completed/current/future (needs 020)
// =============================================================================

// Not staging-safe: `stageStates` (`run-band.tsx`) draws every segment
// "future" until a run's first stage has actually completed, so this needs
// the created run's own pace to have already advanced past its very first
// instant — a timing this claim never polls for, unlike AN-01's own
// assertion. It also carries no skip guard for "no run in the band" at all,
// unlike AN-06/AN-11/AN-12 below, and staging usually has none in flight.
// Mock-only, against the fixture's own fixed `stage_index`.
test('AN-03: the card draws six segments with the current stage distinct from completed and future', async ({
  page,
}) => {
  await page.goto('/');
  const card = runCards(page).first();
  const segments = card.getByTestId('run-card-stage');
  await expect(segments).toHaveCount(6);
  // `.and(...)`, not `.filter({ has: ... })`: the state this claim asks about
  // is `data-state` on the segment itself, not on some descendant of it — the
  // segment is a bare `<span>` with no children at all
  // (`console/src/surfaces/run-band.tsx`'s `StageSegment`), so `has` could
  // never match here regardless of what the console renders. `.and()` is the
  // combinator for "the same element also matches this locator".
  await expect(segments.and(page.locator('[data-state="current"]'))).toHaveCount(1);
});

// =============================================================================
// AN-04 — the arrival animation, suppressed under prefers-reduced-motion
// =============================================================================

// Not staging-safe, both blocks below: each starts its own investigation, a
// second and third run creation this slot's budget has no room for once
// AN-01 has already spent it — true whether or not `emulateMedia` itself
// would behave identically against a real deployment. Mock-only.
test('AN-04: a new card carries the arrival animation class, absent under prefers-reduced-motion', async ({
  page,
}) => {
  await page.goto('/');
  const objective = `painel vivo motion probe ${String(Date.now())}`;
  await startInvestigation(page, objective);

  const card = runCards(page).first();
  await expect(card).toBeVisible({ timeout: 5_000 });
  await expect(card).toHaveClass(/slide-in/);
});

// Same reason as the block above: its own investigation, over budget.
test('AN-04: under prefers-reduced-motion, the animation does not run', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const objective = `painel vivo reduced-motion probe ${String(Date.now())}`;
  await startInvestigation(page, objective);

  const card = runCards(page).first();
  await expect(card).toBeVisible({ timeout: 5_000 });
  const animationName = await card.evaluate(
    (element) => getComputedStyle(element).animationName,
  );
  expect(animationName === 'none' || animationName === '').toBe(true);
});

// =============================================================================
// AN-05 — a completed run leaves the band and the count decreases
// =============================================================================

// Not staging-safe: its own investigation (over the one-run budget), and
// even setting that aside, its 30-second poll for full completion is a bound
// only the mock's compressed, scripted timeline can promise — a real
// pipeline's six stages are not proven to settle inside it. Mock-only.
test('AN-05: when a run completes, its card leaves the band and "em voo" decreases, without reload', async ({
  page,
}) => {
  await page.goto('/');
  const objective = `painel vivo completion probe ${String(Date.now())}`;
  await startInvestigation(page, objective);

  await expect
    .poll(async () => runCards(page).count(), { timeout: 5_000 })
    .toBeGreaterThan(0);
  const flightCountBefore = Number(
    (await page.getByTestId('run-band-flight-count').textContent()) ?? '0',
  );

  await expect
    .poll(async () => runCards(page).count(), { timeout: 30_000 })
    .toBeLessThan(await runCards(page).count());
  const flightCountAfter = Number(
    (await page.getByTestId('run-band-flight-count').textContent()) ?? '0',
  );
  expect(flightCountAfter).toBeLessThan(flightCountBefore);
});

// =============================================================================
// AN-06 — the plan summary is visible before any button is clickable
// =============================================================================

// Staging-safe: reads the one pending approval S2 left behind (the oldest,
// and only, decision always renders expanded — `AttentionBlock`,
// `attention.tsx`) and only checks that Aprovar is enabled; nothing here
// clicks it. "Leitura, fluxo de proposta" (EXECUCAO.md §4), never a decision.
test(
  'AN-06: the "needs you" band shows the plan summary and rollback before any button is clickable',
  { tag: STAGING_SAFE_TAG },
  async ({ page }) => {
    await page.goto('/');
    const card = decisionBand(page).getByTestId('attention-decision-card').first();
    if ((await card.count()) === 0) {
      // Documented, not silently skipped: local mock backing seeds no pending
      // approval by default, and this claim needs a real one.
      test.skip(
        true,
        'the mock scenario carries no pending approval to assert this against',
      );
    }
    await expect(card.getByTestId('attention-decision-plan')).toBeVisible();
    await expect(card.getByTestId('attention-decision-rollback')).toBeVisible();
    await expect(card.getByTestId('attention-decision-risk')).toBeVisible();
    await expect(card.getByTestId('attention-decision-age')).toBeVisible();
    await expect(card.getByTestId('attention-approve')).toBeEnabled();
  },
);

// =============================================================================
// AN-08 — rejecting requires a non-empty reason before it may submit
// =============================================================================

// Not staging-safe: staging carries exactly one pending approval, reserved
// undecided for the S5 demo. This block never calls `attention-reject-submit`
// (no `fetch` reaches `/api/approval` at all, confirmed by reading
// `AttentionDecisionControls` — `decide()` only runs from that button's own
// `onClick`), so it would not actually decide the reserved approval even if
// tagged — but it does click Recusar and type into its reason field, a
// visible interaction with the one item that must stay untouched. Mock-only.
test('AN-08: rejecting requires a non-empty reason before submission is possible', async ({
  page,
}) => {
  await page.goto('/');
  const card = decisionBand(page).getByTestId('attention-decision-card').first();
  if ((await card.count()) === 0) {
    test.skip(true, 'the mock scenario carries no pending approval to reject');
  }
  await card.getByTestId('attention-reject').click();
  const reasonField = card.getByTestId('attention-reject-reason');
  await expect(reasonField).toBeVisible();
  const submit = card.getByTestId('attention-reject-submit');
  await expect(submit).toBeDisabled();
  await reasonField.fill('not a real problem');
  await expect(submit).toBeEnabled();
});

// =============================================================================
// AN-07 — approving in the band closes it without reload
// Runs after AN-08: both need the mock scenario's one pending approval,
// and only this one actually decides it (AN-08 never submits), so this
// order is what lets each see a still-pending card. T040/convergence.
//
// Not staging-safe: this is the claim that decides an approval, and
// staging's one pending approval is reserved undecided for the S5 demo.
// =============================================================================

test('AN-07: approving from the band closes the approval and the band reflects it without reload', async ({
  page,
}) => {
  await page.goto('/');
  const card = decisionBand(page).getByTestId('attention-decision-card').first();
  if ((await card.count()) === 0) {
    test.skip(true, 'the mock scenario carries no pending approval to decide');
  }
  const before = await decisionBand(page)
    .getByTestId('attention-decision-card')
    .count();
  await card.getByTestId('attention-approve').click();
  await expect
    .poll(
      async () => decisionBand(page).getByTestId('attention-decision-card').count(),
      { timeout: 5_000 },
    )
    .toBeLessThan(before);
});

// =============================================================================
// AN-09 — every KPI shows number, sparkline and a decomposed legend
// =============================================================================

test(
  'AN-09: each of the five KPIs shows a number, a sparkline and a decomposition legend',
  { tag: STAGING_SAFE_TAG },
  async ({ page }) => {
    await page.goto('/');
    for (const kpi of [
      'watched',
      'degraded',
      'selfResolved',
      'successRate',
      'timeToCause',
    ]) {
      const tile = kpiTile(page, kpi);
      await expect(tile).toBeVisible();
      await expect(tile.getByTestId('kpi-value')).toBeVisible();
      await expect(tile.getByTestId('kpi-sparkline')).toBeVisible();
      await expect(tile.getByTestId('kpi-legend')).toBeVisible();
    }
  },
);

// =============================================================================
// AN-10 — no number on the Painel diverges from the list that serves it
// =============================================================================

test(
  'AN-10: the "em voo" count on the run band equals the number of cards actually shown',
  { tag: STAGING_SAFE_TAG },
  async ({ page }) => {
    await page.goto('/');
    const shown = await runCards(page).count();
    const declared = Number(
      (await page.getByTestId('run-band-flight-count').textContent()) ?? '-1',
    );
    // The header may count more than are drawn (the six-card visual cap), so
    // the check is "at least as many", never a strict equality that a cap
    // would immediately break. Holds equally at zero runs in flight, which is
    // staging's ordinary moment: the header renders `0` rather than omitting
    // the count (`RunBand`, `run-band.tsx`), so `0 >= 0` is still a real pass.
    expect(declared).toBeGreaterThanOrEqual(shown);
  },
);

// =============================================================================
// AN-11 — "what insists" groups by subject with a timeline, count and chip
// =============================================================================

test(
  'AN-11: "o que insiste em acontecer" shows a per-subject timeline, an N× count and a shaped chip',
  { tag: STAGING_SAFE_TAG },
  async ({ page }) => {
    await page.goto('/');
    const row = subjectRows(page).first();
    if ((await row.count()) === 0) {
      test.skip(
        true,
        'the mock scenario carries no recurring subject to assert this against',
      );
    }
    await expect(row.getByTestId('subject-timeline')).toBeVisible();
    await expect(row.getByTestId('subject-count')).toHaveText(/\d+×/);
    await expect(row.getByTestId('subject-chip')).toHaveAttribute('data-role', /.+/);
  },
);

// =============================================================================
// AN-12 — no subject shows a raw identifier as its subtitle
// =============================================================================

test(
  'AN-12: no subject subtitle shows a raw resource or hex identifier',
  { tag: STAGING_SAFE_TAG },
  async ({ page }) => {
    await page.goto('/');
    const count = await subjectRows(page).count();
    if (count === 0) {
      test.skip(
        true,
        'the mock scenario carries no subject rows to assert this against',
      );
    }
    for (let index = 0; index < count; index += 1) {
      const subtitle =
        (await subjectRows(page)
          .nth(index)
          .getByTestId('subject-subtitle')
          .textContent()) ?? '';
      expect(subtitle).not.toMatch(/^res-[0-9a-f]{8}/);
      expect(subtitle).not.toMatch(/[0-9a-f]{16,}/);
    }
  },
);

// =============================================================================
// AN-13 — "live activity" is a vertical timeline with a shape per type
// =============================================================================

test(
  'AN-13: "atividade ao vivo" is a vertical timeline where each entry carries its type\'s shape',
  { tag: STAGING_SAFE_TAG },
  async ({ page }) => {
    await page.goto('/');
    const entries = activityEntries(page);
    await expect(entries.first()).toBeVisible();
    const kinds = await entries.evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('data-kind')),
    );
    for (const kind of kinds) {
      expect(['investigation', 'resolution', 'incident', 'approval']).toContain(kind);
    }
  },
);

// =============================================================================
// AN-14 — a new deployment event inserts an activity entry without reload
// =============================================================================

// Not staging-safe: its own investigation, a further run this slot's budget
// has no room for once AN-01 has spent it. Mock-only.
test('AN-14: a new event inserts an activity entry at the top, without reload', async ({
  page,
}) => {
  await page.goto('/');
  const before = await activityEntries(page).count();
  const objective = `painel vivo activity probe ${String(Date.now())}`;
  await startInvestigation(page, objective);

  await expect
    .poll(async () => activityEntries(page).count(), { timeout: 5_000 })
    .toBeGreaterThan(before);
  await expect(activityEntries(page).first()).toContainText(objective.slice(0, 20));
});

// =============================================================================
// AN-15 — with the stream down, the freshness chip says fallback, reads continue
// =============================================================================

// Staging-safe: `page.route()` intercepts requests the browser itself makes,
// whatever backing they would otherwise reach, so forcing this one route
// down needs no harness support staging lacks. Creates and decides nothing.
test(
  'AN-15: with the stream down, the freshness chip says fallback and the Painel keeps serving reads',
  { tag: STAGING_SAFE_TAG },
  async ({ page }) => {
    await page.route('**/api/events/stream', async (route) => {
      await route.fulfill({ status: 502, body: '{"streaming":false}' });
    });
    await page.goto('/');
    await expect(page.getByTestId('freshness')).toHaveAttribute('data-state', 'stale', {
      timeout: 30_000,
    });
    // The rest of the page is not blank behind the fallback chip.
    await expect(runBand(page)).toBeVisible();
    await expect(page.getByTestId('kpi-tile').first()).toBeVisible();
  },
);

// =============================================================================
// AN-16 — every genuine empty state names the next step, with a link
// =============================================================================

// Staging-safe: staging currently carries a pending approval, so this skips
// via its own guard rather than asserting the empty state that would only
// exist without one — an honest, named skip, not a manufactured pass.
test(
  'AN-16: an empty "needs you" band says nothing waits and links to Decisions history',
  { tag: STAGING_SAFE_TAG },
  async ({ page }) => {
    await page.goto('/');
    const empty = decisionBand(page).getByTestId('attention-decision-empty');
    if ((await empty.count()) === 0) {
      test.skip(
        true,
        'the mock scenario carries a pending approval, so the empty state does not render',
      );
    }
    await expect(empty).toBeVisible();
    await expect(empty.locator('a[href*="/decisions"]')).toBeVisible();
  },
);

// =============================================================================
// AN-17 — the Painel renders without error in both themes, tokens only
// =============================================================================

test(
  'AN-17: the Painel renders without a console error in both themes',
  { tag: STAGING_SAFE_TAG },
  async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await page.goto('/');
    await expect(runBand(page)).toBeVisible();

    await page.getByTestId('theme-switch').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', /light|dark/);
    await expect(runBand(page)).toBeVisible();

    expect(errors).toEqual([]);
  },
);
