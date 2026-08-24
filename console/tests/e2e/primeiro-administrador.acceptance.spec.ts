import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * The ten normative claims of "primeiro administrador", encoded one
 * assertion per claim.
 *
 * **Two states this file needs, and one mock plane serves one scenario at a
 * time** — the same constraint `030-uma-fonte-por-fato` and `first-day`
 * document. Claims 1, 2, 3, 4 and 9 are about a deployment that has never
 * been claimed: no administrator, no identity provider. Claims 5, 6, 7, 8
 * and 10 are about a deployment that already has one — the ordinary state
 * of every fixture this repository ships, and of staging.
 *
 * The `behaviour` project's committed dataset is already administered, so
 * this file's "unclaimed" block runs against a scenario that reports
 * `unclaimed` for `GET /v1/setup/local-administrator` — which, at the time
 * this spec was written, no mock scenario does yet: the route is new. That
 * block is therefore expected to be red here, honestly, until either the
 * mock plane's dataset is extended with this endpoint (generated through
 * `tools/mockplane/dataset/served.py`, never hand-edited — see
 * `fixtures/scenarios/**`) or the assertions run against a compose backing
 * with a genuinely fresh deployment, as the specification calls for. The
 * failure this file captures for that block is the real one: the notice
 * this feature adds is absent, because the fact it depends on answers
 * `administered` (or 404s) against every dataset that exists today, not
 * `unclaimed`.
 *
 * **This block cannot be faked with `page.route()`.** Both screens read
 * `GET /v1/setup/local-administrator` from a Server Component, on the
 * console's own server process — the request never reaches the browser's
 * network stack, so nothing a browser-side interception installs is ever
 * asked. `030-uma-fonte-por-fato` documents the identical limitation for
 * the incidents list, for the same reason.
 */

const COMMAND_TESTID = 'no-administrator-command';
const NOTICE_TESTID = 'no-administrator-notice';
const STAGING_SAFE_TAG = '@staging-safe';

test.use({ viewport: { width: 1920, height: 1080 } });

// =============================================================================
// Claims 1-4 and 9: a deployment nobody has claimed yet
// =============================================================================

test.describe('the sign-in screen, before anybody has claimed this deployment', () => {
  test('claim 1: shows an identifiable warning block', async ({ page }) => {
    await page.goto('/sign-in');
    await expect(page.getByTestId(NOTICE_TESTID)).toBeVisible();
  });

  test('claim 2: the block contains the command, literal, in a region that selects and copies', async ({
    page,
  }) => {
    await page.goto('/sign-in');
    const command = page.getByTestId(COMMAND_TESTID);
    await expect(command).toBeVisible();
    const className = (await command.getAttribute('class')) ?? '';
    expect(className).toContain('select-all');
    const text = (await command.textContent())?.trim() ?? '';
    expect(text).toMatch(/^ninjasre setup admin\b/);
  });

  test('claim 3: the block sits above the form, not inside it', async ({ page }) => {
    await page.goto('/sign-in');
    const notice = page.getByTestId(NOTICE_TESTID);
    const form = page.getByTestId('sign-in-form');
    await expect(form.getByTestId(NOTICE_TESTID)).toHaveCount(0);
    const noticeBox = await notice.boundingBox();
    const formBox = await form.boundingBox();
    expect(noticeBox, 'the notice did not render').not.toBeNull();
    expect(formBox, 'the form did not render').not.toBeNull();
    if (noticeBox !== null && formBox !== null) {
      expect(noticeBox.y).toBeLessThan(formBox.y);
    }
  });

  test('claim 4: the form still has exactly two fields and one button', async ({
    page,
  }) => {
    await page.goto('/sign-in');
    const form = page.getByTestId('sign-in-form');
    await expect(form.locator('input:not([type="hidden"])')).toHaveCount(2);
    await expect(form.locator('button')).toHaveCount(1);
  });
});

test.describe('the first-run screen, before anybody has claimed this deployment', () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
  });

  test('claim 9: shows the same command, from the same key as the sign-in screen', async ({
    page,
  }) => {
    await page.goto('/sign-in');
    const onSignIn = (
      (await page.getByTestId(COMMAND_TESTID).textContent()) ?? ''
    ).trim();

    await page.goto('/first-run');
    const onFirstRun = (
      (await page.getByTestId(COMMAND_TESTID).textContent()) ?? ''
    ).trim();

    expect(onFirstRun, 'first-run named a different command than sign-in did').toBe(
      onSignIn,
    );
    expect(onFirstRun).not.toBe('');
  });
});

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
