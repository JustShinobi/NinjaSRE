import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The normative claims of the mockup's Autonomy & guardrails screen (`#m2`).
 *
 * Written before the screen carries any of this, against the mock dataset this
 * project drives (`populated`, the scenario the `behaviour` project serves for
 * its whole run). The route resolves, with no `?node=` in the address, to the
 * organisation's own node — the one node in this dataset that carries an
 * active temporary override — so every claim below runs against that node.
 *
 * **The tab identifiers are this spec's own choice.** Nothing in the product
 * declares them yet: `posture`, `rules-windows` and `guardrails` are picked
 * here, in the same `?tab=` parameter and `TabLinks` shape the Decisions
 * screen already uses (`surfaces/screens/decisions.tsx`'s `DECISIONS_TABS`
 * and `TabLinks` from `components/navigation.tsx`), and the implementation that
 * makes this file pass is expected to adopt them rather than invent a second
 * set.
 *
 * **Two claims below are not written to fail today, on purpose:**
 *
 * - The guardrails table's Value column is already fully populated on this
 *   route (a property an earlier feature closed structurally). The claim
 *   here is a verification that the property survives the cut into tabs, not
 *   a reduction from some prior broken count — see its own comment.
 * - The retired "Look at the configuration" CTA cannot be exercised through
 *   the browser at all on this dataset: every node `populated` can resolve
 *   to carries at least one rule, one freeze and one budget, so none of this
 *   route's four empty states ever renders. That claim is asserted against
 *   the screen's own source instead, the same way `scroll-budget.spec.ts`
 *   and `transversal-rules.spec.ts` already read `surfaces.py` and
 *   `routes.ts` as ground truth rather than through a rendered control.
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
// narrower layout.
const VIEWPORT_WIDTH = constant('CONFIG_SCREEN_VIEWPORT_WIDTH_PX');
const VIEWPORT_HEIGHT = constant('CONFIG_SCREEN_VIEWPORT_HEIGHT_PX');
const TAB_BUDGET_VIEWPORTS = constant('CONFIG_SCREEN_TAB_SCROLL_BUDGET_VIEWPORTS');
const TAB_BUDGET_PX = VIEWPORT_HEIGHT * TAB_BUDGET_VIEWPORTS;

