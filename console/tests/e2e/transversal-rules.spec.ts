import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';
import {
  identifierAsName,
  liveControlOnTerminalRun,
  negativeAssertionAfterFailedRead,
  rawMarkdown,
  twoPlaceholders,
} from './bans';

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

/** One string constant, read out of `config/constants/console.py`. */
function stringConstant(name: string): string {
  const source = readFileSync(
    fileURLToPath(new URL('../../../config/constants/console.py', import.meta.url)),
    'utf8',
  );
  const found = new RegExp(`^${name}: Final = "([^"]*)"`, 'm').exec(source);
  if (found?.[1] === undefined) {
    throw new Error(`${name} is not declared in config/constants/console.py`);
  }
  return found[1];
}

// The one spelling of the tag that marks a test safe to run against a shared,
// live environment — read from the constants layer, never repeated as a
// literal, so the suite that declares it and the harness that selects by it
// cannot drift into two spellings that between them select nothing.
const STAGING_SAFE_TAG = stringConstant('CONSOLE_STAGING_SAFE_TAG');

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

/**
 * `/integrations` is not a Settings route — `shell/routes.ts` lists it among
 * `AREAS`, not `SETTINGS_PAGES`, because it has its own top-level nav entry
 * rather than living under the Settings subnav. Structurally it is held to
 * exactly the same three per-route rules below: it renders `page-header` the
 * same way a Settings page does, and it carries its own configuration table
 * (the "Advanced: configured vendors" section) with a Value column the same
 * rule applies to. The integrations-and-intake feature asks this suite to
 * pass on both of its two screens, one of which is this one, so it is added
 * here explicitly rather than by widening what `SETTINGS_ROUTES` itself
 * means — that constant stays a truthful read of `SETTINGS_PAGES` alone.
 */
const NON_SETTINGS_ROUTES_HELD_TO_THE_SAME_RULES: readonly SettingsRoute[] = [
  { id: 'integrations', path: '/integrations' },
];

const ROUTES_UNDER_THESE_RULES: readonly SettingsRoute[] = [
  ...SETTINGS_ROUTES,
  ...NON_SETTINGS_ROUTES_HELD_TO_THE_SAME_RULES,
];

// --- Exceptions: named per route and per rule, with a substantive reason ---

type Rule =
  | 'vocabulary'
  | 'scroll-budget'
  | 'value-column'
  | 'markdown'
  | 'identifier-as-name'
  | 'two-placeholders'
  | 'live-control'
  | 'negative-assertion';

interface Exception {
  readonly path: string;
  readonly rule: Rule;
  readonly reason: string;
}

/**
 * What is already known to violate a rule, and why — filled in as routes are
 * measured, never as a blanket relaxation. Each entry names one route and one
 * rule; the same route can still be held to every rule it has no entry for.
 *
 * `/settings/alert-intake` + `scroll-budget` used to carry an entry here
 * ("the screen repeats seven near-identical sources with nothing
 * collapsed"), but that route is in `SCROLL_BUDGET_MEASURED_ELSEWHERE` below
 * and the scroll-budget test checks that set with `test.skip` before it ever
 * reaches the `test.fixme` lookup against this table — the entry was already
 * dead, unreachable code, not a second, harmless statement of the same fact,
 * and the seven-sources reason it gave stopped being true once an earlier
 * feature cut intake to three. Deleting a dead table entry is not evidence
 * that the route now passes the rule — nothing here measured that.
 *
 * The seven entries below are the five "Now" rules' own debt, each confirmed
 * red against the dataset built to reproduce it before this line existed.
 * Six were named ahead of time, from a diagnosis of the running deployment;
 * one (`/` + `markdown`) was not — the dashboard's own recent-activity
 * feed reads every run's raw summary with the identical, unfiltered
 * mechanism the runs list and the run detail screen already carried an
 * entry for, and the violating dataset that gives the other six their red
 * gives this one too, because it is the same defect, read a third time.
 *
 * `/incidents/{id}` carries none of `identifier-as-name`, `negative-assertion`
 * or `two-placeholders` any more: an opaque, short incident id decoded once
 * at the edge replaced the composite, percent-encoded route parameter the
 * title used to fall back to; a read that fails no longer renders a chip
 * that could assert anything about an investigation, so there is nothing
 * left for that rule to catch either; and the subtitle — the whole reason
 * `two-placeholders` survived the first two fixes — no longer renders at
 * all once the read has failed, rather than repeating the same fallback
 * word across the facts that read never answered.
 */
