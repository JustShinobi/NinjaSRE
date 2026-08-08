import { expect, test } from '@playwright/test';

// A browser test that asserts a heading the console does not render. It exists
// to prove that a red end-to-end suite reddens `make verify`.
test('the seeded failing end-to-end test', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'A heading nobody renders' })).toBeVisible();
});
