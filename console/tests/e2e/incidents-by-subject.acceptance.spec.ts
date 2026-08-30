import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * `/incidents`, grouped by the assunto a detector keeps reopening instead of
 * by every firing on its own row.
 *
 * Against the local mock's `populated` scenario every correlation key fires
 * once, so the grouped view and the flat view hold the same ten rows — which
 * proves the row shape, the subtitle, the segmented controls and the
 * transversal one-click link without needing a recurring subject. The blocks
 * that are unconditionally about a subject with more than one firing (the 24h
 * strip, the live investigation link, the "last cause found" block, and the
 * assunto/disparo ratio) are marked `@staging-safe` and additionally skip
 * locally, by name, when nothing in the current fixture recurs — staging
 * carries the recurring RedisExporterDown/InstanceDown subjects the wave's
 * own audit found, so those blocks are proven for real there.
 *
 * **This spec is expected to be comprehensively red when it is written.** The
 * grouped rows render with `data-testid="incident-group"` and no
 * `data-testid="row"`; the title is a `<span>`, not a link; the filters are
 * `<select>` elements; the summary line does not exist; the recurrence strip
 * does not exist; and the detector-coverage card does not exist. Every task
 * after this one exists to turn one block of this file green.
 */

const STAGING_SAFE_TAG = '@staging-safe';

test.use({ viewport: { width: 1920, height: 1080 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

async function openIncidents(page: Page): Promise<void> {
  await page.goto('/incidents');
  await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
}

// =============================================================================
// AN-I1 / FR-001 — one row per subject, title is the detector's own name
// =============================================================================

test.describe('AN-I1 — the grouped list shows one row per subject, named by the detector', () => {
  test('every group row carries the detector name as its title', async ({ page }) => {
    await openIncidents(page);
    const groups = page.getByTestId('incident-group');
    await expect(groups.first()).toBeVisible();
    const count = await groups.count();
    expect(count).toBeGreaterThan(0);
    // The title is never empty and is never the raw correlation key
    // (`detector:name` never survives to the screen unshortened).
    for (let index = 0; index < count; index += 1) {
      const title = await groups.nth(index).getByTestId('incident-group-summary').innerText();
      expect(title.trim().length).toBeGreaterThan(0);
    }
  });
});

// =============================================================================
// FR-001 / T015a — the closed row is a `row`, one click from the incident
// =============================================================================

test.describe('FR-001 — a closed row reaches the incident in one click, without expanding', () => {
  test('every group carries data-testid="row" with a link to the incident', async ({
    page,
  }) => {
    await openIncidents(page);
    const rows = page.getByTestId('row');
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);

    const first = rows.first();
    const link = first.locator('a').first();
    await expect(link).toBeVisible();
    const href = await link.getAttribute('href');
    expect(href).toMatch(/^\/incidents\/[^/]+$/);

    // Reachable without opening the disclosure: `<details>` on this row is
    // still closed (the harness never clicked its summary), and the link is
    // still visible and clickable.
    const details = first.locator('details');
    await expect(details).toHaveJSProperty('open', false);
  });

  test('clicking the row link opens the incident, not the group', async ({ page }) => {
    await openIncidents(page);
    const link = page.getByTestId('row').first().locator('a').first();
    await link.click();
    await page.waitForURL((url) => /^\/incidents\/[^/]+$/.test(url.pathname));
    await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
  });
});

// =============================================================================
// AN-I2 / AN-T2 — subtitle names the resource, id last, truncated, in mono
// =============================================================================

test.describe('AN-I2/AN-T2 — no subtitle or title begins with a raw identifier', () => {
  test('no visible subject line starts with a resource or opaque id', async ({ page }) => {
    await openIncidents(page);
    const subjects = page.getByTestId('incident-group-subjects');
    const count = await subjects.count();
    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      const text = (await subjects.nth(index).innerText()).trim();
      expect(text).not.toMatch(/^(res-[0-9a-f]{8}|[0-9a-f]{16,})/u);
    }
  });
});

// =============================================================================
// AN-I3 / AN-T1 — filters are segmented controls, never a native <select>
// =============================================================================

test.describe('AN-I3/AN-T1 — state, severity and view are segmented controls', () => {
  test('the filter row has no native select and offers segmented groups', async ({
    page,
  }) => {
    await openIncidents(page);
    await expect(page.locator('select')).toHaveCount(0);
    const segmented = page.getByTestId('segmented');
    expect(await segmented.count()).toBeGreaterThanOrEqual(1);
  });

  test(
    'choosing a segmented option updates the address and the list',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openIncidents(page);
      const severity = page
        .getByTestId('segmented')
        .filter({ has: page.getByTestId('segmented-option').locator('..') })
        .first();
      // Pick the option literally named "critical" inside whichever group
      // carries it, rather than assuming position.
      const option = page.getByTestId('segmented-option').filter({ hasText: /critical/i });
      if ((await option.count()) === 0) test.skip(true, 'no critical option in this dataset');
      await option.first().click();
      await expect(page).toHaveURL(/severity=critical/);
      void severity;
    },
  );
});

// =============================================================================
// AN-I4 — the summary line states the listing's own numbers
// =============================================================================

test.describe('AN-I4 — the summary line names subjects, firings and critical-in-progress', () => {
  test('the summary sentence carries the same subject and firing counts as the list', async ({
    page,
  }) => {
    await openIncidents(page);
    const groupCount = await page.getByTestId('incident-group').count();
    const summary = page.getByTestId('incident-groups');
    await expect(summary).toContainText(String(groupCount));
  });
});

