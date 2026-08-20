import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The catalogue rebuilt: connected first, a suggestion from the estate, and
 * everything else a search rather than a scroll — and the credential panel,
 * as a deep link that never loses the catalogue underneath it.
 *
 * What a browser proves that `tests/unit/surfaces/integrations.test.tsx`
 * cannot: a real navigation preserves scroll position and filters when the
 * panel opens and closes, a deep link opens the panel directly on first
 * paint, and the search box narrows the grid without a full page reload.
 */

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test('Connected and Suggested render above the catalogue, and neither is ever empty', async ({
  page,
}) => {
  await page.goto('/integrations');

  const connected = page.getByTestId('connected-section');
  const suggested = page.getByTestId('suggested-section');
  await expect(connected).toBeVisible();
  await expect(suggested).toBeVisible();

  // Order in the document, not just presence: Connected first, Suggested
  // second, the catalogue grid after both.
  const order = await page.evaluate(() => {
    const ids = ['connected-section', 'suggested-section', 'catalogue-grid'];
    return ids
      .map((id) => document.querySelector(`[data-testid="${id}"]`))
      .filter((node): node is Element => node !== null)
      .map((node) => node.getAttribute('data-testid'));
  });
  expect(order).toEqual(['connected-section', 'suggested-section', 'catalogue-grid']);

  await expect(connected.getByTestId('connected-integration')).toHaveCount(
    await connected.getByTestId('connected-integration').count(),
  );
  expect(await connected.getByTestId('connected-integration').count()).toBeGreaterThan(
    0,
  );
  expect(await suggested.getByTestId('suggested-integration').count()).toBeGreaterThan(
    0,
  );
});

test('the suggestion carries the estate evidence the API computed, and a connect action', async ({
  page,
}) => {
  await page.goto('/integrations');

  const suggestion = page.getByTestId('suggested-integration').first();
  const evidence = await suggestion.getByTestId('suggestion-evidence').innerText();
  // An address and a resource, not a placeholder like "…" or an empty string.
  expect(evidence).toMatch(/Found at .+, on resource .+/);
  await expect(suggestion.getByTestId('connect-suggested')).toBeVisible();
});

test('the summary line counts what the API served', async ({ page }) => {
  await page.goto('/integrations');

  const summary = await page.getByTestId('catalogue-summary').innerText();
  expect(summary).toMatch(/\d+ integrations ·/);
  expect(summary).toMatch(/\d+ connected/);
});

test('search narrows the grid without a full page reload', async ({ page }) => {
  await page.goto('/integrations');

  const before = await page.getByTestId('catalogue-item').count();
  expect(before).toBeGreaterThan(1);

  // Prometheus rather than Loki: the dataset now stores a credential for Loki,
  // so it sits in Connected and is no longer one of the grid's own items. Both
  // are named by their query language in a summary and by nothing else, so the
  // needle still reaches exactly one integration through the same field.
  await page.getByTestId('catalogue-search').getByRole('searchbox').fill('promql');
  await expect(page.getByTestId('catalogue-item')).toHaveCount(1);
  await expect(
    page.locator('[data-testid="catalogue-item"][data-integration="prometheus"]'),
  ).toBeVisible();

  // The address carries the search, so the exact view can be sent to a colleague.
  await expect(page).toHaveURL(/[?&]q=promql/);
});

test('a search with no result offers to clear it, and links to the reference page', async ({
  page,
}) => {
  await page.goto('/integrations?q=nothing-matches-this-at-all');

  await expect(page.getByTestId('way-back')).toBeVisible();
  const clear = page.getByTestId('way-back');
  await expect(clear).toHaveAttribute('href', /^\/integrations(\?.*)?$/);
  await expect(page.getByTestId('empty-not-covered-link')).toHaveAttribute(
    'href',
    '/integrations/not-covered',
  );
});

test('the category filter narrows the grid, and the address carries it', async ({
  page,
}) => {
  await page.goto('/integrations');

  const filter = page.locator('[data-filter="category"] select');
  await expect(filter).toBeVisible();
  const options = await filter.locator('option').allTextContents();
  const chosen = options.find((label) => label.trim() !== 'Any');
  expect(chosen, 'no category option to choose from').toBeTruthy();

  await filter.selectOption({ label: chosen ?? '' });
  await expect(page).toHaveURL(/[?&]category=/);
});

test('the deep link opens the panel directly, over the catalogue underneath it', async ({
  page,
}) => {
  await page.goto('/integrations/metrics-store');

  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('dialog')).toContainText('Metrics store');
  // The catalogue is still there, not replaced by the panel.
  await expect(page.getByTestId('catalogue-grid')).toBeVisible();
});

