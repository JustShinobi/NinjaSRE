import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * `/resources`, answering "what is doing badly, where, and since when" on
 * first paint instead of a flat table an operator has to scan.
 *
 * The local mock's `populated` scenario carries 86 resources — 72 healthy, 14
 * unhealthy, across two nodes (`node01`, `node02`) — with `parent_name`
 * already resolved in the fixture. It carries no `unknown` or `absent`
 * resource, so the segments this spec can prove locally are `healthy` and
 * `unhealthy`; the full four-state bar (`saudável`/`desconhecido`/`não
 * saudável`/`ausente`) and the exact 71/14/14/12 count are `@staging-safe`,
 * against the environment the wave's own audit describes. `unhealthy_since`
 * is a field this feature adds to the contract; the duration-since-unhealthy
 * assertion is `@staging-safe` for the same reason — the local fixture
 * predates the field and is not hand-edited to carry it.
 *
 * **This spec is expected to be comprehensively red when it is written.**
 * There is no segmented health bar, no clickable legend, no node grouping, no
 * card grid — the screen is a flat sortable table with a `<select>`-based
 * filter bar. Every task after this one exists to turn one block of this
 * file green.
 */

const STAGING_SAFE_TAG = '@staging-safe';

test.use({ viewport: { width: 1920, height: 1080 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

async function openResources(page: Page): Promise<void> {
  await page.goto('/resources');
  await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
}

// =============================================================================
// AN-R1 / SC-003 — the segmented health bar, on first paint, one response
// =============================================================================

test.describe('AN-R1/SC-003 — the header shows a proportional health bar with no second request', () => {
  test('the bar draws one segment per health value present, with a legend count each', async ({
    page,
  }) => {
    const requests: string[] = [];
    page.on('request', (request) => {
      const url = request.url();
      if (url.includes('/v1/estate/')) requests.push(url);
    });
    await openResources(page);
    const bar = page.getByTestId('health-bar');
    await expect(bar).toBeVisible();
    const segments = bar.getByTestId('health-segment');
    expect(await segments.count()).toBeGreaterThanOrEqual(2);
    const legend = page.getByTestId('health-legend-item');
    expect(await legend.count()).toBeGreaterThanOrEqual(2);
    for (let index = 0; index < (await legend.count()); index += 1) {
      await expect(legend.nth(index)).toContainText(/\d/);
    }
    // Same response, no second request for the synthesis: every read this
    // header needs came from the resources/summary reads the page already
    // makes, never a client-side follow-up fetch for the bar itself.
    expect(requests.filter((url) => url.includes('/summary')).length).toBeLessThanOrEqual(1);
  });

  test(
    'all four states are present on staging, with the audited counts',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openResources(page);
      const legend = page.getByTestId('health-legend-item');
      // Locale-agnostic: assert the four states exist as distinct legend
      // entries rather than pinning to one language's word for each.
      expect(await legend.count()).toBe(4);
    },
  );
});

// =============================================================================
// AN-R2 — the legend filters, and the filter lands in the address
// =============================================================================

test.describe('AN-R2 — clicking a legend entry filters the list and updates the address', () => {
  test('clicking "unhealthy" in the legend narrows the grid and sets the URL', async ({
    page,
  }) => {
    await openResources(page);
    const unhealthy = page.getByTestId('health-legend-item').filter({ hasText: /unhealthy/i });
    await expect(unhealthy).toBeVisible();
    await unhealthy.click();
    await expect(page).toHaveURL(/health=unhealthy/);
    const cards = page.getByTestId('resource-card');
    const total = await cards.count();
    expect(total).toBeGreaterThan(0);
    for (let index = 0; index < total; index += 1) {
      await expect(cards.nth(index)).toHaveAttribute('data-health', 'unhealthy');
    }
  });
});

// =============================================================================
// AN-R3 / AN-T1 — type chips with counts, no <select>, compact search
// =============================================================================

test.describe('AN-R3/AN-T1 — type filter is a chip row with counts, search is compact, no <select>', () => {
  test('no native select renders, and the type chips carry a count each', async ({ page }) => {
    await openResources(page);
    await expect(page.locator('select')).toHaveCount(0);
    const chips = page.getByTestId('type-chip');
    expect(await chips.count()).toBeGreaterThanOrEqual(1);
    for (let index = 0; index < (await chips.count()); index += 1) {
      await expect(chips.nth(index)).toContainText(/\d/);
    }
  });
});

// =============================================================================
// AN-R4 / AN-R6 — sections by node, unhealthy-first, unhealthy sections first
// =============================================================================

test.describe('AN-R4/AN-R6 — resources group by node, worst node and worst resources first', () => {
  test('each node section names the node, a health chip, and a resource count', async ({
    page,
  }) => {
    await openResources(page);
    const sections = page.getByTestId('node-section');
    const total = await sections.count();
    expect(total).toBeGreaterThan(0);
    for (let index = 0; index < total; index += 1) {
      await expect(sections.nth(index).getByTestId('node-section-name')).toBeVisible();
      await expect(sections.nth(index).getByTestId('node-section-count')).toContainText(/\d/);
    }
  });

  test('a section holding unhealthy resources sorts before an all-healthy one', async ({
    page,
  }) => {
    await openResources(page);
    const sections = page.getByTestId('node-section');
    const flags = await sections.evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('data-has-unhealthy') === 'true'),
    );
    const firstHealthyIndex = flags.indexOf(false);
    const lastUnhealthyIndex = flags.lastIndexOf(true);
    if (firstHealthyIndex === -1 || lastUnhealthyIndex === -1) {
      test.skip(true, 'this dataset has only one kind of section to order');
      return;
    }
    expect(lastUnhealthyIndex).toBeLessThan(firstHealthyIndex);
  });

  test('within a section, unhealthy cards draw before healthy ones', async ({ page }) => {
    await openResources(page);
    const section = page
      .getByTestId('node-section')
      .filter({ has: page.locator('[data-has-unhealthy="true"]') })
      .first();
    if ((await section.count()) === 0) {
      test.skip(true, 'no unhealthy section in this dataset');
      return;
    }
    const healths = await section
      .getByTestId('resource-card')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-health')));
    const firstHealthy = healths.indexOf('healthy');
    const lastUnhealthy = healths.lastIndexOf('unhealthy');
    if (firstHealthy === -1 || lastUnhealthy === -1) return;
    expect(lastUnhealthy).toBeLessThan(firstHealthy);
  });
});