const EXCEPTIONS: readonly Exception[] = [
  {
    path: '/runs/{id}',
    rule: 'markdown',
    reason:
      "the run detail screen prints the investigation's raw report verbatim " +
      'as its title, its tab title, and its summary panel body — removed by ' +
      'the separation between the headline sentence and the report document',
  },
  {
    path: '/runs',
    rule: 'markdown',
    reason:
      'the runs list truncates the same raw report into the subject column — ' +
      'the same headline/report separation, read by the list',
  },
  {
    path: '/',
    rule: 'markdown',
    reason:
      "the dashboard's recent-activity feed reads every run's raw summary " +
      'the same unfiltered way the runs list and the run detail screen do — ' +
      'the same headline/report separation, read a third time',
  },
  {
    path: '/runs',
    rule: 'identifier-as-name',
    reason:
      'the investigation column shows the first eight characters of the run ' +
      'id with nothing else standing for the row — removed once the run ' +
      'carries a headline the column can show instead',
  },
  {
    path: '/runs/{id}',
    rule: 'identifier-as-name',
    reason:
      "the breadcrumb's current crumb is the run id in full, because no " +
      'shorter name for a run exists yet — the same headline that removes ' +
      'the id from the runs list',
  },
  {
    path: '/runs',
    rule: 'two-placeholders',
    reason:
      'a run with no summary yet and no recorded finish shows the same ' +
      'fallback word in both its subject and its duration cell — a distinct ' +
      'word for "in progress" instead of the generic fallback for "unknown"',
  },
  {
    path: '/runs/{id}',
    rule: 'live-control',
    reason:
      'confirmed against a run whose own status is already terminal ' +
      '("succeeded") in the fixture: the control panel still offers to stop ' +
      "it. The badge is not reading the run's status at all — it is a label " +
      'for the live-connection state, and shows regardless of whether the ' +
      'run underneath it has settled. Composing the recorder in production ' +
      '(so a run really does close with a terminal status and a logged end ' +
      'event) does not touch this: that fact was already true of a ' +
      'completed run before and remains true after, and this screen simply ' +
      'is not conditioning the control on it — removed by the console ' +
      "gating the control on the run's own status alongside the connection " +
      'state, not on the connection state alone',
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
  // Measured by `scroll-budget.spec.ts` directly, at this address, and once
  // per tab — against the tighter per-tab budget rather than the whole-page
  // one this file would apply. So the delegation hands this route to a
  // stricter instrument than the rule here, not a weaker one, and measuring
  // it again here would be the looser of the two assertions.
  //
  // What that measurement can and cannot see: the app shell carries
  // `min-h-screen` (`shell/shell.tsx`), so `documentElement.scrollHeight`
  // never reports less than one viewport. A tab at exactly the viewport
  // height is proved to need no scrolling at all, which is what a scroll
  // budget asks; its content height below that line is simply not a thing
  // this instrument measures, and does not need to be.
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

// --- The four rules, per Settings route (plus /integrations, held to the
// same three per-route rules — see the constant's own comment above) -------

for (const route of ROUTES_UNDER_THESE_RULES) {
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

// --- The "Now" rules: five ways a "Now" screen has been found to mislead ---
//
// Unlike the four rules above, these five are not about Settings — they hold
// the group a person is standing in front of when something has broken:
// the dashboard, incidents, runs, and decisions, plus the two dynamic detail
// screens a run or an incident opens onto. The mechanics are the same
// (routes read from the product's own manifest, exceptions named per route
// and per rule, never a softened assertion), and the detectors themselves
// live in `./bans` — pure functions this file calls, proved separately by
// `console/tests/unit/e2e/bans.test.ts` against the exact text a diagnosis
// once recorded, so they stay proved on every run of the standard gate and
// not only on the day this file is pointed at a dataset built to violate
// them.

/** One "Now" route, read from the product's own top-level manifest. */
interface NowRoute {
  readonly id: string;
  readonly path: string;
}

/**
 * The routes `shell/routes.ts` places in the "now" navigation group.
 *
 * Read the same way `settingsRoutesFromSource` reads `SETTINGS_PAGES`: a
 * narrow parse of the one file that owns `AREAS`, because a Playwright spec
 * cannot import a Next.js server module. A route added to the "now" group
 * lands in this list the day it ships, without anyone remembering to add a
 * line here for it.
 */
function nowRoutesFromSource(): readonly NowRoute[] {
  const source = readFileSync(
    fileURLToPath(new URL('../../src/shell/routes.ts', import.meta.url)),
    'utf8',
  );
  const start = source.indexOf('export const AREAS');
  const end = source.indexOf('\n];', start);
  if (start === -1 || end === -1) {
    throw new Error('AREAS is not declared in shell/routes.ts');
  }
  const body = source.slice(start, end);
  const routes: NowRoute[] = [];
  const entryPattern = /id:\s*'([^']+)',\s*path:\s*'([^']+)',\s*group:\s*'([^']+)'/g;
  let match: RegExpExecArray | null;
  while ((match = entryPattern.exec(body)) !== null) {
    const id = match[1];
    const path = match[2];
    const group = match[3];
    if (id === undefined || path === undefined || group === undefined) continue;
    if (group === 'now') routes.push({ id, path });
  }
  if (routes.length === 0) {
    throw new Error('no "now" area was read from shell/routes.ts');
  }
  return routes;
}

const NOW_ROUTES = nowRoutesFromSource();

/**
 * The two dynamic detail screens, reached by the list's own first row.
 *
 * `path` is the label these routes are named by everywhere this suite
 * reports on them — allowlist entries, failure messages — because there is
 * no single address to name (every run and every incident has its own).
 * `list` is where the sweep starts; it never types an id, per the rule this
 * whole file is written to keep: a run or an incident id literal in a test
 * file is a dataset dependency in disguise.
 */
const NOW_DETAIL_ROUTES: readonly { readonly path: string; readonly list: string }[] = [
  { path: '/runs/{id}', list: '/runs' },
  { path: '/incidents/{id}', list: '/incidents' },
];

/** Every label these five rules sweep: the static "now" routes, then the two detail ones. */
const NOW_LABELS: readonly string[] = [
  ...NOW_ROUTES.map((route) => route.path),
  ...NOW_DETAIL_ROUTES.map((route) => route.path),
];

/** Go to `label` — a static route as itself, a detail route via its list's first row. */
async function openNowLabel(page: Page, label: string): Promise<void> {
  const detail = NOW_DETAIL_ROUTES.find((route) => route.path === label);
  if (detail !== undefined) {
    await page.goto(detail.list);
    await page.getByTestId('row').first().locator('a').first().click();
    // Wait for the list to be gone before anything reads the page.
    //
    // The click starts a client-side navigation, and every reader below counts
    // rather than asserts — `locator.count()` has no auto-wait. Against a mock
    // that answers instantly the detail screen is already there; against a real
    // deployment it is not, and a rule that ran here would measure the *list*
    // and find nothing to complain about. Passing because the page had not
    // arrived yet is the one failure mode worse than failing.
    await page.waitForURL((url) => !url.pathname.endsWith(detail.list));
    await page.getByTestId('page-header').first().waitFor({ state: 'visible' });
    return;
  }
  await page.goto(label);
}

/**
 * Every non-empty line of `page`'s own header block: title, subtitle, and —
 * on a detail screen — the breadcrumb's current crumb, because all three sit
 * inside the one `page-header` region every screen in this console draws.
 * `[]` when the screen draws no header block at all.
 */
async function pageHeaderLines(page: Page): Promise<readonly string[]> {
  const header = page.getByTestId('page-header');
  if ((await header.count()) === 0) return [];
  const text = await header.innerText();
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line !== '');
}

