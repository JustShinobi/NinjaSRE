import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The normative claims of the mockup's Integrations catalogue (`#m4`) and
 * Alert intake (`#m3`) screens, encoded before either screen carries them.
 *
 * Written against the `populated` scenario — the only one the `behaviour`
 * project serves for its whole run (`playwright.config.ts`) — with the
 * credential states and the delivery token an earlier slice of this same
 * feature added to that dataset: `alertmanager` verified, `loki` stored but
 * never checked, `chat` healthy, `ticketing` failing, and a token named
 * "Alert delivery" carrying the delivery permission. `prometheus` is left
 * deliberately unconfigured and unsuggested, which is what makes it safe to
 * use below as "some real, searchable, still-Available catalogue item".
 *
 * **Six groups, matching the six claims this file exists to cover — nothing
 * beyond them.** Catalogue, Slide-over, a verified integration's panel,
 * Alert intake's three sources, the receiver YAML and the trust line, and
 * the four-node chain. Anything else the full specification asks for —
 * the estate-discovered address placeholder, the roadmap footer wording on
 * Alert intake itself, "no suggestions at all", more than one delivery
 * token — belongs to a later slice and is not encoded here.
 *
 * **This spec's own conventions, which the implementation is expected to
 * adopt rather than invent a second set of:**
 *
 * - `data-testid="available-section"` does not exist yet — the catalogue's
 *   third group of cards has no heading of its own today. The order check
 *   below looks for a leaf element whose own text reads exactly "Available"
 *   instead, so it does not depend on that testid existing to prove the
 *   heading is missing.
 * - The chain (`#m3`'s fourth callout) is read through `data-testid`
 *   `"chain-node"`, one per node, each carrying `data-role` of `"intake"`,
 *   `"rule"`, `"action"` or `"destination"` in that order — a convention
 *   this file invents because nothing renders a chain at all today.
 *
 * **Several of these claims are already true, for real reasons named at each
 * one.** Feature 030 already built the delivery-token trust line; feature
 * 001 already cut intake to exactly three sources; the two scroll budgets
 * already hold; `Reference` ("Format & test") starts collapsed by design.
 * Every one of those was temporarily broken at its own source, watched red,
 * and restored — see `controle.md` for the failure text each one produced.
 * A claim that never went red here proves nothing about the property it
 * names, so none of them is reported as "covered" without that step.
 */

function constant(name: string): number {
  const source = readFileSync(
    fileURLToPath(new URL('../../../config/constants/surfaces.py', import.meta.url)),
    'utf8',
  );
  const found = new RegExp(`^${name}: Final\\[(?:int|float)\\] = ([0-9.]+)`, 'm').exec(
    source,
  );
  if (found?.[1] === undefined) {
    throw new Error(`${name} is not declared in config/constants/surfaces.py`);
  }
  return Number(found[1]);
}

// 1920x1080, read from the same named constants the product's own scroll
// budget instrument reads, never repeated as a literal. The global Playwright
// viewport (1440x900, `playwright.config.ts`) would measure a different,
// narrower layout, so only the two scroll-budget groups below override it.
const VIEWPORT_WIDTH = constant('CONFIG_SCREEN_VIEWPORT_WIDTH_PX');
const VIEWPORT_HEIGHT = constant('CONFIG_SCREEN_VIEWPORT_HEIGHT_PX');
const BUDGET_VIEWPORTS = constant('CONFIG_SCREEN_SCROLL_BUDGET_VIEWPORTS');
const BUDGET_PX = VIEWPORT_HEIGHT * BUDGET_VIEWPORTS;

const CATALOGUE_ROUTE = '/integrations';
// alertmanager: verified, connected, and the one route the mockup's own M4
// screenshot addresses directly — the deployment's own real, checkable state
// rather than a vendor picked for this test.
const VERIFIED_INTEGRATION_ROUTE = '/integrations/alertmanager';
const INTAKE_ROUTE = '/settings/alert-intake';

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

// =============================================================================
// Catalogue (#m4)
// =============================================================================

test.describe('catalogue: three sections in order, no pagination, one count, search inside every section', () => {
  test('Connected, Suggested by your estate and "Available" appear in that order', async ({
    page,
  }) => {
    await page.goto(CATALOGUE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const positions = await page.evaluate(() => {
      const all = Array.from(document.body.querySelectorAll('*'));
      const indexOf = (predicate: (element: Element) => boolean): number =>
        all.findIndex(predicate);
      return {
        connected: indexOf(
          (element) => element.getAttribute('data-testid') === 'connected-section',
        ),
        suggested: indexOf(
          (element) => element.getAttribute('data-testid') === 'suggested-section',
        ),
        // A leaf whose own text is exactly "Available" — not a wrapping
        // container whose combined textContent happens to include the word.
        available: indexOf(
          (element) =>
            element.children.length === 0 && element.textContent.trim() === 'Available',
        ),
        grid: indexOf(
          (element) => element.getAttribute('data-testid') === 'catalogue-grid',
        ),
      };
    });

    expect(
      positions.connected,
      'connected-section is not in the document',
    ).toBeGreaterThanOrEqual(0);
    expect(
      positions.suggested,
      'suggested-section is not in the document',
    ).toBeGreaterThanOrEqual(0);
    expect(
      positions.available,
      'no leaf element reads exactly "Available" — the catalogue’s third section has no heading of its own yet',
    ).toBeGreaterThanOrEqual(0);
    expect(
      positions.grid,
      'catalogue-grid is not in the document',
    ).toBeGreaterThanOrEqual(0);

    expect(
      positions.connected < positions.suggested &&
        positions.suggested < positions.available &&
        positions.available <= positions.grid,
      `expected connected-section < suggested-section < "Available" <= catalogue-grid in document order, got ${JSON.stringify(positions)}`,
    ).toBe(true);
  });

  test('no pagination control renders, and no "Page N of M" text appears anywhere on the page', async ({
    page,
  }) => {
    await page.goto(CATALOGUE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();
    await expect(page.getByTestId('catalogue-grid')).toBeVisible();

    await expect(page.getByRole('navigation', { name: /pagination/i })).toHaveCount(0);
    const body = await page.locator('body').innerText();
    expect(body, 'a "Page N of M" position is visible on the page').not.toMatch(
      /Page\s+\d+\s+of\s+\d+/,
    );
  });

  test('the top of the page states one count, and it agrees with what the page actually lists', async ({
    page,
  }) => {
    await page.goto(CATALOGUE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const summary = await page.getByTestId('catalogue-summary').innerText();
    const found = [...summary.matchAll(/\d+/g)].map((match) => Number(match[0]));
    const total = found[0];
    const connected = found[1];
    if (total === undefined || connected === undefined) {
      throw new Error(`catalogue-summary carries fewer than 2 numbers: "${summary}"`);
    }
    const suggested = found[2];

    const connectedRows = await page.getByTestId('connected-integration').count();
    const suggestedRows = await page.getByTestId('suggested-integration').count();
    const availableRows = await page.getByTestId('catalogue-item').count();

    expect(
      connected,
      `the header says ${String(connected)} connected, but ${String(connectedRows)} connected-integration rows are drawn`,
    ).toBe(connectedRows);
    if (suggested !== undefined) {
      expect(
        suggested,
        `the header says ${String(suggested)} suggested, but ${String(suggestedRows)} suggested-integration rows are drawn`,
      ).toBe(suggestedRows);
    }
    expect(
      total,
      `the header says ${String(total)} total, but ${String(connectedRows)} connected + ${String(suggestedRows)} suggested + ${String(availableRows)} available = ${String(connectedRows + suggestedRows + availableRows)} are actually drawn`,
    ).toBe(connectedRows + suggestedRows + availableRows);
  });

  test('searching by an item’s own name narrows every section, not only Available', async ({
    page,
  }) => {
    await page.goto(CATALOGUE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const connectedBefore = await page.getByTestId('connected-integration').count();
    test.skip(
      connectedBefore < 2,
      'fewer than 2 connected integrations on this dataset — cannot tell "narrowed to 1" from "always showed 1"',
    );

    const target = await page
      .getByTestId('connected-integration')
      .first()
      .getAttribute('data-integration');
    if (target === null || target === '') {
      throw new Error('connected-integration carries no data-integration attribute');
    }

    await page.getByTestId('catalogue-search').getByRole('searchbox').fill(target);

    await expect
      .poll(() => page.getByTestId('connected-integration').count(), {
        message: `typing "${target}" was expected to narrow Connected from ${String(connectedBefore)} to 1; it did not`,
      })
      .toBe(1);
    await expect(page.getByTestId('connected-integration').first()).toHaveAttribute(
      'data-integration',
      target,
    );
  });

  test('searching by a capability narrows every section, not only Available', async ({
    page,
  }) => {
    await page.goto(CATALOGUE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const connectedBefore = await page.getByTestId('connected-integration').count();
    const suggestedBefore = await page.getByTestId('suggested-integration').count();

    // "resource_pressure" is Prometheus's own capability identifier
    // (`prometheus_resource_pressure`) — unique among this deployment's
    // vendor packages, and Prometheus stays unconfigured and unsuggested on
    // this dataset, so this exercises capability search through a real value
    // the catalogue actually carries rather than an invented keyword.
    await page
      .getByTestId('catalogue-search')
      .getByRole('searchbox')
      .fill('resource_pressure');

    await expect
      .poll(() => page.getByTestId('catalogue-item').count(), {
        message:
          'searching "resource_pressure" was expected to narrow Available to exactly Prometheus',
      })
      .toBe(1);
    await expect(page.getByTestId('catalogue-item').first()).toHaveAttribute(
      'data-integration',
      'prometheus',
    );

    if (connectedBefore > 0) {
      await expect(
        page.getByTestId('connected-section'),
        'Connected still renders while nothing in it matches "resource_pressure"',
      ).toBeHidden();
    }
    if (suggestedBefore > 0) {
      await expect(
        page.getByTestId('suggested-section'),
        'Suggested still renders while nothing in it matches "resource_pressure"',
      ).toBeHidden();
    }
  });

  test('the footer names how many integrations moved to the roadmap, with a link to the list', async ({
    page,
  }) => {
    await page.goto(CATALOGUE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const footer = page.getByTestId('not-covered-link');
    await expect(footer).toBeVisible();
    const text = await footer.innerText();
    expect(
      text,
      `the footer link reads "${text}", not "… moved to the roadmap …"`,
    ).toMatch(/moved to the roadmap/i);
    await expect(footer).toHaveAttribute('href', '/integrations/not-covered');
  });
});

test.describe('catalogue: scroll budget at 1920x1080', () => {
  test.use({ viewport: { width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT } });

  test('the whole post-cut catalogue fits within 2 viewports', async ({ page }) => {
    await page.goto(CATALOGUE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    expect(
      height,
      `/integrations is ${String(height)}px tall against a ${String(BUDGET_PX)}px budget (${String(BUDGET_VIEWPORTS)} viewports of ${String(VIEWPORT_HEIGHT)}px)`,
    ).toBeLessThanOrEqual(BUDGET_PX);
  });
});

// =============================================================================
// Slide-over (#m4)
// =============================================================================

test.describe('slide-over: overlaid on the catalogue, scroll position untouched', () => {
  test('opening a card does not move the scroll position', async ({ page }) => {
    await page.goto(CATALOGUE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    // Scrolled to the card itself — the last one in Available, per the
    // acceptance scenario's own "catalogue scrolled to the Available
    // section" — not to the document's absolute bottom. The panel this
    // click opens renders after the roadmap footer and the advanced
    // configuration section, so scrolling all the way down first would put
    // the viewport where the panel is about to appear anyway, and a jump
    // straight to the defect would read as "no movement".
    const card = page.getByTestId('catalogue-item').last();
    await card.scrollIntoViewIfNeeded();
    const before = await page.evaluate(() => window.scrollY);
    test.skip(
      before <= 20,
      'the last catalogue item is already at the top on this dataset — there is nowhere left to scroll further to catch a jump',
    );

    await card.getByRole('link').click();
    await expect(page.getByRole('dialog')).toBeVisible();

    const whileOpen = await page.evaluate(() => window.scrollY);
    // Both directions: a one-sided bound ("not less than before − 20") would
    // still pass a scroll that jumped *further down* to reach the panel —
    // exactly the defect this test exists to catch — because a larger
    // number is still "greater than before − 20".
    const delta = Math.abs(whileOpen - before);
    expect(
      delta,
      `scroll moved from ${String(before)}px to ${String(whileOpen)}px (Δ${String(delta)}px) the moment the panel opened`,
    ).toBeLessThan(20);
  });

  test('the panel overlaps the catalogue instead of sitting at the foot of the document', async ({
    page,
  }) => {
    await page.goto(CATALOGUE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();
    const heightClosed = await page.evaluate(
      () => document.documentElement.scrollHeight,
    );

    await page.evaluate(() => {
      window.scrollTo(0, document.documentElement.scrollHeight);
    });
    const card = page.getByTestId('catalogue-item').first();
    await card.getByRole('link').click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // (1) Visible without scrolling any further — the operative meaning of
    // "overlaid on the catalogue" rather than "appended after it".
    await expect(
      dialog,
      'the open panel is not within the current viewport without scrolling further',
    ).toBeInViewport();

    // (2) Taken out of normal flow. A plain in-flow block reports "static",
    // the default for any element that never received a position.
    const position = await dialog.evaluate((node) => getComputedStyle(node).position);
    expect(position, `the panel’s own computed position is "${position}"`).not.toBe(
      'static',
    );

    // (3) Does not grow the document to fit itself in — a panel appended at
    // the end of the document, even if it changed no scroll offset, would
    // still add its own height to the total.
    const heightOpen = await page.evaluate(() => document.documentElement.scrollHeight);
    expect(
      heightOpen,
      `the document grew from ${String(heightClosed)}px to ${String(heightOpen)}px when the panel opened`,
    ).toBeLessThanOrEqual(heightClosed + 20);
  });

  test('a deep link opens the panel with the catalogue scrolled to its own top', async ({
    page,
  }) => {
    await page.goto(VERIFIED_INTEGRATION_ROUTE);
    await expect(page.getByRole('dialog')).toBeVisible();
    const scrollY = await page.evaluate(() => window.scrollY);
    expect(
      scrollY,
      `the deep link landed at scrollY=${String(scrollY)}, not at the catalogue’s own top`,
    ).toBeLessThanOrEqual(20);
  });

  test('closing the panel restores both the scroll position and the active filters', async ({
    page,
  }) => {
    await page.goto(`${CATALOGUE_ROUTE}?q=a`);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const scrollable = await page.evaluate(
      () => document.documentElement.scrollHeight - window.innerHeight,
    );
    test.skip(
      scrollable <= 100,
      'the page is not tall enough on this dataset for a scroll-position measurement to mean anything',
    );

    await page.evaluate(() => {
      window.scrollTo(0, document.documentElement.scrollHeight);
    });
    const before = await page.evaluate(() => window.scrollY);
    expect(before).toBeGreaterThan(0);

    const card = page.getByTestId('catalogue-item').last();
    await card.getByRole('link').click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page).toHaveURL(/q=a\b/);

    await page.getByRole('dialog').getByRole('button', { name: /close/i }).click();
    await expect(page.getByRole('dialog')).toBeHidden();
    await expect(page).toHaveURL(/q=a\b/);

    await expect
      .poll(
        () =>
          page.evaluate((origin: number) => Math.abs(window.scrollY - origin), before),
        {
          message: `expected scroll to return within 20px of ${String(before)}px after closing`,
        },
      )
      .toBeLessThan(20);
  });
});

// =============================================================================
// A verified integration's panel (#m4)
// =============================================================================

test.describe('a connected, verified integration shows what can be done with it', () => {
  test('no empty credential field is paired with a disabled action', async ({
    page,
  }) => {
    await page.goto(VERIFIED_INTEGRATION_ROUTE);
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    const submit = dialog.getByTestId('store-credential');
    const submitCount = await submit.count();
    let emptyFieldWithDisabledAction = false;
    if (submitCount > 0 && (await submit.getAttribute('data-state')) === 'disabled') {
      const inputs = dialog.getByTestId('credential').locator('input');
      const inputCount = await inputs.count();
      for (let index = 0; index < inputCount; index += 1) {
        if ((await inputs.nth(index).inputValue()) === '') {
          emptyFieldWithDisabledAction = true;
          break;
        }
      }
    }
    expect(
      emptyFieldWithDisabledAction,
      'alertmanager is connected and verified, yet the panel shows an empty credential field beside a disabled action',
    ).toBe(false);
  });

  test('offers Test again, Replace credential and Disconnect, named', async ({
    page,
  }) => {
    await page.goto(VERIFIED_INTEGRATION_ROUTE);
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    await expect(dialog.getByRole('button', { name: /^Test again$/ })).toBeVisible();
    await expect(
      dialog.getByRole('button', { name: /^Replace credential$/ }),
    ).toBeVisible();
    // `Button`'s destructive variant appends "(destructive)" to the
    // accessible name (`components/action.tsx`), so this matches the visible
    // word as a prefix rather than the whole accessible name.
    await expect(dialog.getByRole('button', { name: /^Disconnect/ })).toBeVisible();
  });
});

// =============================================================================
// Alert intake: three sources with real state (#m3)
// =============================================================================

test.describe('alert intake: exactly three sources, each with its real state', () => {
  test('exactly three sources are listed', async ({ page }) => {
    await page.goto(INTAKE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();
    await expect(page.getByTestId('ingress-source')).toHaveCount(3);
  });

  test('the receiving source carries the exact "Receiving" chip; the silent ones carry "Ready — nothing arrived yet"', async ({
    page,
  }) => {
    await page.goto(INTAKE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const sources = page.getByTestId('ingress-source');
    const count = await sources.count();
    for (let index = 0; index < count; index += 1) {
      const row = sources.nth(index);
      const silent = (await row.getAttribute('data-never-delivered')) === 'true';
      const expected = silent ? 'Ready — nothing arrived yet' : 'Receiving';
      const name = await row.getAttribute('data-source');
      await expect(
        row.getByText(expected, { exact: true }),
        `source "${name ?? String(index)}" does not carry the exact chip "${expected}"`,
      ).toBeVisible();
    }
  });

  test('the receiving source is expanded with its last delivery and this week’s volume', async ({
    page,
  }) => {
    await page.goto(INTAKE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const receiving = page
      .locator('[data-testid="ingress-source"][data-never-delivered="false"]')
      .first();
    await expect(receiving).toBeVisible();
    await expect(
      receiving.getByText(/\d+\s+this week/i),
      'no "N this week" delivery volume is shown for the receiving source',
    ).toBeVisible();
    await expect(
      receiving.getByText(/ago/i),
      'no relative last-delivery time is shown for the receiving source',
    ).toBeVisible();
  });

  test('a silent source renders as one compact line, not the full card', async ({
    page,
  }) => {
    await page.goto(INTAKE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const receiving = page
      .locator('[data-testid="ingress-source"][data-never-delivered="false"]')
      .first();
    const silent = page
      .locator('[data-testid="ingress-source"][data-never-delivered="true"]')
      .first();
    await expect(receiving).toBeVisible();
    await expect(silent).toBeVisible();

    const receivingHeight = (await receiving.boundingBox())?.height;
    const silentHeight = (await silent.boundingBox())?.height;
    if (receivingHeight === undefined || silentHeight === undefined) {
      throw new Error('one of the two source rows reported no bounding box');
    }
    expect(
      silentHeight,
      `a silent source is ${String(silentHeight)}px tall, the receiving one is ${String(receivingHeight)}px — expected the silent one to be a single compact line, well under half`,
    ).toBeLessThan(receivingHeight / 2);
  });

  test('"Format & test" is collapsed by default', async ({ page }) => {
    await page.goto(INTAKE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const references = page.getByTestId('reference');
    const count = await references.count();
    expect(count, 'no "Format & test" section is drawn at all').toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      await expect(references.nth(index)).toHaveAttribute('data-expanded', 'false');
    }
  });
});

test.describe('alert intake: scroll budget at 1920x1080', () => {
  test.use({ viewport: { width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT } });

  test('the whole screen fits within 2 viewports', async ({ page }) => {
    await page.goto(INTAKE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    expect(
      height,
      `/settings/alert-intake is ${String(height)}px tall against a ${String(BUDGET_PX)}px budget (${String(BUDGET_VIEWPORTS)} viewports of ${String(VIEWPORT_HEIGHT)}px)`,
    ).toBeLessThanOrEqual(BUDGET_PX);
  });
});

// =============================================================================
// The receiver YAML and the delivery-token trust line (#m3)
// =============================================================================

test.describe('the Alertmanager receiver YAML and the delivery-token trust line', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'], {
      origin: baseURL ?? 'http://127.0.0.1:8423',
    });
  });

  test('the copied receiver YAML carries this deployment’s own delivery URL and the delivery token’s name', async ({
    page,
  }) => {
    await page.goto(INTAKE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const alertmanagerRow = page.locator(
      '[data-testid="ingress-source"][data-source="alertmanager"]',
    );
    await expect(alertmanagerRow).toBeVisible();

    const url = (
      await alertmanagerRow.getByTestId('ingress-url').locator('code').innerText()
    ).trim();
    expect(url, 'no full delivery URL is shown for the Alertmanager source').not.toBe(
      '',
    );

    const tokenName = (
      await page.getByTestId('delivery-token-name').innerText()
    ).trim();
    expect(tokenName, 'no delivery token is currently named on this screen').not.toBe(
      '',
    );

    const button = alertmanagerRow.getByRole('button', {
      name: 'Copy Alertmanager receiver YAML',
    });
    await expect(button).toBeVisible();
    await button.click();

    const copied = await page.evaluate(() => navigator.clipboard.readText());
    expect(
      copied,
      `the copied text does not contain the delivery URL (${url}): ${copied}`,
    ).toContain(url);
    expect(
      copied,
      `the copied text does not name the delivery token (${tokenName}): ${copied}`,
    ).toContain(tokenName);
    expect(
      copied,
      'the copied text does not look like a webhook_configs block',
    ).toContain('webhook_configs');
  });

  test('the trust line names the delivery token and offers to rotate it', async ({
    page,
  }) => {
    await page.goto(INTAKE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const trust = page.getByTestId('delivery-token-trust');
    await expect(trust).toBeVisible();
    await expect(trust).toContainText('Authenticated with delivery token');

    const tokenName = (
      await page.getByTestId('delivery-token-name').innerText()
    ).trim();
    expect(tokenName, 'the trust line names no delivery token').not.toBe('');

    await expect(page.getByRole('button', { name: /rotate/i })).toBeVisible();
  });

  test('no source shows the raw permission name as its trust mechanism', async ({
    page,
  }) => {
    await page.goto(INTAKE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    // Every "Format & test" section is opened first: the raw permission, if
    // it is shown at all, has historically lived in the "Trusted by …" line
    // inside it — invisible to `body.innerText()` while collapsed, which is
    // exactly how a leak here could go unnoticed by a check that never opens
    // it.
    //
    // Scoped per row rather than queried once across the whole page by
    // `[aria-expanded="false"]`: that selector is exactly what each click
    // changes, so a live locator re-evaluated after every click silently
    // reindexes the remaining buttons and — once fewer of them match than
    // the loop still expects — hangs waiting for an index that will never
    // appear (`Locator.all()` does not fix this either: its entries still
    // resolve against the same live, shrinking selector). Each
    // `ingress-source` row is a stable parent that never disappears when its
    // own toggle's `aria-expanded` flips, so resolving one toggle per row,
    // from a fixed list of rows, sidesteps the whole class of failure.
    const rows = await page.getByTestId('ingress-source').all();
    for (const row of rows) {
      const toggle = row
        .getByTestId('reference')
        .locator('button[aria-expanded]')
        .first();
      if ((await toggle.count()) > 0) {
        await toggle.click();
      }
    }

    const body = await page.locator('body').innerText();
    expect(
      body,
      'the raw permission name "webhook.deliver" is visible somewhere on the screen',
    ).not.toMatch(/webhook\.deliver/);
  });
});

// =============================================================================
// The chain: intake, rule, action, destination (#m3)
// =============================================================================

test.describe('the chain: intake, rule, action and destination, in one line', () => {
  test('four nodes render in order, each carrying a real, non-empty value', async ({
    page,
  }) => {
    await page.goto(INTAKE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const nodes = page.getByTestId('chain-node');
    await expect(nodes).toHaveCount(4);

    const roles = await nodes.evaluateAll((elements) =>
      elements.map((element) => element.getAttribute('data-role')),
    );
    expect(
      roles,
      `expected the four nodes in order intake, rule, action, destination; got ${JSON.stringify(roles)}`,
    ).toEqual(['intake', 'rule', 'action', 'destination']);

    const texts = await nodes.allInnerTexts();
    for (const [index, text] of texts.entries()) {
      expect(
        text.trim(),
        `chain node ${String(index)} (${roles[index] ?? ''}) carries no visible value`,
      ).not.toBe('');
    }

    // The rule node is cross-referenced against the routing rules this same
    // screen already lists, rather than compared to a value this test chose
    // itself — proving the node names something real, not an example.
    const ruleTexts = await page
      .getByTestId(/routing-rule|catch-all-rule/)
      .allInnerTexts();
    const combinedRuleTexts = ruleTexts.join(' | ');
    const ruleNode = page.locator('[data-testid="chain-node"][data-role="rule"]');
    const ruleNodeText = (await ruleNode.innerText()).trim();
    expect(
      combinedRuleTexts.length === 0 || combinedRuleTexts.includes(ruleNodeText),
      `the rule node ("${ruleNodeText}") does not match anything the routing rules panel lists ("${combinedRuleTexts}")`,
    ).toBe(true);
  });

  test('the destination node navigates to the section whose name matches what it promises', async ({
    page,
  }) => {
    await page.goto(INTAKE_ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const destination = page.locator(
      '[data-testid="chain-node"][data-role="destination"]',
    );
    await expect(destination).toBeVisible();

    const link = destination.getByRole('link');
    if ((await link.count()) > 0) {
      await link.first().click();
    } else {
      await destination.click();
    }
    await expect(page).toHaveURL(/\/settings\/schedules-destinations/);
  });
});
