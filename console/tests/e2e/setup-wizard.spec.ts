import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The setup wizard, once there is nothing left for it to do.
 *
 * This project drives against the populated dataset — a deployment whose
 * checklist has been closed for a while — which is exactly the state that
 * proves the two claims this file is about: the wizard's own address stops
 * serving the wizard, and a screen a step once handed over to stops offering
 * a way back that would have nowhere honest to send anybody.
 *
 * The wizard's own mid-flow behaviour (the stepper, the position line, the
 * handover banner actually appearing, continuing past an unverified check)
 * needs an *unfinished* checklist, which this dataset does not carry — that
 * half is proven against the first-day project instead, in
 * `tests/first-day/first-day.spec.ts`, the project built for a deployment on
 * its first day.
 */

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test('the wizard route redirects to the dashboard once the checklist is complete', async ({
  page,
}) => {
  await page.goto('/first-run');

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId('page-header')).toHaveAttribute(
    'data-area',
    'dashboard',
  );
  // Absent, not merely unreachable by address: the invitation this route
  // used to be reached from is also gone, because there is nothing left for
  // either of them to invite anybody to finish.
  await expect(page.getByTestId('setup-hero')).toHaveCount(0);
});

test('a screen a step once handed over to offers no way back once setup is finished', async ({
  page,
}) => {
  // Both destinations the wizard's last two steps hand over to, each asked
  // explicitly for the way back this dataset has nothing left to offer.
  await page.goto('/resources?return=setup');
  await expect(page.getByTestId('setup-return-banner')).toHaveCount(0);

  await page.goto('/settings/alert-intake?return=setup');
  await expect(page.getByTestId('setup-return-banner')).toHaveCount(0);
});
