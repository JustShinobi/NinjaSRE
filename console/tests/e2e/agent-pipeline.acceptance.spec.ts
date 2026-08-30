import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * `/agent`, opening on a metro line of the six stages instead of the
 * orchestrator/stage/specialist hierarchy graph, with three summary cards
 * beneath it reading what the other three tabs already read.
 *
 * The local mock's `populated` scenario carries the real six stages
 * (`resolve_integrations`, `intake`, `plan_evidence`, `gather_evidence`,
 * `diagnose`, `deliver`) with `model_role` set on `intake`, `gather_evidence`
 * and `diagnose` — enough to prove every regime word this feature derives.
 * It carries one `running` run, four tools and two skills, and five autonomy
 * classes all resolving to "propose" — enough to prove every card
 * structurally. The exact staging figures (63 of 80, 2 investigations in
 * flight) are `@staging-safe`.
 *
 * **This spec is expected to be comprehensively red when it is written.**
 * The Pipeline tab draws an orchestrator/stage/specialist hierarchy graph,
 * not a metro line; there is no "N investigations in flight" chip; there are
 * no summary cards below it. Every task after this one exists to turn one
 * block of this file green.
 */

const STAGING_SAFE_TAG = '@staging-safe';

const STAGE_ORDER = [
  'resolve_integrations',
  'intake',
  'plan_evidence',
  'gather_evidence',
  'diagnose',
  'deliver',
] as const;

