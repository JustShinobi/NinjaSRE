import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * Organização, in a browser, against the built console.
 *
 * What a unit test cannot show: that a period preset clicked from the audit
 * log's own address actually keeps the browser on that address rather than
 * ending up somewhere else — the widen-the-period defect was exactly a
 * navigation leaving the page, and a navigation is the one thing a jsdom
 * render never does.
 */

test.describe('the audit log answers the filter it was given', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('clicking a period preset stays on the audit log address', async ({ page }) => {
    await page.goto('/settings/audit-log');
    await expect(page).toHaveURL(/\/settings\/audit-log$/);

    const preset = page.getByTestId('tab-link').filter({ hasText: /last 7 days/i });
    await expect(preset).toBeVisible();
    await preset.click();

    // The defect this reproduces: the same click used to land on Members &
    // roles, because the hard-coded `/administration` link carried no `tab`
    // and the retired route's own redirect table read that as the default.
    await expect(page).toHaveURL(/\/settings\/audit-log\?since=/);
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-audit-log',
    );
  });

  test('the count beside the list is never contradicted by the list itself', async ({
    page,
  }) => {
    await page.goto('/settings/audit-log');

    const panel = page.getByTestId('panel');
    await expect(panel).toHaveAttribute('data-state', 'ready');

    // "Nothing has been recorded" must not appear while the page is also
    // reporting real events — the two defects this feature closes were never
    // supposed to be visible on the same screen at once.
    await expect(page.getByText('Nothing has been recorded')).toHaveCount(0);
    await expect(page.getByTestId('row-list')).toBeVisible();
  });
});

test.describe('machine tokens, grouped', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('the bootstrap accumulation collapses into one group with a count, and reduces in one gesture', async ({
    page,
  }) => {
    await page.goto('/settings/machine-tokens');
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-machine-tokens',
    );

    const bootstrapGroup = page
      .getByTestId('token-group')
      .filter({ has: page.getByText('bootstrap', { exact: true }) });
    await expect(bootstrapGroup).toBeVisible();
    await expect(bootstrapGroup.getByTestId('token-group-count')).toContainText('15');

    await bootstrapGroup.getByTestId('revoke-older').click();
    await bootstrapGroup.getByTestId('confirm-revoke-older').click();

    await expect(bootstrapGroup.getByTestId('token-group-count')).toContainText('1');
  });

  test('issuing a token offers scopes to choose, none of them pre-selected', async ({
    page,
  }) => {
    await page.goto('/settings/machine-tokens');

    await expect(page.getByLabel('What it is for')).toBeVisible();
    // At least one permission checkbox, offered but unchecked — the ceiling
    // this viewer's own token may hold, chosen from rather than assumed. A
    // box used to start pre-checked here, which is exactly what let a name
    // typed and "Issue" clicked emit every scope the issuer held — including
    // the destructive ones — for a purpose that asked for one.
    const scopes = page.locator('input[type="checkbox"][name^="scope-"]');
    await expect(scopes.first()).toBeVisible();
    await expect(scopes.first()).not.toBeChecked();
  });
});

test.describe('single sign-on, as a flow', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('shows configure, test and activate as three steps, each field carrying its own help', async ({
    page,
  }) => {
    await page.goto('/settings/single-sign-on');
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-single-sign-on',
    );

    await expect(page.getByTestId('sso-step-configure')).toBeVisible();
    await expect(page.getByTestId('sso-step-test')).toBeVisible();
    await expect(page.getByTestId('sso-step-activate')).toBeVisible();

    // A representative field's own help, not just its label — the gap the
    // eight-field form this replaces never closed.
    await expect(page.getByText(/issuer URL your provider documents/i)).toBeVisible();

    // The local fallback, declared on the page rather than assumed.
    await expect(page.getByTestId('sso-fallback')).toBeVisible();
  });

  test('keeps the advanced claim-mapping section collapsed, naming the four claims once opened', async ({
    page,
  }) => {
    // A real production build, not a component render: the class of defect
    // this directory exists to catch breaks only here, never in a unit test.
    await page.goto('/settings/single-sign-on');

    const advanced = page.getByTestId('advanced-config-policies-sso-claims');
    await expect(advanced).toBeVisible();
    await expect(advanced).not.toHaveAttribute('open', '');

    await advanced.locator('summary').click();
    await expect(advanced).toHaveAttribute('open', '');
    await expect(advanced.getByText('Subject claim')).toBeVisible();
  });
});

test.describe('members and roles, without tokens or sign-on crowding it', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('lists principals with canonical chips, grants with legible permissions, and active sessions', async ({
    page,
  }) => {
    await page.goto('/settings/members-roles');
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-members-roles',
    );

    await expect(page.getByTestId('principal').first()).toBeVisible();
    await expect(page.getByTestId('grant-panel')).toBeVisible();

    // What moved out: no machine-token issuance here, and no SSO form.
    await expect(page.getByTestId('issue-token')).toHaveCount(0);
    await expect(page.getByTestId('sso-setup-flow')).toHaveCount(0);
  });
});
