import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test, type Page } from '@playwright/test';

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
 * **Screen-wide claims are checked on every tab they apply to, named by tab.**
 * A claim written against `ROUTE` with no `?tab=` only ever exercises
 * whichever tab the address defaults to (Posture) — the exact shape of the
 * defect this project keeps re-finding once a screen grows tabs, because a
 * requirement about "the route" or "either appearance" silently narrows to
 * "whichever tab happened to be open when the test was written". The tab
 * strip's own claims (three tabs, addressable, per-tab budget), the missing
 * paragraph, the override's absence from the body, and the guardrails
 * table's Value column are all checked once per tab that could carry them.
 *
 * **Some of the per-tab checks below are not written to pass today, on
 * purpose — each says why in its own comment:**
 *
 * - The guardrails table's Value column is already fully populated where it
 *   has always lived (the Guardrails tab) — a property an earlier feature
 *   closed structurally. On Posture, the same column is a later slice's
 *   read-only summary and does not exist yet; that half stays red, by name,
 *   until it does.
 * - The missing-paragraph walk is expected to fail on Rules & windows, where
 *   the three conceptual paragraphs still live, until a later slice removes
 *   them.
 * - The override-not-in-the-body claim is expected to fail on Posture, where
 *   the grant/revoke panel still sits in the page body, until a later slice
 *   moves it into a side panel opened from the header.
 * - The retired "Look at the configuration" CTA cannot be exercised through
 *   the browser at all on this dataset: every node `populated` can resolve
 *   to carries at least one rule, one freeze and one budget, so none of this
 *   route's four empty states ever renders. That claim is asserted against
 *   the screen's own source instead, the same way `scroll-budget.spec.ts`
 *   and `transversal-rules.spec.ts` already read `surfaces.py` and
 *   `routes.ts` as ground truth rather than through a rendered control — and
 *   the source scan already covers every tab at once, so it needs no loop.
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
  // This claim is about the route, not about whichever tab a bare `ROUTE`
  // happens to default to: a conceptual paragraph before the
  // first control anywhere on this screen, and the three tabs are three
  // separate DOM trees now, not three views of one. Walking only Posture
  // (`ROUTE` with no `?tab=`) would have kept passing the day the three
  // glossary paragraphs moved to Rules & windows in the tab cut — the
  // content never left the page, it only left the one tab this claim used to
  // look at. Named per tab, so a reader knows which one still owes the fix.
  for (const tab of TAB_IDS) {
    test(`no paragraph sits between the title and the first control, tab=${tab}`, async ({
      page,
    }) => {
      await page.goto(`${ROUTE}?tab=${tab}`);
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
          const nextTestid =
            next === undefined ? null : next.getAttribute('data-testid');
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

      expect(violation, `tab=${tab}: ${violation ?? ''}`).toBeNull();
    });
  }

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

/**
 * Opens every collapsed `<details>` (the advanced, technical
 * `policies.autonomy.` section on Rules & windows has no bearing here, but
 * the pattern is shared with `transversal-rules.spec.ts` for the same
 * reason: closed `<details>` has no `innerText` at all, regardless of what
 * its cells hold), then asserts no `effective-field` row's Value cell — the
 * second `<td>` — is blank. Does not assert row count is non-zero: the two
 * call sites disagree on whether zero rows is the expected state today, so
 * each names its own expectation around this shared walk.
 */
async function assertNoEmptyValueCell(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.querySelectorAll('details').forEach((node) => {
      node.open = true;
    });
  });

  const rows = page.getByTestId('effective-field');
  const rowCount = await rows.count();
  for (let index = 0; index < rowCount; index += 1) {
    const row = rows.nth(index);
    const value = (await row.locator('td').nth(1).innerText()).trim();
    const path = await row.getAttribute('data-path');
    expect(value, `row "${path ?? String(index)}" has an empty Value cell`).not.toBe(
      '',
    );
  }
}

test.describe('the guardrails table keeps every value filled', () => {
  // The table's two appearances now live on two different tabs, not two
  // places on one page: the Guardrails tab's editable table, and Posture's
  // read-only summary of the same fields. A single check against bare
  // `ROUTE` only ever exercised Posture — and would have kept passing there
  // by accident once tabs existed, for the wrong reason: not because the
  // property held, but because that tab draws no such table at all yet.
  test('no empty cell in the Value column, on the Guardrails tab', async ({ page }) => {
    await page.goto(`${ROUTE}?tab=guardrails`);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const rowCount = await page.getByTestId('effective-field').count();
    expect(
      rowCount,
      'tab=guardrails: the guardrails table drew no rows at all',
    ).toBeGreaterThan(0);

    await assertNoEmptyValueCell(page);
  });

  test('no empty cell in the Value column, in Posture’s read-only guardrails summary', async ({
    page,
  }) => {
    await page.goto(`${ROUTE}?tab=posture`);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const rowCount = await page.getByTestId('effective-field').count();
    // Named red, not a mystery: Posture's own read-only guardrails summary
    // (Setting, Value, Set at) is a later slice of this same feature. This
    // goes green the day that slice lands, with no change to this assertion.
    expect(
      rowCount,
      'tab=posture: 0 guardrails-summary rows — Posture’s read-only guardrails ' +
        'summary is not built yet (a later slice); this stays red until it is',
    ).toBeGreaterThan(0);

    await assertNoEmptyValueCell(page);
  });
});

// --- (f): override is a rare action, not a permanent third of the page -----

test.describe('override is a rare action, not a permanent third of the page', () => {
  // The requirement says "no tab" in as many words: not occupying body space is a
  // property of the whole route, not of whichever tab `ROUTE` happened to
  // default to when this was written. Once the panel does move behind the
  // header button (a later slice), it could easily stay mounted, but hidden,
  // on the one tab it used to live in — a single check against bare `ROUTE`
  // would not catch that, because that tab is Posture, the very one this
  // panel is expected to leave last.
  for (const tab of TAB_IDS) {
    test(`the override editor does not occupy body space, tab=${tab}`, async ({
      page,
    }) => {
      await page.goto(`${ROUTE}?tab=${tab}`);
      await expect(page.getByTestId('page-header')).toBeVisible();

      // Anchored to the component's own testid, not its current heading
      // text: `override-editor.tsx` renders `data-testid="override-editor"`
      // on the outermost element of the whole grant/revoke component, so
      // this survives a rename of "Grant or revoke an override" that a
      // heading-text lookup could not. Checked for visibility rather than
      // absence: if a future drawer keeps this same component mounted while
      // closed (`display:none` rather than unmounted), presence alone would
      // be a false red for a screen that is already compliant.
      await expect(
        page.getByTestId('override-editor'),
        `tab=${tab}: the override editor is visible in the page body`,
      ).not.toBeVisible();
    });
  }

  test('a header button opens the override in a side panel', async ({ page }) => {
    await page.goto(ROUTE);
    await expect(page.getByTestId('page-header')).toBeVisible();

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
    // Not a screen-wide claim like (e)/(f)/(g): the simulation section is
    // part of `AutonomyEditor`, which lives on exactly one tab (Rules &
    // windows, per the field-ownership map's placement of `dry_run`
    // alongside the rules, freezes and budgets it simulates), never on
    // Posture or Guardrails. `ROUTE` with no `?tab=` defaults to Posture,
    // where this section can never appear — found while repairing the three
    // screen-wide claims above, same root cause (a tab cut changing which
    // address a pre-tabs assertion actually reaches), fixed for the same
    // reason: pointed at the one tab this claim could ever pass on, rather
    // than the one a bare route happens to default to.
    await page.goto(`${ROUTE}?tab=rules-windows`);
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
