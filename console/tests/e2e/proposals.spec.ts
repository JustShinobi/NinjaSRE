import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * Approving without having looked, attempted in a browser.
 *
 * The component test proves the control is absent until the effect has
 * rendered. What it cannot prove is that a person arriving at the Changes tab
 * of Decisions has no other way through: no second approve button further
 * down the page, no form that submits on Enter, nothing that a keyboard
 * reaches and a render assertion does not. So this drives the bypass — land
 * on the queue, look for something to approve with, and require that there is
 * nothing — and then walks the intended path to be sure the absence is a
 * guarantee rather than a bug.
 */

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test('the queue offers nothing to approve with before the effect has rendered', async ({
  page,
}) => {
  await page.goto('/decisions?tab=changes');

  const items = page.getByTestId('proposal-item');
  await expect(items.first()).toBeVisible();

  // The bypass, attempted: every proposal on the page, and not one approval
  // control between them.
  await expect(page.getByTestId('approve')).toHaveCount(0);
  await expect(page.getByTestId('approve-first').first()).toBeVisible();

  // Rejecting is available without a preview — refusing narrows rather than
  // widens — and is refused without a reason.
  await expect(page.getByTestId('reject').first()).toBeDisabled();
});

test('the approval appears once the deployment has said what would change', async ({
  page,
}) => {
  await page.goto('/decisions?tab=changes');

  await page.getByTestId('show-effect').first().click();

  await expect(page.getByTestId('effect').first()).toBeVisible();
  await expect(page.getByTestId('approve').first()).toBeVisible();
});

test('each proposal carries the investigation it came out of, as a link', async ({
  page,
}) => {
  await page.goto('/decisions?tab=changes');

  const origin = page.getByTestId('origin-run').first();
  await expect(origin).toBeVisible();
  await expect(origin).toHaveAttribute('href', /^\/runs\/run-/);
});
