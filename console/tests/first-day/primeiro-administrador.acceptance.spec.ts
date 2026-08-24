import { expect, test } from '@playwright/test';

import { signIn } from '../e2e/session';

/**
 * Claims 1-4 and 9 of "primeiro administrador": the sign-in and first-run
 * screens, on a deployment nobody has claimed yet.
 *
 * Run against the `first-run` dataset for the reason
 * `010-provider-out-of-the-box.acceptance.spec.ts` beside this file already
 * is: one mock plane serves one scenario, and the `behaviour` project's own
 * dataset is already administered — claims 5, 7, 8 and 10, in
 * `primeiro-administrador.acceptance.spec.ts`, depend on it staying that
 * way. `first-run` is the one committed scenario nobody has opened local
 * sign-in on (`GET /v1/setup/local-administrator` answers `unclaimed`
 * there, the CLI invitation attached), which is exactly the state these
 * five claims are about.
 *
 * Claim 9 signs in before it starts, the same as every other spec in this
 * project — a viewer who reached `/first-run` at all is always signed in,
 * through the environment account or an identity provider, and "signed in"
 * is a different fact from "this deployment has a local administrator"
 * (the comment on `first-run.tsx`'s own read of the notice names the same
 * distinction). It still reads `/sign-in` first because the claim is that
 * both screens name the same command from the same key, not that either
 * one is reachable unauthenticated.
 */

const COMMAND_TESTID = 'no-administrator-command';
const NOTICE_TESTID = 'no-administrator-notice';

test.use({ viewport: { width: 1920, height: 1080 } });

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
