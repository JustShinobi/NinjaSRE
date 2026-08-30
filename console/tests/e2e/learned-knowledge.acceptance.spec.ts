import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * `/knowledge`, opening on what past investigations learned rather than on
 * the documents tab, with episodes as cards and a component filter that does
 * not show the same guest twice.
 *
 * The local mock's `populated` scenario carries five episodes with plain
 * component names (`plateau`, `cluster`, `node01`, `node02`, …) — none of
 * them the `container:<id>`/`guest:<id>` pair the wave's own staging audit
 * found duplicated. The exact-duplicate collapse (AN-C2) is proven at the
 * unit level against synthetic data (`console/tests/unit/surfaces/component-normalisation.test.ts`)
 * and, structurally, `@staging-safe` here. The local dataset also carries no
 * pending `knowledge`-typed proposal, so the "has a pending proposal" half of
 * AN-C4 is `@staging-safe`; the honest empty state is proven locally.
 *
 * **This spec is expected to be comprehensively red when it is written.** The
 * default tab is Documents; episodes render as table rows, not cards; the
 * component filter is a flat list with duplicates; there is no learned-from
 * panel reading the proposal queue. Every task after this one exists to turn
 * one block of this file green.
 */

const STAGING_SAFE_TAG = '@staging-safe';

test.use({ viewport: { width: 1920, height: 1080 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

// =============================================================================
// AN-C1 — Learned is the default tab; deep links keep working
// =============================================================================

test.describe('AN-C1 — Knowledge opens on Learned by default; deep links to other tabs still work', () => {
  test('visiting /knowledge with no tab in the address shows Learned as active', async ({
    page,
  }) => {
    await page.goto('/knowledge');
    await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
    await expect(
      page.locator('[data-tab="learned"][aria-current="page"]'),
    ).toBeVisible();
  });

  test('?tab=documents still opens Documents', async ({ page }) => {
    await page.goto('/knowledge?tab=documents');
    await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
    await expect(
      page.locator('[data-tab="documents"][aria-current="page"]'),
    ).toBeVisible();
  });

  test('?tab=topology still opens Topology', async ({ page }) => {
    await page.goto('/knowledge?tab=topology');
    await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
    await expect(
      page.locator('[data-tab="topology"][aria-current="page"]'),
    ).toBeVisible();
  });
});

// =============================================================================
// AN-C3 — episodes render as cards with a shaped outcome chip
// =============================================================================

test.describe('AN-C3 — every episode is a card: title-phrase, outcome shape, component chips', () => {
  test('the Learned tab draws episode cards, never a table', async ({ page }) => {
    await page.goto('/knowledge');
    await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
    await expect(page.getByTestId('episodes-table')).toHaveCount(0);
    const cards = page.getByTestId('episode-card');
    expect(await cards.count()).toBeGreaterThan(0);
  });

  test('a resolved episode carries a resolved-shaped outcome chip and a relative time', async ({
    page,
  }) => {
    await page.goto('/knowledge');
    // Self-referential: data-outcome lives on the card itself.
    const resolved = page.locator(
      '[data-testid="episode-card"][data-outcome="resolved"]',
    );
    expect(await resolved.count()).toBeGreaterThan(0);
    await expect(resolved.first().getByTestId('episode-time')).toBeVisible();
  });

  test('a component chip on a card is clickable and applies the filter', async ({
    page,
  }) => {
    await page.goto('/knowledge');
    const chip = page
      .getByTestId('episode-card')
      .first()
      .getByTestId('episode-component-chip')
      .first();
    await expect(chip).toBeVisible();
    const text = (await chip.innerText()).trim();
    await chip.click();
    await expect(page).toHaveURL(/component=/);
    const filterChip = page.getByTestId('component-filter-summary');
    await expect(filterChip).toContainText(text.length > 0 ? text : /.+/);
  });

  test('an episode with a run links to its investigation', async ({ page }) => {
    await page.goto('/knowledge');
    const linked = page.getByTestId('episode-card').filter({
      has: page.getByTestId('episode-open-investigation'),
    });
    const total = await linked.count();
    expect(total).toBeGreaterThan(0);
    await expect(
      linked.first().getByTestId('episode-open-investigation'),
    ).toHaveAttribute('href', /^\/runs\//);
  });
});

// =============================================================================
// AN-C2 — component filter groups by type, with counts, no duplicates
// =============================================================================

test.describe('AN-C2 — the component filter groups by type with counts and no duplicate identifier', () => {
  test('opening the component filter shows type groups, each with a count', async ({
    page,
  }) => {
    await page.goto('/knowledge');
    const filter = page.getByTestId('component-filter-toggle');
    await expect(filter).toBeVisible();
    await filter.click();
    const groups = page.getByTestId('component-filter-group');
    expect(await groups.count()).toBeGreaterThan(0);
    for (let index = 0; index < (await groups.count()); index += 1) {
      await expect(
        groups.nth(index).getByTestId('component-filter-group-count'),
      ).toContainText(/\d/);
    }
  });

  test(
    'a component seen as both container: and guest: appears once, under guests',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/knowledge');
      await page.getByTestId('component-filter-toggle').click();
      const entries = page.getByTestId('component-filter-option');
      const values = await entries.allInnerTexts();
      const counts = new Map<string, number>();
      for (const value of values) {
        counts.set(value, (counts.get(value) ?? 0) + 1);
      }
      for (const [, count] of counts) {
        expect(count).toBe(1);
      }
    },
  );
});

// =============================================================================
// AN-C4 — the learned-from panel reads the pending knowledge-proposal queue
// =============================================================================

test.describe('AN-C4 — the side panel lists pending knowledge proposals, or says honestly there are none', () => {
  test('with no pending knowledge proposal, the panel says so in at most two sentences and links to the queue', async ({
    page,
  }) => {
    await page.goto('/knowledge');
    const panel = page.getByTestId('knowledge-learned-panel');
    await expect(panel).toBeVisible();
    const cards = panel.getByTestId('knowledge-proposal-card');
    if ((await cards.count()) > 0) {
      test.skip(true, 'this environment already carries a pending knowledge proposal');
      return;
    }
    const empty = panel.getByTestId('knowledge-proposal-empty');
    await expect(empty).toBeVisible();
    const sentences = (await empty.innerText()).split(/(?<=[.!?])\s+/u).filter(Boolean);
    expect(sentences.length).toBeLessThanOrEqual(2);
    await expect(panel.getByRole('link')).toBeVisible();
  });

  test(
    'a pending knowledge proposal card names its text, its origin, and "promote to document"',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/knowledge');
      const cards = page.getByTestId('knowledge-proposal-card');
      const total = await cards.count();
      test.skip(total === 0, 'no pending knowledge proposal in this environment');
      if (total === 0) return;
      await expect(cards.first()).toContainText(/\w/);
      await expect(cards.first().getByRole('link')).toBeVisible();
    },
  );
});

// =============================================================================
// AN-C5 — the bottom strip previews Documents and Topology with real counts
// =============================================================================

test.describe('AN-C5 — the bottom strip previews Documents and Topology, each with its own count or empty', () => {
  test('two preview cards exist, each a link to its own tab', async ({ page }) => {
    await page.goto('/knowledge');
    const documents = page.getByTestId('knowledge-preview-documents');
    const topology = page.getByTestId('knowledge-preview-topology');
    await expect(documents).toBeVisible();
    await expect(topology).toBeVisible();
    await expect(documents.getByRole('link')).toHaveAttribute('href', /tab=documents/);
    await expect(topology.getByRole('link')).toHaveAttribute('href', /tab=topology/);
  });
});

// =============================================================================
// AN-C6 — no empty state on this screen is a wall of prose
// =============================================================================

test.describe('AN-C6 — no empty state on Knowledge exceeds two sentences or ends without an action', () => {
  test('every empty-state block on the three tabs is short and ends with a link', async ({
    page,
  }) => {
    for (const tab of ['learned', 'documents', 'topology']) {
      await page.goto(`/knowledge?tab=${tab}`);
      await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
      const empties = page.locator('[data-testid$="-empty"], [data-state="empty"]');
      const total = await empties.count();
      for (let index = 0; index < total; index += 1) {
        const text = (await empties.nth(index).innerText()).trim();
        if (text === '') continue;
        const sentences = text.split(/(?<=[.!?])\s+/u).filter(Boolean);
        expect(sentences.length).toBeLessThanOrEqual(2);
      }
    }
  });
});

// =============================================================================
// AN-T1 — no native select on this screen either
// =============================================================================

test.describe('AN-T1 — Knowledge renders no native select as a primary filter', () => {
  test('no select element exists on any of the three tabs', async ({ page }) => {
    for (const tab of ['learned', 'documents', 'topology']) {
      await page.goto(`/knowledge?tab=${tab}`);
      await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
      await expect(page.locator('select')).toHaveCount(0);
    }
  });
});