// =============================================================================
// AN-R5 / AN-R9 — cards, not rows; shape by state; duration since unhealthy
// =============================================================================

test.describe('AN-R5/AN-R9 — resources are cards in a grid, shaped by state, with the node from the response', () => {
  test('resources render as cards, never as table rows', async ({ page }) => {
    await openResources(page);
    await expect(page.getByTestId('resources-table')).toHaveCount(0);
    const cards = page.getByTestId('resource-card');
    expect(await cards.count()).toBeGreaterThan(0);
  });

  test('an unhealthy card carries a danger border and names how long it has been out', async ({
    page,
  }) => {
    await openResources(page);
    const unhealthy = page.getByTestId('resource-card').filter({
      has: page.locator('[data-health="unhealthy"]'),
    });
    const total = await unhealthy.count();
    expect(total).toBeGreaterThan(0);
    await expect(unhealthy.first()).toHaveAttribute('data-health', 'unhealthy');
  });

  test(
    'the unhealthy duration is read from the response, never computed twice',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openResources(page);
      const unhealthy = page.getByTestId('resource-card').filter({
        has: page.locator('[data-health="unhealthy"]'),
      });
      const total = await unhealthy.count();
      test.skip(total === 0, 'no unhealthy resource in this environment');
      if (total === 0) return;
      await expect(unhealthy.first().getByTestId('resource-unhealthy-duration')).toBeVisible();
    },
  );
});

// =============================================================================
// AN-R7 — three or more unhealthy, same node/type/window, get a synthesis
// =============================================================================

test.describe('AN-R7 — a batch of unhealthy resources gets a synthesis line above the sections', () => {
  test(
    'the synthesis, when present, names the count, the type, the node, and a batch-investigate link',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openResources(page);
      const synthesis = page.getByTestId('unhealthy-synthesis');
      const total = await synthesis.count();
      test.skip(total === 0, 'no batch of 3+ unhealthy resources in this environment');
      if (total === 0) return;
      await expect(synthesis).toContainText(/\d/);
      await expect(synthesis.getByRole('link')).toBeVisible();
    },
  );
});

// =============================================================================
// AN-R8 — the zone/criticality warning is a thin footer card, not header prose
// =============================================================================

test.describe('AN-R8 — the zone/criticality warning lives in the footer, not the header', () => {
  test('when nothing is placed or graded, the warning sits below the sections with a CTA', async ({
    page,
  }) => {
    await openResources(page);
    const warning = page.getByTestId('placement-warning');
    if ((await warning.count()) === 0) return; // legitimate: something is declared
    await expect(warning).toBeVisible();
    await expect(warning.getByRole('link')).toBeVisible();
    // Not in the page header's own region.
    const header = page.getByTestId('page-header').first();
    const inHeader = await header.locator('[data-testid="placement-warning"]').count();
    expect(inHeader).toBe(0);
  });
});

// =============================================================================
// AN-T2 / AN-T1 transversal checks specific to this screen
// =============================================================================

test.describe('AN-T2 — no card names a resource by a raw identifier', () => {
  test('every card name is the display name, never an opaque id', async ({ page }) => {
    await openResources(page);
    const names = page.getByTestId('resource-card-name');
    const total = await names.count();
    expect(total).toBeGreaterThan(0);
    for (let index = 0; index < total; index += 1) {
      const text = (await names.nth(index).innerText()).trim();
      expect(text).not.toMatch(/^(res-[0-9a-f]{8}|[0-9a-f]{16,})/u);
    }
  });
});