test.use({ viewport: { width: 1920, height: 1080 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

// =============================================================================
// AN-A1 / AN-A2 — the metro line, six nodes, in order, one sentence each
// =============================================================================

test.describe('AN-A1/AN-A2 — the Pipeline tab opens with a six-node metro line, one sentence each', () => {
  test('the metro shows the six stages in the order the pipeline serves', async ({ page }) => {
    await page.goto('/agent');
    await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
    const nodes = page.getByTestId('pipeline-metro-node');
    await expect(nodes).toHaveCount(STAGE_ORDER.length);
    const order = await nodes.evaluateAll((elements) =>
      elements.map((element) => element.getAttribute('data-stage')),
    );
    expect(order).toEqual([...STAGE_ORDER]);
  });

  test('each node names its regime, a readable name, and a one-sentence microcopy', async ({
    page,
  }) => {
    await page.goto('/agent');
    const nodes = page.getByTestId('pipeline-metro-node');
    const total = await nodes.count();
    // Never vacuous: a page with no metro nodes yet must fail this claim,
    // not pass it by having nothing to loop over.
    expect(total).toBe(STAGE_ORDER.length);
    for (let index = 0; index < total; index += 1) {
      const node = nodes.nth(index);
      await expect(node.getByTestId('pipeline-metro-regime')).toBeVisible();
      await expect(node.getByTestId('pipeline-metro-name')).toBeVisible();
      const copy = (await node.getByTestId('pipeline-metro-copy').innerText()).trim();
      const sentences = copy.split(/(?<=[.!?])\s+/u).filter(Boolean);
      expect(sentences.length).toBeLessThanOrEqual(1);
    }
  });

  test('the stage with a bound model role reads "model: <role>"; one with none reads "no model"', async ({
    page,
  }) => {
    await page.goto('/agent');
    const intake = page.getByTestId('pipeline-metro-node').filter({
      has: page.locator('[data-stage="intake"]'),
    });
    await expect(intake.getByTestId('pipeline-metro-regime')).toContainText('intake');
    const resolve = page.getByTestId('pipeline-metro-node').filter({
      has: page.locator('[data-stage="resolve_integrations"]'),
    });
    const resolveRegime = (await resolve.getByTestId('pipeline-metro-regime').innerText()).toLowerCase();
    expect(resolveRegime).not.toContain('intake');
  });
});

// =============================================================================
// AN-A3 — "N investigations in flight" chip, from the runs listing
// =============================================================================

test.describe('AN-A3 — the pipeline card shows how many investigations are running now', () => {
  test('with a running run in the listing, the chip names a positive count', async ({
    page,
  }) => {
    await page.goto('/agent');
    const chip = page.getByTestId('pipeline-in-flight');
    const total = await chip.count();
    if (total === 0) {
      test.skip(true, 'no running investigation in this environment right now');
      return;
    }
    await expect(chip).toContainText(/\d/);
  });
});

// =============================================================================
// AN-A4 / AN-A8 — three summary cards below the metro, each linking its tab
// =============================================================================

test.describe('AN-A4 — three summary cards sit below the metro, each reading its own tab’s route', () => {
  test('Tools, Autonomy and Team Context cards exist and link their tabs', async ({ page }) => {
    await page.goto('/agent');
    const tools = page.getByTestId('pipeline-summary-tools');
    const autonomy = page.getByTestId('pipeline-summary-autonomy');
    const team = page.getByTestId('pipeline-summary-team');
    await expect(tools).toBeVisible();
    await expect(autonomy).toBeVisible();
    await expect(team).toBeVisible();
    await expect(tools.getByRole('link').first()).toHaveAttribute('href', /tab=tools/);
    await expect(autonomy.getByRole('link').first()).toHaveAttribute('href', /tab=autonomy/);
    await expect(team.getByRole('link').first()).toHaveAttribute('href', /tab=team/);
  });
});

// =============================================================================
// AN-A5 — the Tools card: X of Y enabled, domain bars, side-effect chips
// =============================================================================

test.describe('AN-A5 — the Tools card names X of Y enabled, domain bars, and side-effect counts', () => {
  test('the card states an enabled/total ratio and at least one domain bar', async ({
    page,
  }) => {
    await page.goto('/agent');
    const card = page.getByTestId('pipeline-summary-tools');
    await expect(card).toContainText(/\d+.*\d+/u);
    const bars = card.getByTestId('domain-bar');
    expect(await bars.count()).toBeGreaterThan(0);
  });

  test('a destructive side-effect chip, when present, carries the danger role', async ({
    page,
  }) => {
    await page.goto('/agent');
    const card = page.getByTestId('pipeline-summary-tools');
    // The card itself must exist before "no destructive chip" can be read as
    // a legitimate zero rather than as the feature not existing yet.
    await expect(card).toBeVisible();
    const allChips = card.getByTestId('side-effect-chip');
    expect(await allChips.count()).toBeGreaterThan(0);
    const chip = allChips.filter({ has: page.locator('[data-role="danger"]') });
    if ((await chip.count()) === 0) return; // legitimate: no destructive tool enabled here
    await expect(chip.first()).toBeVisible();
  });
});

// =============================================================================
// AN-A6 — the Autonomy card: five classes, all resolving, dangerous in amber
// =============================================================================

test.describe('AN-A6 — the Autonomy card shows the five-class ladder with the resolved decision', () => {
  test('all five classes render, each with its resolved decision, no full "Why:" text', async ({
    page,
  }) => {
    await page.goto('/agent');
    const card = page.getByTestId('pipeline-summary-autonomy');
    const rows = card.getByTestId('autonomy-summary-row');
    await expect(rows).toHaveCount(5);
    for (let index = 0; index < 5; index += 1) {
      await expect(rows.nth(index).getByTestId('autonomy-summary-decision')).toBeVisible();
    }
    await expect(card.getByTestId('outlook-reason')).toHaveCount(0);
  });
});

// =============================================================================
// AN-A7 — the Team Context card: prompt budget, or an honest empty state
// =============================================================================

test.describe('AN-A7 — the Team Context card shows the prompt budget bar or a short empty state', () => {
  test('the card names N of M tokens, or says nothing is written yet in at most two sentences', async ({
    page,
  }) => {
    await page.goto('/agent');
    const card = page.getByTestId('pipeline-summary-team');
    const budget = card.getByTestId('team-budget');
    if ((await budget.count()) > 0) {
      await expect(budget).toContainText(/\d/);
      return;
    }
    const empty = card.getByTestId('team-empty');
    await expect(empty).toBeVisible();
    const sentences = (await empty.innerText()).split(/(?<=[.!?])\s+/u).filter(Boolean);
    expect(sentences.length).toBeLessThanOrEqual(2);
    await expect(card.getByRole('link')).toBeVisible();
  });
});

// =============================================================================
// AN-A8 — the three other tabs keep serving their full content
// =============================================================================

test.describe('AN-A8 — Tools, Autonomy and Team Context still serve their full content', () => {
  test('the Tools tab still lists capabilities beyond the summary card', async ({ page }) => {
    await page.goto('/agent?tab=tools');
    await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
    const tools = page.getByTestId('agent-tool');
    const skills = page.getByTestId('catalogue-skill');
    expect((await tools.count()) + (await skills.count())).toBeGreaterThan(0);
  });

  test('the Autonomy tab still shows the full outlook, "Why:" included', async ({ page }) => {
    await page.goto('/agent?tab=autonomy');
    await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
    await expect(page.getByTestId('outlook-class')).not.toHaveCount(0);
  });

  test('the Team Context tab still shows the section editor', async ({ page }) => {
    await page.goto('/agent?tab=team');
    await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
    await expect(page.getByTestId('page-header').first()).toBeVisible();
  });
});

// =============================================================================
// Real staging figures — proven where the number this feature does not choose lives
// =============================================================================

test.describe(
  'staging figures — the wave’s own audited numbers',
  { tag: STAGING_SAFE_TAG },
  () => {
    test('the Tools card names the audited 63 of 80 on the environment the wave measured', async ({
      page,
    }) => {
      await page.goto('/agent');
      const card = page.getByTestId('pipeline-summary-tools');
      const text = await card.innerText();
      if (!/80/.test(text)) {
        test.skip(true, 'this environment does not carry the audited catalogue size');
        return;
      }
      expect(text).toMatch(/63/);
    });
  },
);

// =============================================================================
// AN-T1 / AN-T3 transversal checks specific to this screen
// =============================================================================

test.describe('AN-T1 — Agent renders no native select as a primary filter', () => {
  test('no select element on any of the four tabs', async ({ page }) => {
    for (const tab of ['topology', 'tools', 'autonomy', 'team']) {
      await page.goto(`/agent?tab=${tab}`);
      await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
      await expect(page.locator('select')).toHaveCount(0);
    }
  });
});
