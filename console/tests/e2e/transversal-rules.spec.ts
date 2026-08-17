import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * Four rules every Settings screen is held to, checked against the built
 * console rather than assumed from a mockup.
 *
 * **Vocabulary.** A raw backend spelling — an account kind still in upper
 * case, a health word never translated to a display name, a dotted
 * configuration path standing in for a title, a delivery route's internal
 * name, a validation message naming a payload key instead of a form label —
 * is a leak from a data shape into a sentence a person reads. None of that
 * belongs in the text a viewer actually sees.
 *
 * **Scroll budget.** A Settings screen earns pagination, search or a filter
 * once it would otherwise ask for more than a declared number of Full HD
 * viewports of scrolling. Measured against the rendered document's own
 * height, at the viewport the budget is declared against — which is not the
 * suite's own global viewport, so this file sets its own.
 *
 * **One count of setup progress.** Wherever this console states how much of
 * the guided setup is left, it states the same total and the same pending
 * count as every other place that states it. Two truthful counts of two
 * different things are still a lie once a reader is invited to compare them
 * on the same screen.
 *
 * **A configuration table's Value column is never blank.** A table that
 * names a setting and its origin but not its value is a browser for a
 * schema, not an answer to "what is this deployment actually doing".
 *
 * **Routes are read from the product's own manifest, not retyped here.**
 * `SETTINGS_PAGES` is the console's single list of what the Settings subnav
 * serves; a page added to it is swept by this suite the day it lands,
 * without anyone remembering to add a line for it.
 *
 * **Exceptions are named, per route and per rule, never global.** A route
 * that still violates a rule because another piece of work has not reached
 * it yet is declared here, with the substantive reason a reader can check
 * against the running screen — never a softened assertion that would also
 * let a route that was never meant to violate the rule slip through.
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

// The suite's own viewport for the rolagem rule: 1920x1080, read from the
// same named constants the product's own scroll-budget instrument reads,
// never repeated as a literal. The global Playwright viewport (1440x900,
// `playwright.config.ts`) is unrelated to this budget and would measure a
// different, narrower layout.
const VIEWPORT_WIDTH = constant('CONFIG_SCREEN_VIEWPORT_WIDTH_PX');
const VIEWPORT_HEIGHT = constant('CONFIG_SCREEN_VIEWPORT_HEIGHT_PX');
const BUDGET_VIEWPORTS = constant('CONFIG_SCREEN_SCROLL_BUDGET_VIEWPORTS');
const BUDGET_PX = VIEWPORT_HEIGHT * BUDGET_VIEWPORTS;