/** Every cell of every drawn row, one array of texts per row — never the whole row as one string. */
async function rowCells(page: Page): Promise<readonly (readonly string[])[]> {
  const rows = page.getByTestId('row');
  const count = await rows.count();
  const drawn: string[][] = [];
  for (let index = 0; index < count; index += 1) {
    drawn.push(await rows.nth(index).locator('td').allInnerTexts());
  }
  return drawn;
}

/**
 * Where the staging backing wants a full-page capture per route swept — set
 * only by that backing, read here rather than passed down through every
 * test, because the alternative is a parameter every one of these tests
 * would carry for a concern that belongs to how they are run, not to what
 * they check.
 */
const EVIDENCE_DIR = process.env.NINJASRE_STAGING_EVIDENCE_DIR;

test.afterEach(async ({ page }, testInfo) => {
  if (EVIDENCE_DIR === undefined || EVIDENCE_DIR === '') return;
  // A route this test declared fixme never navigated anywhere — capturing it
  // would be a blank page standing in for a route nothing here actually
  // swept.
  const skipped = testInfo.annotations.some(
    (annotation) => annotation.type === 'fixme' || annotation.type === 'skip',
  );
  if (skipped) return;
  const safeName = testInfo.titlePath
    .join('-')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  await page
    .screenshot({ path: `${EVIDENCE_DIR}/${safeName}.png`, fullPage: true })
    .catch(() => {
      // A capture that fails (a route this run never reached, a page already
      // closed) is not this hook's failure to report — the test itself
      // already reported its own result.
    });
});

// --- Rule: markdown cru -------------------------------------------------