test.use({ viewport: { width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

const ROUTE = '/settings/autonomy-guardrails';

const TAB_IDS = ['posture', 'rules-windows', 'guardrails'] as const;

const TAB_LABEL: Readonly<Record<(typeof TAB_IDS)[number], string>> = {
  posture: 'Posture',
  'rules-windows': 'Rules & windows',
  guardrails: 'Guardrails',
};

// --- (a)-(d): one question per tab, addressable by the URL -----------------

test.describe('one question per tab, addressable by the URL', () => {
  test('three tabs are present, named Posture, Rules & windows and Guardrails, in that order', async ({
    page,
  }) => {
    await page.goto(ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const links = page.getByTestId('tab-links').getByTestId('tab-link');
    await expect(links).toHaveCount(3);
    await expect(links.nth(0)).toHaveText(TAB_LABEL.posture);
    await expect(links.nth(1)).toHaveText(TAB_LABEL['rules-windows']);
    await expect(links.nth(2)).toHaveText(TAB_LABEL.guardrails);
  });

  test('each tab is reachable at its own address, and the active tab is reflected in the URL', async ({
    page,
  }) => {
    // Opened directly, not reached by clicking through another tab first.
    await page.goto(`${ROUTE}?tab=guardrails`);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const tabs = page.getByTestId('tab-links').getByTestId('tab-link');
    await expect(tabs.filter({ hasText: TAB_LABEL.guardrails })).toHaveAttribute(
      'aria-current',
      'page',
    );

    const rulesWindowsLink = tabs.filter({ hasText: TAB_LABEL['rules-windows'] });
    await rulesWindowsLink.click();
    await expect(page).toHaveURL(/tab=rules-windows/);
    await expect(rulesWindowsLink).toHaveAttribute('aria-current', 'page');
  });

  test('the route with no tab named opens Posture, and so does an unknown tab name', async ({
    page,
  }) => {
    await page.goto(ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();
    const tabs = page.getByTestId('tab-links').getByTestId('tab-link');
    await expect(tabs.filter({ hasText: TAB_LABEL.posture })).toHaveAttribute(
      'aria-current',
      'page',
    );

    await page.goto(`${ROUTE}?tab=not-a-real-tab`);
    await expect(page.getByTestId('page-header')).toBeVisible();
    await expect(tabs.filter({ hasText: TAB_LABEL.posture })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  test('each tab stays within the per-tab scroll budget at 1920x1080', async ({
    page,
  }) => {
    for (const tab of TAB_IDS) {
      await page.goto(`${ROUTE}?tab=${tab}`);
      await expect(page.getByTestId('page-header')).toBeVisible();

      const height = await page.evaluate(() => document.documentElement.scrollHeight);
      expect(
        height,
        `tab=${tab} is ${String(height)}px tall against a ${String(TAB_BUDGET_PX)}px ` +
          `budget (${String(TAB_BUDGET_VIEWPORTS)} viewports of ${String(VIEWPORT_HEIGHT)}px)`,
      ).toBeLessThanOrEqual(TAB_BUDGET_PX);
    }
  });
});

// --- (g)-(h): the conceptual paragraphs are gone, no CTA misleads ----------

test.describe('the conceptual paragraphs are gone, and no CTA misleads about where it goes', () => {
  test('no paragraph sits between the title and the first control', async ({
    page,
  }) => {
    await page.goto(ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    // A DOM-order walk, not a lookup of the known offender: this must see a
    // paragraph wherever one sits, not merely confirm today's specific one is
    // there. Asserting only that "autonomy-glossary" is empty would pass the
    // day that block is deleted even if a new paragraph took its place
    // somewhere else before the first real control.
    //
    // Chrome is skipped, not just the header. Once tabs exist, `TabLinks`
    // renders as the header's own sibling — `surfaces/screens/decisions.tsx`
    // is the exact shape this route's own tabs are expected to copy — a
    // `<nav>` full of `<a>` elements. A walk that stopped at the first tag in
    // `CONTROL_TAGS` would treat that first tab link as "the first control"
    // and return on its very first iteration, passing with every conceptual
    // paragraph still sitting untouched below the tab strip. So every known
    // chrome block — the header, then the tab strip — is skipped by its own
    // subtree before the search for a paragraph or a real control begins.
    const violation = await page.evaluate(() => {
      const headerEl = document.querySelector('[data-testid="page-header"]');
      if (headerEl === null) return 'no page-header found';

      const all = Array.from(document.body.querySelectorAll('*'));
      let index = all.indexOf(headerEl);
      if (index === -1) return 'page-header is not attached under body';

      // Chrome blocks sit back to back, in document order: the header's own
      // subtree (breadcrumb, title, the required subtitle line, any header
      // action), then — once tabs exist — the tab strip's own subtree. Skip
      // each one in turn, however many of them are actually present, rather
      // than only the header.
      const CHROME_TESTIDS = ['page-header', 'tab-links'];
      for (;;) {
        const root = all[index];
        if (root === undefined) break;
        while (index + 1 < all.length && root.contains(all[index + 1] ?? null)) {
          index += 1;
        }
        const next = all[index + 1];
        const nextTestid = next === undefined ? null : next.getAttribute('data-testid');
        if (nextTestid === null || !CHROME_TESTIDS.includes(nextTestid)) break;
        index += 1;
      }

      const CONTROL_TAGS = new Set(['INPUT', 'SELECT', 'BUTTON', 'TEXTAREA', 'A']);
      for (let cursor = index + 1; cursor < all.length; cursor += 1) {
        const el = all[cursor];
        if (el === undefined) continue;
        if (el.tagName === 'P') {
          const text = el.textContent.trim().slice(0, 120);
          return `a paragraph sits before the first control: "${text}"`;
        }
        if (CONTROL_TAGS.has(el.tagName)) return null;
      }
      return null;
    });

    expect(violation).toBeNull();
  });

  test('the retired "Look at the configuration" CTA label is gone from this route', async ({
    page,
  }) => {
    await page.goto(ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    // Documents, rather than assumes, that the label cannot be observed by
    // rendering on this dataset: every node `populated` resolves to carries
    // a non-empty rules list, freeze and budget, so none of the four empty
    // states this label is attached to is reachable here. True today and
    // expected to stay true once the label is retired, so this assertion is
    // honest but does not by itself prove anything changed.
    const body = await page.locator('body').innerText();
    expect(
      body,
      'the empty-state CTA was expected to be unreachable on this dataset, but its ' +
        'label rendered — the fixture assumption behind the source check below no ' +
        'longer holds and needs re-reading',
    ).not.toContain('Look at the configuration');

    // The actual proof: the catalogue key this label reads from must no
    // longer be referenced by the screen at all.
    const source = readFileSync(
      fileURLToPath(
        new URL('../../src/surfaces/settings/autonomy.tsx', import.meta.url),
      ),
      'utf8',
    );
    const references = (source.match(/autonomy\.empty\.action/g) ?? []).length;
    expect(
      references,
      `"autonomy.empty.action" (the "Look at the configuration" label) is still ` +
        `referenced ${String(references)} time(s) in autonomy.tsx`,
    ).toBe(0);
  });
});

// --- (e): the guardrails table keeps every value filled ---------------------

test.describe('the guardrails table keeps every value filled', () => {
  test('no empty cell in the Value column, in either appearance of the table', async ({
    page,
  }) => {
    await page.goto(ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    // A configuration table inside a collapsed `<details>` (the advanced,
    // technical `policies.autonomy.` section) has no `innerText` at all while
    // closed, regardless of what its cells hold — opening every section first
    // is what makes this check the data rather than the fold. The same
    // pattern `transversal-rules.spec.ts` already uses for this exact rule.
    await page.evaluate(() => {
      document.querySelectorAll('details').forEach((node) => {
        node.open = true;
      });
    });

    const rows = page.getByTestId('effective-field');
    const rowCount = await rows.count();
    expect(rowCount, 'the guardrails table drew no rows at all').toBeGreaterThan(0);

    for (let index = 0; index < rowCount; index += 1) {
      const row = rows.nth(index);
      const value = (await row.locator('td').nth(1).innerText()).trim();
      const path = await row.getAttribute('data-path');
      expect(value, `row "${path ?? String(index)}" has an empty Value cell`).not.toBe(
        '',
      );
    }
  });
});

// --- (f): override is a rare action, not a permanent third of the page -----

test.describe('override is a rare action, not a permanent third of the page', () => {
  test('the override does not occupy body space, and a header button opens it in a side panel', async ({
    page,
  }) => {
    await page.goto(ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    // Anchored to the component's own testid, not its current heading text:
    // `override-editor.tsx` renders `data-testid="override-editor"` on the
    // outermost element of the whole grant/revoke component, so this
    // survives a rename of "Grant or revoke an override" that a heading-text
    // lookup could not. Checked for visibility rather than absence: if a
    // future drawer keeps this same component mounted while closed
    // (`display:none` rather than unmounted), presence alone would be a
    // false red for a screen that is already compliant.
    const bodyOverrideEditor = page.getByTestId('override-editor');
    await expect(bodyOverrideEditor).not.toBeVisible();

    // A button in the header, labelled as a temporary override, that opens a
    // side panel — `Drawer` (`components/overlay.tsx`) is this console's own
    // non-modal overlay, built exactly for "keep the context behind it
    // visible", and renders `role="dialog"` labelled by its own title.
    const trigger = page
      .getByTestId('page-header')
      .getByRole('button', { name: /temporary override/i });
    await expect(trigger).toBeVisible();

    await trigger.click();
    await expect(
      page.getByRole('dialog', { name: /temporary override/i }),
    ).toBeVisible();
  });
});

// --- (i): the simulation section converges on one CTA -----------------------

test.describe('the simulation section converges on one CTA', () => {
  test('exactly one primary CTA carries the simulation section, and no competing label survives beside it', async ({
    page,
  }) => {
    await page.goto(ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

    // Scoped to the simulation section itself, not the whole editor:
    // `autonomy-editor` also holds the rule-saving button, itself a
    // legitimate `variant="primary"` control, so counting primaries there
    // would over-count regardless of what the simulation section does.
    // `autonomy-simulation` does not exist yet — this is the contract the
    // implementation is expected to satisfy, named here rather than left to
    // be guessed at later.
    const section = page.getByTestId('autonomy-simulation');
    await expect(section).toBeVisible();

    // (1) Exactly one primary CTA. `Button` emits `data-variant={variant}`
    // (`components/action.tsx`), so this is a direct attribute selector
    // rather than a label lookup: the surviving CTA is free to carry a new
    // label once the section gains its own title and its own sentence about
    // what it answers, and this assertion does not depend on what that
    // label turns out to be.
    const primaries = section.locator('button[data-variant="primary"]');
    await expect(primaries).toHaveCount(1);

    // (2) None of today's three competing labels survives as a sibling of
    // the primary — including the primary's own current label, which the
    // surviving control is free to keep. A button matching one of these
    // names that is NOT the primary is exactly the "still competing" shape
    // this claim retires.
    const named = section.getByRole('button', {
      name: /^(Explain one action|Simulate everything|Stop simulating|What would this decide differently\?)$/,
    });
    const namedCount = await named.count();
    let survivors = 0;
    for (let index = 0; index < namedCount; index += 1) {
      const variant = await named.nth(index).getAttribute('data-variant');
      if (variant !== 'primary') survivors += 1;
    }
    expect(
      survivors,
      `${String(survivors)} of today's competing simulation button(s) survive beside ` +
        'the primary CTA',
    ).toBe(0);
  });
});
