import { expect, test } from '@playwright/test';

/**
 * The console, a browser, and a gateway answering from the committed dataset.
 *
 * What this proves that a unit test cannot: the built artefact serves, the
 * server component's fetch reaches the address the deployment configured, and
 * what comes back is rendered into the document a browser actually parses.
 */
test('the run list renders what the gateway reported', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Investigations' })).toBeVisible();
  const runs = page.getByTestId('run');
  await expect(runs.first()).toBeVisible();
  expect(await runs.count()).toBeGreaterThan(0);
});

test('each run carries the role its status maps to', async ({ page }) => {
  await page.goto('/');

  const first = page.getByTestId('run').first();
  const status = await first.getByTestId('run-status').innerText();
  const role = await first.getAttribute('data-role');

  expect(role).not.toBeNull();
  if (status === 'succeeded') {
    expect(role).toBe('success');
  }
});