test.describe('markdown cru: no "Now" screen prints a raw report as text', () => {
  for (const label of NOW_LABELS) {
    test(label, { tag: STAGING_SAFE_TAG }, async ({ page }) => {
      test.fixme(
        exceptionFor(label, 'markdown') !== undefined,
        exceptionFor(label, 'markdown')?.reason ?? '',
      );

      await openNowLabel(page, label);
      const body = await page.locator('body').innerText();
      const found = rawMarkdown(body);
      expect(found, `${label} shows raw markdown: "${found ?? ''}"`).toBeNull();
    });
  }
});

// --- Rule: identifier as name --------------------------------------------

test.describe('identificador como nome: nothing here is a name only because it is an id', () => {
  for (const label of NOW_LABELS) {
    test(label, { tag: STAGING_SAFE_TAG }, async ({ page }) => {
      test.fixme(
        exceptionFor(label, 'identifier-as-name') !== undefined,
        exceptionFor(label, 'identifier-as-name')?.reason ?? '',
      );

      await openNowLabel(page, label);

      let found: string | null = null;
      for (const line of await pageHeaderLines(page)) {
        found = identifierAsName(line);
        if (found !== null) break;
      }
      if (found === null) {
        for (const cells of await rowCells(page)) {
          for (const cell of cells) {
            // The first line only: index 0's cell also carries the row
            // link's screen-reader-only "Open" label, appended on its own
            // line, which is not part of the value this rule is about.
            const value = cell.split('\n')[0]?.trim() ?? '';
            found = identifierAsName(value);
            if (found !== null) break;
          }
          if (found !== null) break;
        }
      }
      expect(
        found,
        `${label} shows an identifier standing in for a name: "${found ?? ''}"`,
      ).toBeNull();
    });
  }
});

// --- Rule: two placeholders in one metadata line -------------------------

test.describe('dois placeholders: no metadata line carries more than one fallback', () => {
  for (const label of NOW_LABELS) {
    test(label, { tag: STAGING_SAFE_TAG }, async ({ page }) => {
      test.fixme(
        exceptionFor(label, 'two-placeholders') !== undefined,
        exceptionFor(label, 'two-placeholders')?.reason ?? '',
      );

      await openNowLabel(page, label);

      let found: string | null = null;
      for (const line of await pageHeaderLines(page)) {
        found = twoPlaceholders(line);
        if (found !== null) break;
      }
      if (found === null) {
        for (const cells of await rowCells(page)) {
          found = twoPlaceholders(cells.join(' '));
          if (found !== null) break;
        }
      }
      expect(found, `${label}: ${found ?? ''}`).toBeNull();
    });
  }
});

// --- Rule: a live control never survives onto a terminal run -------------

test.describe('controle de run vivo: a settled run offers no live-only control', () => {
  const label = '/runs/{id}';

  test(label, { tag: STAGING_SAFE_TAG }, async ({ page }) => {
    test.fixme(
      exceptionFor(label, 'live-control') !== undefined,
      exceptionFor(label, 'live-control')?.reason ?? '',
    );

    await page.goto('/runs');
    const firstRow = page.getByTestId('row').first();
    // The status column: the second cell of every row this screen draws.
    const listStatus = (await firstRow.locator('td').nth(1).innerText()).trim();
    await firstRow.locator('a').first().click();

    const stopRun = page.getByTestId('stop-run');
    const controlText =
      (await stopRun.count()) > 0 ? (await stopRun.innerText()).trim() : '';
    const found = liveControlOnTerminalRun(listStatus, controlText);
    expect(found, `${label}: ${found ?? ''}`).toBeNull();
  });
});

// --- Rule: no negative assertion after a failed read ----------------------

test.describe('afirmação negativa: nothing here answers from a read that failed', () => {
  const label = '/incidents/{id}';

  test(label, { tag: STAGING_SAFE_TAG }, async ({ page }) => {
    test.fixme(
      exceptionFor(label, 'negative-assertion') !== undefined,
      exceptionFor(label, 'negative-assertion')?.reason ?? '',
    );

    await page.goto('/incidents');
    await page.getByTestId('row').first().locator('a').first().click();

    const failedPanel = page.locator('[data-testid="panel"][data-state="error"]');
    const dependencyFailed = (await failedPanel.count()) > 0;
    // The investigation chip: the second of the two chips this header
    // draws next to the incident's own title.
    const chips = page.getByTestId('incident-chip');
    const chipCount = await chips.count();
    const assertion = chipCount > 1 ? (await chips.nth(1).innerText()).trim() : '';
    const found = negativeAssertionAfterFailedRead(dependencyFailed, assertion);
    expect(found, `${label}: ${found ?? ''}`).toBeNull();
  });
});
