import { expect, test } from '@playwright/test';

import { signIn } from '../e2e/session';

/**
 * The destinations CTA, on a deployment that cannot deliver a message at all.
 *
 * This is the reproduction of a defect worth naming precisely, because the
 * page was never silent about it — it was *contradicting itself*. The sentence
 * in the body is the deployment's own: "Connect a chat or notification
 * integration in the catalogue, then declare a destination here." The button
 * underneath it opened the raw configuration editor, which is not the
 * catalogue and cannot connect anything. An operator who read the words and an
 * operator who pressed the button went to two different places.
 *
 * It belongs in this project rather than in `tests/e2e/`, because the state it
 * needs — nothing wired that can carry a message — is the first-day dataset,
 * and one mock plane serves one scenario.
 */

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test.describe('a deployment with nothing that can deliver a message', () => {
  test('sends the destinations CTA to the catalogue, never to the schema editor', async ({
    page,
  }) => {
    await page.goto('/settings/schedules-destinations');

    const cta = page.getByTestId('way-back').first();
    await expect(cta).toBeVisible();

    const href = await cta.getAttribute('href');
    expect(href).not.toBeNull();

    // The defect, stated as the assertion that would have failed: the button
    // used to open `/configuration`.
    expect(href).not.toContain('/configuration');

    // And what it does instead: the catalogue, narrowed to the one category
    // that can fix this. `communication` is the category the vendor catalogue
    // actually declares — there is no `chat`.
    expect(href).toContain('/integrations');
    expect(href).toContain('category=communication');

    // Never `view=`: that filter narrows to what is already connected or
    // suggested, which on this deployment is precisely nothing, so it would
    // hide every vendor the operator came here to find.
    expect(href).not.toContain('view=');
  });

  test('says in the body what the button then does', async ({ page }) => {
    await page.goto('/settings/schedules-destinations');

    // The body sentence is the deployment's, not the console's. The two
    // agreeing is the whole property.
    await expect(page.getByText(/catalogue/i).first()).toBeVisible();
  });

  test('actually arrives at the catalogue, filtered, when pressed', async ({
    page,
  }) => {
    await page.goto('/settings/schedules-destinations');

    await page.getByTestId('way-back').first().click();

    // Followed for real rather than asserted on the attribute alone: a CTA
    // that resolves to the right address and then fails to land on it is the
    // same broken promise from the operator's side.
    await expect(page).toHaveURL(/\/integrations\?.*category=communication/);
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'integrations',
    );
  });
});