test.use({ viewport: { width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

// --- Where the routes come from --------------------------------------------

/** One Settings route, read from the product's own subnav manifest. */
interface SettingsRoute {
  readonly id: string;
  readonly path: string;
}

// The manifest itself cannot be imported from a Playwright spec file — it is
// a Next.js server module compiled into the console's own bundle, unreachable
// from Node the way `config/constants/surfaces.py` is. What this suite reads
// instead is the same manifest's declared shape, one entry per line, from the
// one file that owns it — a narrower, load-bearing read of `routes.ts` rather
// than a second, hand-maintained list of Settings addresses drifting from the
// one the product already ships.
function settingsRoutesFromSource(): readonly SettingsRoute[] {
  const source = readFileSync(
    fileURLToPath(new URL('../../src/shell/routes.ts', import.meta.url)),
    'utf8',
  );
  const start = source.indexOf('export const SETTINGS_PAGES');
  const end = source.indexOf('\n];', start);
  if (start === -1 || end === -1) {
    throw new Error('SETTINGS_PAGES is not declared in shell/routes.ts');
  }
  const body = source.slice(start, end);
  const routes: SettingsRoute[] = [];
  const entryPattern = /id:\s*'([^']+)'[\s\S]*?path:\s*'([^']+)'/g;
  let match: RegExpExecArray | null;
  while ((match = entryPattern.exec(body)) !== null) {
    const id = match[1];
    const path = match[2];
    if (id === undefined || path === undefined) continue;
    routes.push({ id, path });
  }
  if (routes.length === 0) {
    throw new Error('no Settings route was read from shell/routes.ts');
  }
  return routes;
}

const SETTINGS_ROUTES = settingsRoutesFromSource();

// --- Exceptions: named per route and per rule, with a substantive reason ---

type Rule = 'vocabulary' | 'scroll-budget' | 'value-column';

interface Exception {
  readonly path: string;
  readonly rule: Rule;
  readonly reason: string;
}

/**
 * What is already known to violate a rule, and why — filled in as routes are
 * measured, never as a blanket relaxation. Each entry names one route and one
 * rule; the same route can still be held to every rule it has no entry for.
 */
// `/settings/autonomy-guardrails` + `scroll-budget` is not listed here: it is
// in `SCROLL_BUDGET_MEASURED_ELSEWHERE` below (reached via the retired
// `/autonomy` address, which redirects to it), and the scroll-budget test
// checks that set with `test.skip` before it ever reaches the `test.fixme`
// lookup against this table — an entry for the same pair here would be dead,
// unreachable code rather than a second, harmless statement of the same fact.
const EXCEPTIONS: readonly Exception[] = [
  {
    path: '/settings/alert-intake',
    rule: 'scroll-budget',
    reason: 'the screen repeats seven near-identical sources with nothing collapsed',
  },
  {
    path: '/settings/members-roles',
    rule: 'vocabulary',
    reason:
      "a person's or a token group's own chip still shows the raw health word " +
      "HEALTHY rather than the product's canonical, translated state words",
  },
  {
    path: '/settings/machine-tokens',
    rule: 'vocabulary',
    reason:
      'the same token-group chip named above for /settings/members-roles — ' +
      'both routes render it from the one call site in ' +
      "machine-token-groups.tsx, so this is that route's own occurrence of " +
      'it, not a second defect',
  },
  {
    path: '/settings/autonomy-guardrails',
    rule: 'vocabulary',
    reason:
      'the raw schema editor below the guardrail table still titles its own ' +
      'collapsible sections with dotted configuration paths (e.g. "policies.' +
      'autonomy") rather than a display name',
  },
  {
    path: '/settings/notifications',
    rule: 'vocabulary',
    reason:
      'the raw schema editor below the effective-value table still titles its ' +
      'own section with the dotted configuration path ' +
      '"surfaces.notification_policy" rather than a display name',
  },
  {
    path: '/settings/alert-intake',
    rule: 'vocabulary',
    reason:
      'a trust relationship on this screen is still named by its delivery ' +
      'route\'s internal identifier ("webhook.deliver") rather than a ' +
      'display name',
  },
  {
    path: '/settings/schedules-destinations',
    rule: 'vocabulary',
    reason:
      "a schedule's own chip still shows the raw health word HEALTHY rather " +
      "than the product's canonical, translated state words",
  },
];

function exceptionFor(path: string, rule: Rule): Exception | undefined {
  return EXCEPTIONS.find((entry) => entry.path === path && entry.rule === rule);
}

/**
 * The Settings routes whose scroll height this suite's sibling,
 * `scroll-budget.spec.ts`, already measures against these exact constants —
 * directly, or by way of a retired address that redirects straight to it.
 * Re-measuring them here would be the same assertion twice, and two copies
 * of one rule are exactly what this file exists to prevent from diverging.
 * A route not in this set gets its own, real assertion below.
 */
const SCROLL_BUDGET_MEASURED_ELSEWHERE = new Set<string>([
  '/settings/members-roles',
  '/settings/single-sign-on',
  '/settings/machine-tokens',
  '/settings/audit-log',
  '/settings/alert-intake',
  '/settings/schedules-destinations',
  // Reached by `scroll-budget.spec.ts` via the retired `/autonomy` address,
  // which redirects here (`shell/routes.ts`'s `SETTINGS_REDIRECTS`) — the
  // same document loads either way.
  '/settings/autonomy-guardrails',
]);

// --- Rule 1: vocabulary -----------------------------------------------------

/**
 * A raw backend spelling standing in for the sentence a person should read.
 * Written out here rather than imported, so this file states its own rule
 * end to end and a clone with nothing else present still runs it.
 */
const BANNED_VOCABULARY =
  /SERVICE_ACCOUNT|HEALTHY|policies\.|surfaces\.|models\.investigator|webhook\.deliver|_id is required/;

// --- Rule 4: a configuration table's Value column ---------------------------

/** Every value cell of every configuration table this page rendered. */
async function configurationValueCells(page: Page): Promise<readonly string[]> {
  // A configuration table inside a collapsed `<details>` (the advanced,
  // technical groups every domain page folds its own schema fields into)
  // has no `innerText` at all while closed, regardless of what its cells
  // hold — opening every section first is what makes this rule check the
  // data rather than the fold.
  await page.evaluate(() => {
    document.querySelectorAll('details').forEach((node) => {
      node.open = true;
    });
  });
  const rows = page.getByTestId('effective-field');
  const count = await rows.count();
  const values: string[] = [];
  for (let index = 0; index < count; index += 1) {
    const cells = rows.nth(index).locator('td');
    values.push((await cells.nth(1).innerText()).trim());
  }
  return values;
}

// --- The four rules, per Settings route -------------------------------------

for (const route of SETTINGS_ROUTES) {
  test.describe(route.path, () => {
    test('carries no banned vocabulary in its visible text', async ({ page }) => {
      test.fixme(
        exceptionFor(route.path, 'vocabulary') !== undefined,
        exceptionFor(route.path, 'vocabulary')?.reason ?? '',
      );

      await page.goto(route.path);
      await expect(page.getByTestId('page-header')).toBeVisible();
      const body = await page.locator('body').innerText();
      const found = BANNED_VOCABULARY.exec(body);
      expect(
        found,
        `"${found?.[0] ?? ''}" is banned vocabulary, visible on ${route.path}`,
      ).toBeNull();
    });

    test('stays within the scroll budget', async ({ page }) => {
      test.skip(
        SCROLL_BUDGET_MEASURED_ELSEWHERE.has(route.path),
        'measured by console/tests/e2e/scroll-budget.spec.ts against the same constants',
      );
      test.fixme(
        exceptionFor(route.path, 'scroll-budget') !== undefined,
        exceptionFor(route.path, 'scroll-budget')?.reason ?? '',
      );

      await page.goto(route.path);
      await expect(page.getByTestId('page-header')).toBeVisible();
      const height = await page.evaluate(() => document.documentElement.scrollHeight);
      expect(
        height,
        `${route.path} is ${String(height)}px tall against a ${String(BUDGET_PX)}px ` +
          `budget (${String(BUDGET_VIEWPORTS)} viewports of ${String(VIEWPORT_HEIGHT)}px)`,
      ).toBeLessThanOrEqual(BUDGET_PX);
    });

    test('draws no empty cell in a configuration table’s Value column', async ({
      page,
    }) => {
      test.fixme(
        exceptionFor(route.path, 'value-column') !== undefined,
        exceptionFor(route.path, 'value-column')?.reason ?? '',
      );

      await page.goto(route.path);
      await expect(page.getByTestId('page-header')).toBeVisible();
      const values = await configurationValueCells(page);
      const empty = values.findIndex((value) => value === '');
      expect(
        empty,
        `row ${String(empty)} of the configuration table on ${route.path} has an ` +
          'empty Value cell',
      ).toBe(-1);
    });
  });
}

// --- Rule 3: one count of setup progress ------------------------------------
//
// Not one test per Settings route: no Settings page states setup progress as
// a number (the return banner a handed-over Settings page shows names no
// count, only a link back to the wizard). The three surfaces that do state
// it are the wizard's own header, the wizard's own steps panel, and the
// dashboard's setup card — so this rule is one test comparing those three,
// wherever this run of the console renders them.

// `total` is absent for the wizard header on purpose: "Step N of 7" names
// which of the seven wizard *screens* this is, a different fact from how
// many of the deployment's own checklist steps remain — the number the
// checklist panel and the dashboard card both state as their own total.
// `pending` is the one number every surface below claims about the same
// thing, and it is the one this rule holds every surface to.
interface ProgressClaim {
  readonly surface: string;
  readonly total?: number | undefined;
  readonly pending: number;
}

function pendingOfTotal(text: string): { pending: number; total: number } | null {
  const found = /(\d+)\s+of\s+(\d+)/i.exec(text);
  if (found?.[1] === undefined || found[2] === undefined) return null;
  return { pending: Number(found[1]), total: Number(found[2]) };
}

function stepOfTotal(text: string): { total: number; pending: number } | null {
  const position = /Step\s+\d+\s+of\s+(\d+)/i.exec(text);
  if (position?.[1] === undefined) return null;
  const pending = /(\d+)\s+steps?\s+left/i.exec(text);
  if (pending?.[1] === undefined) return null;
  return { total: Number(position[1]), pending: Number(pending[1]) };
}

async function progressClaims(page: Page): Promise<readonly ProgressClaim[]> {
  const claims: ProgressClaim[] = [];

  await page.goto('/');
  const hero = page.getByTestId('setup-hero');
  if (await hero.count()) {
    const text = await page.getByTestId('setup-hero-progress').innerText();
    const parsed = pendingOfTotal(text);
    if (parsed !== null) {
      claims.push({
        surface: 'dashboard card',
        total: parsed.total,
        pending: parsed.pending,
      });
    }
  }

  await page.goto('/first-run');
  if (new URL(page.url()).pathname.endsWith('/first-run')) {
    const positionText = await page.getByTestId('wizard-position').innerText();
    const step = stepOfTotal(positionText);
    if (step !== null) {
      // No `total` — `step.total` is the wizard's own seven-screen count,
      // not the checklist total; see `ProgressClaim`'s own doc above.
      claims.push({
        surface: 'wizard header',
        pending: step.pending,
      });
    }
    const progressText = await page.getByTestId('first-run-progress').innerText();
    const panel = pendingOfTotal(progressText);
    if (panel !== null) {
      claims.push({
        surface: 'wizard panel',
        total: panel.total,
        pending: panel.pending,
      });
    }
  }

  return claims;
}

test.describe('setup progress: one count, everywhere it is shown', () => {
  test('every surface that states it this run agrees on the total and the pending count', async ({
    page,
  }) => {
    const claims = await progressClaims(page);
    if (claims.length < 2) {
      // Nothing to reconcile on this dataset: setup is finished, the wizard
      // redirects away, and the dashboard's own card is absent by design.
      return;
    }
    const [first, ...rest] = claims;
    for (const claim of rest) {
      expect(
        claim.pending,
        `${claim.surface} claims ${String(claim.pending)} pending against ` +
          `${first?.surface ?? ''}'s ${String(first?.pending ?? -1)}`,
      ).toBe(first?.pending);
    }

    // The checklist total specifically — only the surfaces that state one
    // (the wizard header does not; see `ProgressClaim`'s own doc).
    const totalled = claims.filter(
      (claim): claim is ProgressClaim & { total: number } => claim.total !== undefined,
    );
    const [firstTotal, ...restTotals] = totalled;
    for (const claim of restTotals) {
      expect(
        claim.total,
        `${claim.surface} claims a total of ${String(claim.total)} against ` +
          `${firstTotal?.surface ?? ''}'s ${String(firstTotal?.total ?? -1)}`,
      ).toBe(firstTotal?.total);
    }
  });

  test('the stated pending count is the number of rows actually drawn as not-done', async ({
    page,
  }) => {
    // Every claim above compares a stated number to another stated number —
    // which is why they could all agree while the screen was wrong: a
    // derivation and the visible checklist can cite the same figure without
    // either one describing what the other draws. This is the missing
    // comparison, on both surfaces that draw the deployment's own checklist
    // as rows.
    await page.goto('/first-run');
    if (new URL(page.url()).pathname.endsWith('/first-run')) {
      const rows = await page.getByTestId('checklist-step').all();
      const attributes = await Promise.all(
        rows.map((row) => row.getAttribute('data-done')),
      );
      const notDone = attributes.filter((done) => done === 'false').length;
      const stated = /(\d+)\s+of\s+\d+/.exec(
        await page.getByTestId('first-run-progress').innerText(),
      );
      expect(
        stated?.[1],
        'the checklist panel names no pending count to check',
      ).toBeDefined();
      expect(
        notDone,
        `the checklist panel draws ${String(notDone)} not-done rows (of ${String(rows.length)} total) against a stated ${String(stated?.[1])}`,
      ).toBe(Number(stated?.[1]));
    }

    await page.goto('/');
    const hero = page.getByTestId('setup-hero');
    if (await hero.count()) {
      const rows = await hero.getByTestId('setup-hero-step').all();
      const attributes = await Promise.all(
        rows.map((row) => row.getAttribute('data-done')),
      );
      const notDone = attributes.filter((done) => done === 'false').length;
      const stated = /(\d+)\s+of\s+\d+/.exec(
        await hero.getByTestId('setup-hero-progress').innerText(),
      );
      expect(
        stated?.[1],
        'the dashboard card names no pending count to check',
      ).toBeDefined();
      expect(
        notDone,
        `the dashboard card draws ${String(notDone)} not-done rows (of ${String(rows.length)} total) against a stated ${String(stated?.[1])}`,
      ).toBe(Number(stated?.[1]));
    }
  });
});