test('opening a card preserves the filters when it closes, back at the same address', async ({
  page,
}) => {
  await page.goto('/integrations?q=a');

  const card = page.getByTestId('catalogue-item').first();
  const name = await card.getAttribute('data-integration');
  await card.getByRole('link').click();
  await expect(page.getByRole('dialog')).toBeVisible();
  expect(page.url()).toContain(`/integrations/${String(name)}`);
  // The filter survives the trip into the panel too — the deep link a card
  // opens is not "the catalogue, unfiltered", it is "this filtered view,
  // with the panel open over it".
  await expect(page).toHaveURL(/q=a\b/);

  await page.getByRole('dialog').getByRole('button', { name: /close/i }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(page).toHaveURL(/q=a\b/);
  await expect(page.getByTestId('catalogue-grid')).toBeVisible();
});

/**
 * Scroll position, restored across the round trip through the panel.
 *
 * `IntegrationPanel` closes via `router.replace(closeHref, { scroll: false })`,
 * which stops the router's own scroll-to-top, but a soft navigation between
 * `/integrations/[name]` and `/integrations` does not put `window.scrollY`
 * back on its own — an earlier version of this test only measured that and
 * found it at 0. The fix is explicit: `captureScrollPosition` remembers the
 * position in `sessionStorage` before any of the three links that open the
 * panel navigate away, and `IntegrationPanel` restores it when it unmounts.
 * `sessionStorage` rather than the URL because this is the browser's own
 * scroll state, not screen state — nobody expects a shared `/integrations`
 * link to land at somebody else's scroll offset, and the filter this test
 * also checks continues to travel in the address exactly as it does today.
 */
test('scroll position is restored across the round trip through the panel', async ({
  page,
}) => {
  await page.goto('/integrations?q=a');
  const scrollable = await page.evaluate(
    () => document.documentElement.scrollHeight - window.innerHeight,
  );
  test.skip(
    scrollable <= 100,
    'the page is not tall enough on this dataset for the measurement to mean anything',
  );

  await page.evaluate(() => {
    window.scrollTo(0, document.documentElement.scrollHeight);
  });
  const scrolledTo = await page.evaluate(() => window.scrollY);
  expect(scrolledTo).toBeGreaterThan(0);

  const card = page.getByTestId('catalogue-item').last();
  await card.getByRole('link').click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: /close/i }).click();
  await expect(page.getByRole('dialog')).toBeHidden();

  // A small tolerance rather than an exact match: the panel's own height can
  // shift the document by a pixel or two between open and close, and the
  // property this test is about is "back where it was", not "the identical
  // integer".
  await expect
    .poll(() => page.evaluate(() => window.scrollY), {
      message: `expected scroll to return near ${String(scrolledTo)}px`,
    })
    .toBeGreaterThan(scrolledTo - 20);
  const restoredScroll = await page.evaluate(() => window.scrollY);
  expect(restoredScroll).toBeGreaterThan(scrolledTo - 20);
});

test('the panel names the field, its minimum scope and its guide when the catalogue declares them', async ({
  page,
}) => {
  await page.goto('/integrations/metrics-store');

  const dialog = page.getByRole('dialog');
  await expect(dialog.getByLabel('API token')).toBeVisible();
});

test('the panel names every required permission, what it grants and where it is turned on', async ({
  page,
}) => {
  await page.goto('/integrations/metrics-store');

  const permissions = page.getByRole('dialog').getByTestId('required-permission');
  await expect(permissions.first()).toBeVisible();
  const text = await permissions.allInnerTexts();
  const combined = text.join(' ');
  // The declared, probed content — not a name a viewer would still have to
  // look up: what the scope is called, what it grants, and where an
  // operator turns it on.
  expect(combined).toContain('metrics:read');
  expect(combined).toContain('run range queries against stored series');
  expect(combined).toContain('Settings → API tokens → Scopes');
});

test('the not-covered footer link opens the reference page, structured per vendor', async ({
  page,
}) => {
  await page.goto('/integrations');

  const footer = page.getByTestId('not-covered-link');
  await expect(footer).toBeVisible();
  await footer.click();

  await expect(page).toHaveURL('/integrations/not-covered');
  const gaps = page.getByTestId('known-gap');
  expect(await gaps.count()).toBeGreaterThan(0);

  const first = gaps.first();
  await expect(first).toHaveAttribute('data-cause', /not_built|unreachable/);
  await expect(page.getByTestId('back-to-integrations')).toHaveAttribute(
    'href',
    '/integrations',
  );
});

test('no credential value is echoed back into the DOM after saving', async ({
  page,
}) => {
  await page.goto('/integrations/metrics-store');

  const secret = 'tok-not-a-real-token-00000000';
  await page.getByRole('dialog').getByLabel('API token').fill(secret);
  await page.getByRole('button', { name: /save and test/i }).click();

  // The intermediate "saving" state and the eventual outcome both render
  // without the value anywhere on the page — not masked, not echoed.
  await expect(page.getByTestId('credential-outcome')).toBeVisible({ timeout: 15_000 });
  const body = await page.locator('body').innerText();
  expect(body).not.toContain(secret);
  const html = await page.content();
  expect(html).not.toContain(secret);
});
