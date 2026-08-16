import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The scroll budget, measured rather than assumed.
 *
 * A configuration screen earns search, a filter or pagination once it would
 * otherwise ask for more than two Full HD viewports of scrolling. This is the
 * instrument that measures it — every screen in the Settings group, at the
 * viewport the budget is declared against, with the height read from the
 * rendered document rather than guessed from a mockup.
 *
 * The global suite viewport is 1440x900, fixed for reasons that have nothing
 * to do with 1080p — see `console/playwright.config.ts`. This spec overrides
 * it for its own tests rather than inheriting that one and calling it 1080p.
 *
 * Every screen measures within budget against the deterministic mock dataset
 * this suite runs on, and that is a fact about the dataset as much as about
 * the screens: it holds a handful of integrations and no audit history, not
 * the representative scale this budget is meant to be checked against —
 * eighty-five integrations, fifteen tokens, two hundred audit events. The
 * catalogue and the raw configuration editor are the two screens most likely
 * to cross the budget once they carry that much, and each is a redesign
 * another feature of this wave owns. `ConfigScreen.expectedOverBudget` is
 * this spec's own mechanism for the day a screen does measure over budget —
 * named, with `test.fail`, so the suite reports it as an expected red rather
 * than hiding it — and it carries nothing today because nothing here
 * measures over budget on this dataset yet.
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

const VIEWPORT_WIDTH = constant('CONFIG_SCREEN_VIEWPORT_WIDTH_PX');
const VIEWPORT_HEIGHT = constant('CONFIG_SCREEN_VIEWPORT_HEIGHT_PX');
const BUDGET_VIEWPORTS = constant('CONFIG_SCREEN_SCROLL_BUDGET_VIEWPORTS');
const BUDGET_PX = VIEWPORT_HEIGHT * BUDGET_VIEWPORTS;

test.use({ viewport: { width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

interface ConfigScreen {
  readonly route: string;
  /**
   * Named and true only for a screen already measured over budget on this
   * dataset, with the reason. Absent (the ordinary case) means the budget is
   * expected to hold.
   */
  readonly expectedOverBudget?: string;
}

const SCREENS: readonly ConfigScreen[] = [
  { route: '/first-run' },
  { route: '/integrations' },
  { route: '/signals' },
  { route: '/autonomy' },
  { route: '/configuration' },
  // The four pages Administration desmembered into, each measured at its own
  // address now rather than as one screen carrying all five subjects.
  { route: '/settings/members-roles' },
  { route: '/settings/single-sign-on' },
  { route: '/settings/machine-tokens' },
  { route: '/settings/audit-log' },
];

for (const screen of SCREENS) {
  test(`${screen.route} stays within the scroll budget`, async ({ page }) => {
    test.fail(screen.expectedOverBudget !== undefined, screen.expectedOverBudget ?? '');

    await page.goto(screen.route);
    await expect(page.getByTestId('page-header')).toBeVisible();

    const height = await page.evaluate(() => document.documentElement.scrollHeight);

    expect(
      height,
      `${screen.route} is ${String(height)}px tall against a ${String(BUDGET_PX)}px ` +
        `budget (${String(BUDGET_VIEWPORTS)} viewports of ${String(VIEWPORT_HEIGHT)}px)`,
    ).toBeLessThanOrEqual(BUDGET_PX);
  });
}