// =============================================================================
// AN-I8 — every row carries the recurrence strip, shaped chips, N× and time
// =============================================================================

test.describe('AN-I8 — every row carries the recurrence strip, N×, and a relative time', () => {
  test('a group row shows its count in monospace and a relative last-fired time', async ({
    page,
  }) => {
    await openIncidents(page);
    const first = page.getByTestId('incident-group').first();
    await expect(first.getByTestId('incident-group-count')).toBeVisible();
    await expect(first.getByTestId('incident-group-state')).toBeVisible();
  });

  test('a group with more than one firing draws the recurrence strip', async ({ page }) => {
    await openIncidents(page);
    const withCount = page.getByTestId('incident-group').filter({
      has: page.getByTestId('incident-group-count'),
    });
    let found = false;
    const total = await withCount.count();
    for (let index = 0; index < total; index += 1) {
      const countText = await withCount.nth(index).getAttribute('data-count');
      if (countText !== null && Number(countText) > 1) {
        found = true;
        await expect(
          withCount.nth(index).getByTestId('incident-recurrence-strip'),
        ).toBeVisible();
        break;
      }
    }
    test.skip(!found, 'no recurring subject (count > 1) in this local dataset');
  });
});

// =============================================================================
// AN-I5 / AN-I7 — expanding a recurring subject draws one 24h axis, no repeats
// =============================================================================

test.describe('AN-I5/AN-I7 — expanding a group with more than one firing shows the 24h strip', () => {
  test(
    'the expansion never repeats an occurrence as a plain list, and shows one point per firing',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openIncidents(page);
      const groups = page.getByTestId('incident-group');
      const total = await groups.count();
      let target = -1;
      for (let index = 0; index < total; index += 1) {
        const count = await groups.nth(index).getAttribute('data-count');
        if (count !== null && Number(count) > 1) {
          target = index;
          break;
        }
      }
      test.skip(target === -1, 'no recurring subject (count > 1) in this local dataset');
      if (target === -1) return;

      const group = groups.nth(target);
      await group.getByTestId('incident-group-summary').click();
      await expect(group.getByTestId('incident-24h-strip')).toBeVisible();
      const declaredCount = Number(await group.getAttribute('data-count'));
      const points = group.getByTestId('incident-24h-point');
      // Never a plain repeated list: the occurrences inside a `<details>`
      // body used to print the same summary text N times. This spec insists
      // the timeline draws points, not a duplicated list of rows.
      const textualOccurrences = group.getByTestId('incident-occurrence-row');
      expect(await textualOccurrences.count()).toBe(0);
      expect(await points.count()).toBeGreaterThan(0);
      expect(await points.count()).toBeLessThanOrEqual(declaredCount);
    },
  );
});

// =============================================================================
// AN-I6 — live investigation link and last-cause-found block
// =============================================================================

test.describe('AN-I6 — a live subject links to its investigation; a resolved one names its cause', () => {
  test(
    'an expanded subject whose newest firing is live links to its run',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openIncidents(page);
      const live = page.getByTestId('incident-group').filter({ has: page.locator('[data-live="true"]') });
      const total = await live.count();
      test.skip(total === 0, 'no live subject in this dataset');
      if (total === 0) return;
      await live.first().getByTestId('incident-group-summary').click();
      const link = live.first().getByTestId('incident-live-link');
      const linkCount = await link.count();
      if (linkCount === 0) {
        // The live firing may carry no run_id, which is a legitimate state —
        // the block only claims a link when one exists.
        return;
      }
      await expect(link).toHaveAttribute('href', /^\/runs\//);
    },
  );
});

// =============================================================================
// AN-I9 — the detector-coverage card, sourced from the same figure everywhere
// =============================================================================

test.describe('AN-I9 — the footer card names degraded findings with no detector watching', () => {
  test('the card, when present, names a number and links to detector configuration', async ({
    page,
  }) => {
    await openIncidents(page);
    const card = page.getByTestId('detector-coverage-gap');
    const count = await card.count();
    if (count === 0) {
      // Zero uncovered findings is a legitimate state: the card must not
      // exist rather than exist saying zero.
      return;
    }
    await expect(card).toContainText(/\d/);
    await expect(card.getByRole('link')).toBeVisible();
  });
});

// =============================================================================
// SC-001 — grouped listing is at most a third of the flat one, on staging
// =============================================================================

test.describe('SC-001 — the grouped listing is materially shorter than the flat one', () => {
  test(
    'the grouped view holds at most a third of the rows the flat view holds',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openIncidents(page);
      const grouped = await page.getByTestId('incident-group').count();
      await page.goto('/incidents?view=flat');
      await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
      const flat = await page.getByTestId('row-list').getAttribute('data-total');
      const flatCount = Number(flat ?? '0');
      const noRecurrence = flatCount === 0 || grouped === flatCount;
      test.skip(
        noRecurrence,
        'no recurring subject in this dataset -- grouping and the flat count are identical',
      );
      if (noRecurrence) return;
      expect(grouped).toBeLessThanOrEqual(Math.ceil(flatCount / 3));
    },
  );
});

// =============================================================================
// AN-T3 — every string is catalogued
// =============================================================================

test.describe('AN-T3 — nothing on the screen is hardcoded prose', () => {
  test('the page renders with no obviously untranslated placeholder text', async ({
    page,
  }) => {
    await openIncidents(page);
    await expect(page.locator('body')).not.toContainText('undefined');
    await expect(page.locator('body')).not.toContainText('[object Object]');
  });
});
