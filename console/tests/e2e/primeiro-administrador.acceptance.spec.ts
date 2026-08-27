import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * Six of the ten normative claims of "primeiro administrador" — the ones
 * about a deployment that already has an administrator, or that names no
 * mechanism at all. Encoded one assertion per claim.
 *
 * **Two states this file's claims need, and one mock plane serves one
 * scenario at a time** — the same constraint `030-uma-fonte-por-fato`
 * documents and resolves the same way `first-day` already does. Claims 5,
 * 7, 8 and 10 are about a deployment that already has an administrator —
 * the `behaviour` project's own committed dataset, and the ordinary state
 * of every fixture this repository ships, and of staging. Claims 1, 2, 3,
 * 4 and 9 are about a deployment nobody has claimed yet, and live in
 * `console/tests/first-day/primeiro-administrador.acceptance.spec.ts`
 * instead, against the `first-run` dataset — the one committed scenario
 * that reports `unclaimed` for `GET /v1/setup/local-administrator`,
 * following the same project split
 * `010-provider-out-of-the-box.acceptance.spec.ts` already uses for a
 * claim that needs that same dataset. Moving the block there rather than
 * asserting it here is what lets this file's dataset stay administered,
 * which claims 5, 7, 8 and 10 depend on.
 *
 * **This fact cannot be faked with `page.route()`.** Both screens read
 * `GET /v1/setup/local-administrator` from a Server Component, on the
 * console's own server process — the request never reaches the browser's
 * network stack, so nothing a browser-side interception installs is ever
 * asked. `030-uma-fonte-por-fato` documents the identical limitation for
 * the incidents list, for the same reason.
 */

const NOTICE_TESTID = 'no-administrator-notice';
const STAGING_SAFE_TAG = '@staging-safe';

test.use({ viewport: { width: 1920, height: 1080 } });

// =============================================================================
// Claims 5, 7, 8: a deployment that already has an administrator
// =============================================================================

test.describe('the sign-in screen, already administered (staging-safe)', () => {
  test(
    'claim 5: the block does not exist in the document — not merely hidden',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/sign-in');
      await expect(page.getByTestId(NOTICE_TESTID)).toHaveCount(0);
    },
  );

  test(
    'claim 7: a refused sign-in shows the same refusal as always, and the notice never joins it',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/sign-in');
      await page.getByLabel(/username/i).fill('nobody-this-account-does-not-exist');
      await page.getByLabel(/password/i).fill('definitely the wrong passphrase');
      await page.getByTestId('sign-in-form').locator('button[type="submit"]').click();

      await expect(page.getByTestId('sign-in-reason')).toBeVisible();
      await expect(page.getByTestId(NOTICE_TESTID)).toHaveCount(0);
    },
  );

  test(
    'claim 8: the sign-in screen still names no deployment anywhere',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/sign-in');
      // The screen's own claim about itself, independent of this feature —
      // guarded here because the notice this feature adds is exactly the
      // kind of addition that could have reintroduced a deployment name.
      const title = await page.title();
      expect(title.toLowerCase()).not.toContain('deployment');
      await expect(page.getByTestId(NOTICE_TESTID)).toHaveCount(0);
    },
  );
});

// =============================================================================
// Claim 6: a deployment with an identity provider
// =============================================================================

test.describe('the sign-in screen, an identity provider is the way in', () => {
  test.skip(
    true,
    'requires a deployment configured with an active identity provider; not reachable ' +
      'from either the committed mock dataset or a plain compose bring-up — needs a ' +
      'deployment the orchestrator configures with SSO active, or the mock dataset ' +
      'extended with that state (tools/mockplane/dataset/served.py)',
  );

  test('claim 6: the block does not exist in the document', async ({ page }) => {
    await page.goto('/sign-in');
    await expect(page.getByTestId(NOTICE_TESTID)).toHaveCount(0);
  });
});

// =============================================================================
// Claim 10: neither screen ever prints a raw catalogue key
// =============================================================================

test.describe('the catalogue keys this feature added are never printed raw', () => {
  async function assertsNoRawKey(page: Page, path: string): Promise<void> {
    await page.goto(path);
    const body = (await page.textContent('body')) ?? '';
    expect(body).not.toContain('noAdministrator.title');
    expect(body).not.toContain('noAdministrator.body');
  }

  test(
    'claim 10a: /sign-in never shows a raw i18n key',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await assertsNoRawKey(page, '/sign-in');
    },
  );

  test('claim 10b: /first-run never shows a raw i18n key', async ({
    page,
    context,
    baseURL,
  }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
    await assertsNoRawKey(page, '/first-run');
  });
});
