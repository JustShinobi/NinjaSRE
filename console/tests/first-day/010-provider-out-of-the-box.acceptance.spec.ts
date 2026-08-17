import { expect, test } from '@playwright/test';

import { signIn } from '../e2e/session';

/**
 * The normative claims of the mockup's Verify step (`#m5`).
 *
 * Run against the `first-run` dataset — a deployment mid-setup, which is the
 * only dataset where `/first-run` renders at all rather than handing back to
 * the dashboard (`setup-wizard.spec.ts`, in the `behaviour` project, is the
 * regression test for that redirect on a *finished* checklist). The provider
 * this dataset configured is Google Gemini, degraded on tool calling; the two
 * connected integrations are Prometheus and Proxmox VE.
 *
 * Every row's own chip starts from what the deployment already recorded
 * (`thing.readiness`, a checklist-wide fact) and becomes what a live check
 * found once somebody presses the row's own button — the same
 * listing-is-free/verifying-is-not split `settings/models-providers`'s
 * acceptance spec exercises, applied per row here instead of to one card.
 */

const ROUTE = '/first-run?step=verify';

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test.describe('Setup — the Verify step mirrors the preflight, never translates it', () => {
  test('one row per verifiable dependency, each with a chip and a display name', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    const rows = page.getByTestId('verify-row');
    await expect(rows).toHaveCount(3);

    const provider = page
      .getByTestId('verify-row')
      .filter({ hasText: 'Google Gemini' });
    await expect(provider).toBeVisible();

    // Display names, never raw catalogue identifiers.
    await expect(
      page.getByTestId('verify-row').filter({ hasText: 'Prometheus' }),
    ).toBeVisible();
    await expect(
      page.getByTestId('verify-row').filter({ hasText: 'Proxmox VE' }),
    ).toBeVisible();
    const body = await page.locator('body').innerText();
    expect(body).not.toContain('google_gemini');
    expect(body).not.toMatch(/\bprometheus\b/);
    expect(body).not.toMatch(/\bproxmox\b/);
  });

  test('checking the provider reports Degraded — never Failing — with what passed and the exit', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    const provider = page
      .getByTestId('verify-row')
      .filter({ hasText: 'Google Gemini' });
    await provider.getByTestId('verify-one').click();

    await expect(provider.getByTestId('status-chip')).toHaveText('Degraded');
    const detail = (await provider.getByTestId('verify-detail').textContent()) ?? '';
    expect(detail.length).toBeGreaterThan(0);
  });

  test('checking an integration reports Verified and how long it took to answer', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    const prometheus = page.getByTestId('verify-row').filter({ hasText: 'Prometheus' });
    await prometheus.getByTestId('verify-one').click();

    await expect(prometheus.getByTestId('status-chip')).toHaveText('Verified');
    await expect(prometheus.getByTestId('verify-latency')).toHaveText(
      /answered in \d+\s?ms/i,
    );
  });

  test('the footer counts what is degraded and says nothing is failing, and Continue is enabled', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    for (const name of ['Google Gemini', 'Prometheus', 'Proxmox VE']) {
      await page
        .getByTestId('verify-row')
        .filter({ hasText: name })
        .getByTestId('verify-one')
        .click();
    }

    const footer = page.getByTestId('verify-footer');
    await expect(footer).toContainText(/1/);
    await expect(footer).toContainText(/degraded/i);
    await expect(footer).toContainText(/none failing/i);

    await expect(page.getByTestId('verify-continue')).toBeEnabled();
  });

  test('a failing check holds Continue back and names the row responsible', async ({
    page,
  }) => {
    // A live override for this one test: the fixture's own three rows are
    // degraded/verified/verified, and the claim under test — a real failure
    // blocking the step — needs one that fails, without inventing a fourth
    // named dependency the rest of this dataset does not have.
    //
    // Intercepted at `/api/verify`, the address the browser itself calls —
    // not the gateway route behind it, which this courier reaches from the
    // Next.js server process rather than from the page, where Playwright's
    // network interception has nothing to attach to.
    await page.route('**/api/verify', async (route) => {
      const body: unknown = route.request().postDataJSON();
      const name: unknown =
        typeof body === 'object' && body !== null
          ? Reflect.get(body, 'name')
          : undefined;
      if (name !== 'prometheus') {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          reachable: true,
          verified: false,
          reason: 'the credential was rejected: the token has expired',
          checks: [],
          findings: [],
        }),
      });
    });

    await page.goto(ROUTE);

    const prometheus = page.getByTestId('verify-row').filter({ hasText: 'Prometheus' });
    await prometheus.getByTestId('verify-one').click();
    await expect(prometheus.getByTestId('status-chip')).toHaveText('Failing');

    const continueButton = page.getByTestId('verify-continue');
    await expect(continueButton).toBeDisabled();
    await expect(page.getByTestId('verify-blocking-row')).toHaveText(/Prometheus/);
  });
});
