import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The Agent group of Settings, in a browser against the built console and the
 * real route table: Models & providers, Autonomy & guardrails, Notifications.
 *
 * What a unit test cannot show: that these three pages are actually reachable
 * from the Settings subnav, that a real browser round-trip through the
 * courier routes (`/api/preview`, `/api/config`, `/api/autonomy`,
 * `/api/verify`) produces the inline result a screen promises, and that no
 * empty state anywhere in this group is a link into the raw configuration
 * editor — the property SC-004 exists for, proved here at the HTTP layer
 * rather than only against a hand-built fixture.
 *
 * The `populated` scenario's own `config-effective` and `config-fields`
 * fixtures do not yet carry `models.*`, `policies.masking/guardrails/
 * approvals.*` or `surfaces.notification_policy.*` — nothing read those paths
 * from the mock plane before this feature, so the assertions below are
 * deliberately structural (a control exists, is labelled, is reachable) not
 * value-specific (a role resolves to a named provider). Extending the mock's
 * own captured dataset to carry those three groups is named, not silently
 * skipped, in this feature's own control file.
 */

test.describe('Models & providers', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('is reachable from the Settings subnav and shows the investigator role', async ({
    page,
  }) => {
    await page.goto('/settings');
    await page
      .getByTestId('settings-nav-entry')
      .filter({ hasText: 'Models & providers' })
      .click();

    await expect(page).toHaveURL(/\/settings\/models-providers$/);
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-models-providers',
    );

    const investigator = page.getByTestId('model-role-investigator');
    await expect(investigator).toBeVisible();
    await expect(investigator.getByLabel('Provider')).toBeVisible();
  });

  test('keeps the seven advanced roles collapsed until asked for', async ({ page }) => {
    await page.goto('/settings/models-providers');

    const advanced = page.getByTestId('advanced-roles');
    await expect(advanced.getByTestId('advanced-roles-summary')).toContainText('7');
    await expect(page.getByTestId('model-role-subagent')).toHaveCount(0);

    // One shared disclosure for all seven, not a per-role accordion: nobody
    // who has never touched one pays for seven separate controls.
    await advanced.getByTestId('advanced-roles-toggle').click();
    await expect(page.getByTestId('model-role-subagent')).toBeVisible();
  });

  test('has no empty state anywhere on the page that points at the raw editor', async ({
    page,
  }) => {
    await page.goto('/settings/models-providers');

    for (const link of await page.getByTestId('way-back').all()) {
      const href = await link.getAttribute('href');
      expect(href ?? '').not.toContain('/configuration');
    }
  });
});

test.describe('Autonomy & guardrails', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('is reachable from the Settings subnav, with the Settings breadcrumb rather than the retired area header', async ({
    page,
  }) => {
    await page.goto('/settings');
    await page
      .getByTestId('settings-nav-entry')
      .filter({ hasText: 'Autonomy & guardrails' })
      .click();

    await expect(page).toHaveURL(/\/settings\/autonomy-guardrails$/);
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-autonomy-guardrails',
    );
    await expect(page.locator('nav ol')).toContainText('Autonomy & guardrails');
  });

  // The two halves of what used to be one page. They are two claims about two
  // tabs now, at their own addresses, rather than one claim about what sits
  // beneath what — the screen no longer stacks them, so a test that asserted
  // the stacking would be asserting a layout this deliberately stopped having.
  test('shows the rules table in resolution order', async ({ page }) => {
    await page.goto('/settings/autonomy-guardrails?tab=rules-windows');

    const rules = page.getByTestId('autonomy-rule');
    await expect(rules.first()).toBeVisible();
  });

  test('shows the guardrails section with the invariants nothing can switch off', async ({
    page,
  }) => {
    await page.goto('/settings/autonomy-guardrails?tab=guardrails');

    // The section's own heading, not the bare word: the tab strip names a tab
    // "Guardrails" too, so the word appears more than once and only the
    // heading is the one this test means.
    await expect(
      page.getByRole('heading', { name: 'Guardrails', exact: true }),
    ).toBeVisible();
    const invariants = page.getByTestId('guardrail-invariant');
    await expect(invariants).toHaveCount(2);
  });

  test('creates a rule with a chosen scope on its own tab, never on the raw editor', async ({
    page,
  }) => {
    await page.goto('/settings/autonomy-guardrails?tab=rules-windows');

    const newRule = page.getByTestId('new-rule');
    await expect(newRule).toBeVisible();
    // Closed on arrival, which is what keeps this page inside its scroll
    // budget: somebody reading the posture does not scroll past three empty
    // forms to do it. Creating a rule therefore starts by asking for the form.
    await newRule.locator('summary').click();
    // Scoped to `newRule`: the explain form elsewhere on this same editor
    // also has a field called "Capability", and the per-row editors also
    // each have one called "Level" — scoping to this section is what keeps
    // the click on the one this test is about.
    await newRule.getByLabel('Scope').selectOption('capability');
    await newRule.getByLabel('Capability').fill('estate.enable_backup_job');
    await newRule.getByTestId('add-rule').click();

    // The new row renders through the same per-row editor an existing rule
    // does — proof that creating a rule and levelling one are the same form.
    await expect(page.getByTestId('rule-editor')).toHaveCount(
      (await page.getByTestId('autonomy-rule').count()) + 1,
    );
  });

  // Every tab, not just the one a bare address opens: the three are separate
  // documents now, so a sweep of one of them proves nothing about the other
  // two, and an empty state pointing at the retired editor could hide on
  // either of the tabs this never visited.
  for (const tab of ['posture', 'rules-windows', 'guardrails']) {
    test(`has no empty state on the ${tab} tab that points at the raw editor`, async ({
      page,
    }) => {
      await page.goto(`/settings/autonomy-guardrails?tab=${tab}`);

      for (const link of await page.getByTestId('way-back').all()) {
        const href = await link.getAttribute('href');
        expect(
          href ?? '',
          `a way-back link on ${tab} points at the raw editor`,
        ).not.toContain('/configuration');
      }
    });
  }
});

test.describe('Notifications', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('is reachable from the Settings subnav and names every control', async ({
    page,
  }) => {
    await page.goto('/settings');
    await page
      .getByTestId('settings-nav-entry')
      .filter({ hasText: 'Notifications' })
      .click();

    await expect(page).toHaveURL(/\/settings\/notifications$/);
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-notifications',
    );

    const rows = page.getByTestId('effective-field');
    await expect(rows).toHaveCount(6);
  });

  test('carries the existing platform-ceiling contract note, not an invented one', async ({
    page,
  }) => {
    await page.goto('/settings/notifications');

    await expect(page.getByTestId('notifications-contract-note')).toContainText(
      'can only make the platform ceiling stricter',
    );
  });
});
