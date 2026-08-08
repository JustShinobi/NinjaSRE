import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The two budgets, asserted where they can actually be measured.
 *
 * A route transition that takes a second is not a bug anybody files; it is a
 * console people stop using the palette in. So it is a number, in
 * `config/constants/console.py`, checked on every run of the browser suite —
 * which is what "asserted in CI" means for a thing only a browser can time.
 *
 * Both are measured warm and cold: the first navigation is a cold render on the
 * server, and the second is a transition the router serves without re-fetching
 * the frame. They are different numbers because they are different operations,
 * and holding only one of them would let the other rot.
 */

/** The budgets, read from the file that declares them rather than restated here. */
function budget(name: string): number {
  const source = readFileSync(
    fileURLToPath(new URL('../../../config/constants/console.py', import.meta.url)),
    'utf8',
  );
  const found = new RegExp(`^${name}: Final = ([0-9.]+)`, 'm').exec(source);
  if (found?.[1] === undefined) {
    throw new Error(`${name} is not declared in config/constants/console.py`);
  }
  return Number(found[1]);
}

const FIRST_PAINT = budget('CONSOLE_FIRST_PAINT_BUDGET_MS');
const TRANSITION = budget('CONSOLE_ROUTE_TRANSITION_BUDGET_MS');

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test('a cold route paints its frame inside the first-paint budget', async ({
  page,
}) => {
  await page.goto('/audit');

  const painted = await page.evaluate(() => {
    const [entry] = performance
      .getEntriesByType('paint')
      .filter((each) => each.name === 'first-contentful-paint');
    return entry?.startTime ?? Number.NaN;
  });

  expect(Number.isNaN(painted), 'the browser reported no first paint').toBe(false);
  expect(painted, `first paint took ${String(painted)}ms`).toBeLessThan(FIRST_PAINT);
});

test('a warm route transition lands inside the transition budget', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('page-header')).toBeVisible();

  const started = Date.now();
  await page.locator('[data-testid="nav-entry"][data-area="knowledge"]').click();
  await expect(page.getByTestId('page-header')).toHaveAttribute(
    'data-area',
    'knowledge',
  );
  const elapsed = Date.now() - started;

  expect(elapsed, `the transition took ${String(elapsed)}ms`).toBeLessThan(TRANSITION);
});

test('every route paints its frame inside the budget, not only the first', async ({
  page,
}) => {
  // A budget held on one route and nowhere else is a budget held by accident.
  for (const path of ['/', '/approvals', '/audit']) {
    await page.goto(path);
    const painted = await page.evaluate(() => {
      const [entry] = performance
        .getEntriesByType('paint')
        .filter((each) => each.name === 'first-contentful-paint');
      return entry?.startTime ?? Number.NaN;
    });
    expect(painted, `${path} painted in ${String(painted)}ms`).toBeLessThan(
      FIRST_PAINT,
    );
  }
});
