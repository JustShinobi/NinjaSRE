import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * The shell, in a browser, against the built console and the committed dataset.
 *
 * What a unit test cannot show: that the guard runs before routing in the real
 * artefact, that the chrome is in the HTML a browser parses rather than in
 * something React produces afterwards, and that a deep link opened cold lands on
 * the route it names.
 */

/** Every route the console serves, taken from the same manifest the shell reads. */
const AREAS = [
  { id: 'dashboard', path: '/', title: 'Overview' },
  { id: 'incidents', path: '/incidents', title: 'Incidents' },
  { id: 'runs', path: '/runs', title: 'Investigations' },
  { id: 'approvals', path: '/approvals', title: 'Approvals' },
  { id: 'resources', path: '/resources', title: 'Resources' },
  { id: 'topology', path: '/topology', title: 'Topology' },
  { id: 'detectors', path: '/detectors', title: 'Detectors' },
  { id: 'memory', path: '/memory', title: 'Memory' },
  { id: 'knowledge', path: '/knowledge', title: 'Knowledge' },
  { id: 'autonomy', path: '/autonomy', title: 'Autonomy' },
  { id: 'configuration', path: '/configuration', title: 'Configuration' },
  { id: 'audit', path: '/audit', title: 'Audit' },
] as const;

async function currentArea(page: Page): Promise<string | null> {
  return page
    .locator('[data-testid="nav-entry"][aria-current="page"]')
    .getAttribute('data-area');
}

test.describe('an unauthenticated visitor', () => {
  for (const area of AREAS) {
    test(`sees the sign-in and nothing else at ${area.path}`, async ({ page }) => {
      await page.goto(area.path);

      await expect(page.getByTestId('sign-in')).toBeVisible();
      await expect(page.getByTestId('sidebar')).toHaveCount(0);
      // Nothing about the deployment behind it: no name, no counts, no areas.
      await expect(page.getByTestId('deployment-name')).toHaveCount(0);
    });
  }

  test('is sent to the sign-in from a route that does not exist either', async ({
    page,
  }) => {
    await page.goto('/no-such-area');
    await expect(page.getByTestId('sign-in')).toBeVisible();
  });
});

test.describe('a signed-in operator', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  for (const area of AREAS) {
    test(`opens ${area.path} cold, with its own title`, async ({ page }) => {
      await page.goto(area.path);

      await expect(page.getByTestId('page-header')).toHaveAttribute(
        'data-area',
        area.id,
      );
      await expect(page).toHaveTitle(new RegExp(`^${area.title} · `));
      expect(await currentArea(page)).toBe(area.id);
    });
  }

  test('renders a not-found page inside the shell, with a way back', async ({
    page,
  }) => {
    await page.goto('/no-such-area');

    await expect(page.getByTestId('not-found')).toBeVisible();
    // Inside: the navigation is still there, so the way back is the one they
    // already know rather than the browser's back button.
    await expect(page.getByTestId('sidebar')).toBeVisible();
    await expect(page.getByTestId('way-back')).toHaveAttribute('href', '/');
  });

  test('keeps the sidebar, the utility bar and the guardian line on every route', async ({
    page,
  }) => {
    for (const area of AREAS) {
      await page.goto(area.path);
      await expect(page.getByTestId('sidebar')).toBeVisible();
      await expect(page.getByTestId('topbar')).toBeVisible();
      await expect(page.getByTestId('guardian')).toBeVisible();
    }
  });

  test('opens the palette from the keyboard and navigates with it', async ({
    page,
  }) => {
    await page.goto('/');
    await page.keyboard.press('Control+k');

    await expect(page.getByTestId('palette')).toBeVisible();
    await page.keyboard.type('audit');
    await page.keyboard.press('Enter');

    await expect(page).toHaveURL(/\/audit$/);
  });

  test('dismisses the palette without changing the page', async ({ page }) => {
    await page.goto('/knowledge');
    await page.keyboard.press('Control+k');
    await page.keyboard.press('Escape');

    await expect(page.getByTestId('palette')).toHaveCount(0);
    await expect(page).toHaveURL(/\/knowledge$/);
  });

  test('collapses the sidebar to a reachable drawer below the breakpoint', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto('/');

    await expect(page.getByTestId('sidebar')).toBeHidden();
    await page.getByTestId('open-drawer').click();

    // Nothing is lost: every area the rail carries is in the drawer, and so is
    // the guardian line the rail keeps in its footer.
    const inDrawer = page.locator('[data-testid="nav-entry"]:visible');
    expect(await inDrawer.count()).toBeGreaterThanOrEqual(AREAS.length);
    await expect(page.locator('[data-testid="guardian"]:visible')).toHaveCount(1);
  });

  test('does not run off the side of a 320-pixel viewport', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto('/');

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test('signs out for real, clearing the session rather than navigating away', async ({
    page,
    context,
  }) => {
    await page.goto('/');
    await page.getByTestId('account').click();
    await page.getByTestId('sign-out').click();

    await expect(page.getByTestId('sign-in')).toBeVisible();
    const session = (await context.cookies()).find(
      (cookie) => cookie.name === 'ninjasre_session' && cookie.value !== '',
    );
    // The cookie is what the guard reads. Leaving it set would mean the next
    // person at that keyboard types the address and is inside.
    expect(session).toBeUndefined();

    await page.goto('/audit');
    await expect(page.getByTestId('sign-in')).toBeVisible();
  });

  test('shows what is waiting, and how much of it', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('open-notifications').click();

    await expect(page.getByTestId('notifications')).toBeVisible();
    await expect(page.getByTestId('notification').first()).toBeVisible();
  });
});

test.describe('the first paint', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('carries the whole frame before any script has run', async ({
    browser,
    baseURL,
  }) => {
    // JavaScript off: what is left is the HTML the server sent. The chrome has
    // to be in it, or "the shell renders before the page data" is a claim about
    // hydration rather than about what somebody sees.
    const context = await browser.newContext({ javaScriptEnabled: false });
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
    const page = await context.newPage();

    await page.goto('/');

    await expect(page.getByTestId('sidebar')).toBeVisible();
    await expect(page.getByTestId('topbar')).toBeVisible();
    await expect(page.getByTestId('guardian')).toBeVisible();
    await expect(page.locator('[data-testid="nav-entry"]').first()).toBeVisible();
    await context.close();
  });
});
