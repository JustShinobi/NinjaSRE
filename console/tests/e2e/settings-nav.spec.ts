import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The hybrid navigation, in a browser, against the built console.
 *
 * What a unit test cannot show: that the sidebar a signed-in visitor actually
 * sees carries exactly Integrations and Settings, that clicking Settings
 * lands on a real, addressed page rather than a client-side view, and that
 * every retired address really does redirect at the HTTP layer rather than
 * merely computing the right string somewhere in a unit test's assertion.
 *
 * The permission-gated absence of a whole subnav group (the spec's second
 * acceptance scenario for finding a setting in two clicks) is not repeated
 * here: `console/tests/unit/shell/routes.test.ts` and
 * `console/tests/unit/shell/role-matrix.test.tsx` already hold it against
 * every role the platform declares, and the mock backing this suite drives
 * against serves one scenario per run — proving it here would need a second,
 * differently-scoped backing invocation this feature does not build.
 */

async function currentArea(
  page: import('@playwright/test').Page,
): Promise<string | null> {
  return page
    .locator('[data-testid="nav-entry"][aria-current="page"]')
    .getAttribute('data-area');
}

test.describe('the sidebar, after the hybrid navigation', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('carries exactly Integrations and Settings where six areas used to be', async ({
    page,
  }) => {
    await page.goto('/');

    const settingsGroupEntries = page
      .locator('[data-testid="nav-entry"]')
      .filter({ hasText: /^(Integrations|Settings)$/ });
    await expect(settingsGroupEntries).toHaveCount(2);

    // None of the five retired top-level entries is offered any more.
    for (const retired of [
      'Setup',
      'Signals',
      'Autonomy',
      'Configuration',
      'Administration',
    ]) {
      await expect(
        page
          .locator('[data-testid="nav-entry"]')
          .filter({ hasText: new RegExp(`^${retired}$`) }),
      ).toHaveCount(0);
    }
  });
});

test.describe('opening Settings', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('shows the subnav, grouped by intention, with the first reachable page already open', async ({
    page,
  }) => {
    await page.goto('/');
    await page.getByTestId('nav-entry').filter({ hasText: 'Settings' }).click();

    // The address itself moved: the hub never stays on screen, so the URL in
    // the bar always names a real page, not a generic container.
    await expect(page).toHaveURL(/\/settings\/[a-z-]+$/);
    expect(await currentArea(page)).toBe('settings');

    const subnav = page.getByTestId('settings-subnav');
    await expect(subnav).toBeVisible();

    // The three groups, in the mockup's own order.
    const groupHeadings = subnav.locator('p');
    await expect(groupHeadings).toHaveText(['Organization', 'Agent', 'Data']);

    // All nine pages the subnav lists. The signed-in principal
    // (`fixtures/scenarios/populated/principal.json`) holds the role `owner`,
    // and an owner holds every permission the role catalogue grants — so no
    // page is gated away from this viewer. `console/tests/unit/shell/routes.test.ts`
    // proves the permission-gated absence itself, for every permission
    // combination; this is the one real viewer this suite can drive a
    // browser as, and it is deliberately the widest one.
    const entries = subnav.locator('[data-testid="settings-nav-entry"]');
    await expect(entries).toHaveText([
      'Members & roles',
      'Single sign-on',
      'Machine tokens',
      'Audit log',
      'Models & providers',
      'Autonomy & guardrails',
      'Notifications',
      'Alert intake',
      'Schedules & destinations',
    ]);

    // Exactly one of them is marked current, matching the address just opened.
    const marked = subnav.locator('[aria-current="page"]');
    await expect(marked).toHaveCount(1);
  });

  test('reaches every page this viewer may open in one click from the subnav, each keeping the Settings header', async ({
    page,
  }) => {
    await page.goto('/settings/members-roles');

    // Every page the subnav offers, starting from the one already open.
    const destinations: readonly { readonly label: string; readonly path: string }[] = [
      { label: 'Single sign-on', path: '/settings/single-sign-on' },
      { label: 'Machine tokens', path: '/settings/machine-tokens' },
      { label: 'Audit log', path: '/settings/audit-log' },
      { label: 'Models & providers', path: '/settings/models-providers' },
      { label: 'Autonomy & guardrails', path: '/settings/autonomy-guardrails' },
      { label: 'Notifications', path: '/settings/notifications' },
      { label: 'Alert intake', path: '/settings/alert-intake' },
      { label: 'Schedules & destinations', path: '/settings/schedules-destinations' },
      { label: 'Members & roles', path: '/settings/members-roles' },
    ];

    for (const destination of destinations) {
      await page
        .getByTestId('settings-nav-entry')
        .filter({ hasText: new RegExp(`^${destination.label}$`) })
        .click();
      await expect(page).toHaveURL(new RegExp(`${destination.path}$`));
      // The subnav survives every hop: this is a segment navigation, not a
      // document load starting the whole shell over.
      await expect(page.getByTestId('settings-subnav')).toBeVisible();
      await expect(page.getByTestId('sidebar')).toBeVisible();
    }
  });

  test('none of the nine Settings pages is the honest stand-in any more', async ({
    page,
  }) => {
    // Alert intake and Schedules & destinations were the last two — every
    // Settings page the subnav lists now renders its own screen rather than
    // the generic "not built yet" placeholder.
    await page.goto('/settings/alert-intake');

    await expect(page.getByTestId('way-back')).toHaveCount(0);
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-alert-intake',
    );
    await expect(page.locator('h1')).toHaveText('Alert intake');
  });
});

test.describe('an old address, after the hybrid navigation', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('/autonomy redirects to its Settings address', async ({ page }) => {
    await page.goto('/autonomy');
    await expect(page).toHaveURL(/\/settings\/autonomy-guardrails$/);
  });

  test('/administration redirects to Members & roles', async ({ page }) => {
    await page.goto('/administration');
    await expect(page).toHaveURL(/\/settings\/members-roles$/);
  });

  test('/administration?tab=audit redirects to Audit log', async ({ page }) => {
    await page.goto('/administration?tab=audit');
    await expect(page).toHaveURL(/\/settings\/audit-log$/);
  });

  test('/signals redirects to Alert intake', async ({ page }) => {
    await page.goto('/signals');
    await expect(page).toHaveURL(/\/settings\/alert-intake$/);
  });

  test('/signals?tab=destinations redirects to Schedules & destinations', async ({
    page,
  }) => {
    await page.goto('/signals?tab=destinations');
    await expect(page).toHaveURL(/\/settings\/schedules-destinations$/);
  });

  test('/signals?tab=observation is not redirected: continuous observation has no Settings page yet', async ({
    page,
  }) => {
    await page.goto('/signals?tab=observation');
    await expect(page).toHaveURL(/\/signals\?tab=observation$/);
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'signals',
    );
  });

  test('/configuration is retired: its address forwards rather than rendering an editor', async ({
    page,
  }) => {
    await page.goto('/configuration');

    // The forward is made in the browser, not by the server, because the group
    // a bookmark wanted was in the fragment and a fragment is never sent with
    // the request. So this waits for the URL to settle rather than reading the
    // one the first response carried.
    await expect(page).toHaveURL(/\/settings/);
    await expect(page.getByTestId('config-editor')).toHaveCount(0);
  });

  test('a bookmark into one of the old editor’s sections lands on the page that owns it', async ({
    page,
  }) => {
    await page.goto('/configuration#config-section-policies-observation');

    await expect(page).toHaveURL(/\/settings\/alert-intake/);
  });
});
