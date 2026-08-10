import { expect, test, type Page, type Request, type Response } from '@playwright/test';

import { signIn } from '../e2e/session';

/**
 * The first day, in a browser.
 *
 * Three claims can only be made here, and each of them is about what a *page*
 * does rather than what a component returns.
 *
 * **Nothing redirects.** A fresh deployment's dashboard is the dashboard, with
 * its figures at zero, the tutorial over the top of it and the checklist beside
 * it. The address never leaves the shell. A unit test cannot say that, because
 * a unit test has no address.
 *
 * **No secret is anywhere.** A sentinel is typed into the credential form and
 * then hunted for in every response body the browser received, in the rendered
 * document, in the server-component payload, and in browser storage. The
 * payload is the one a component test structurally cannot see: React sends the
 * props of a server component down the wire as text, and a value that reached
 * one would be sitting in the page source with nothing rendering it.
 *
 * **Killing the browser loses nothing.** The context is destroyed mid-flow and
 * a new one opened. It resumes correctly because there is nothing to resume
 * *from* — the step is derived from the deployment, and this asserts the
 * absence that makes that true.
 */

/** What is typed into the credential field, and hunted for afterwards. */
const SENTINEL = 'sk-ant-e2e-3f9c1a7b5d0e2846';

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

/** Every response body this page received, as text, for the sweep. */
function collectBodies(page: Page): { bodies: string[]; addresses: string[] } {
  const bodies: string[] = [];
  const addresses: string[] = [];
  page.on('request', (request: Request) => {
    addresses.push(request.url());
    const posted = request.postData();
    // A request body is where the secret is *supposed* to be, exactly once, on
    // the way to the vault. What is asserted below is that it is nowhere else.
    if (posted !== null && !request.url().includes('/api/credential')) {
      bodies.push(`REQUEST ${request.url()} ${posted}`);
    }
  });
  page.on('response', (response: Response) => {
    void response
      .text()
      .then((text) => {
        bodies.push(`RESPONSE ${response.url()} ${text}`);
      })
      .catch(() => undefined);
  });
  return { bodies, addresses };
}

test('a fresh deployment renders the product, not a form in front of it', async ({
  page,
}) => {
  await page.goto('/');

  // The dashboard, at its own address, with honest numbers on it.
  expect(new URL(page.url()).pathname).toBe('/');
  await expect(page.getByTestId('main-figures')).toBeVisible();
  await expect(page.getByTestId('tutorial')).toBeVisible();
  await expect(page.getByTestId('tutorial-skip')).toBeVisible();

  // The tutorial is over the top of the product rather than instead of it: the
  // page behind it has already rendered.
  await expect(page.getByTestId('page-header')).toHaveAttribute(
    'data-area',
    'dashboard',
  );

  await page.getByTestId('tutorial-skip').click();
  await expect(page.getByTestId('tutorial')).toBeHidden();

  const checklist = page.getByTestId('setup-checklist');
  await expect(checklist).toBeVisible();
  await page.getByTestId('checklist-next').click();
  await expect(page).toHaveURL(/\/first-run\?step=/);
  await expect(page.getByTestId('page-header')).toHaveAttribute(
    'data-area',
    'first-run',
  );
});

test('the guided run walks provider to verification without leaving the shell', async ({
  page,
}) => {
  const seen: string[] = [];
  page.on('framenavigated', (frame) => {
    if (frame.parentFrame() === null) seen.push(new URL(frame.url()).pathname);
  });

  await page.goto('/first-run');
  await expect(page.getByTestId('wizard-body')).toHaveAttribute(
    'data-step',
    'provider',
  );

  // All nine, and the local one drawn like the other eight.
  await expect(page.getByTestId('provider-option')).toHaveCount(9);
  await expect(
    page.locator('[data-testid="provider-option"][data-local="true"]'),
  ).toHaveCount(1);

  await page
    .locator('[data-testid="provider-option"][data-provider="anthropic"]')
    .getByTestId('choose-provider')
    .click();
  await expect(page.getByTestId('wizard-body')).toHaveAttribute(
    'data-step',
    'credential',
  );
  await expect(page.getByTestId('where-to-get-it')).toBeVisible();

  await page.getByTestId('credential').locator('input').first().fill(SENTINEL);
  await page.getByTestId('store-credential').click();
  // The deployment accepted it. Asserting only that *a* result appeared would
  // pass identically against a refusal, and against a route nothing serves.
  await expect(page.getByTestId('credential-result')).toHaveText(/Stored\./);

  // The remaining steps are reachable and each says why it exists.
  for (const step of ['model', 'integrations', 'verify', 'estate', 'alerts']) {
    await page.goto(`/first-run?step=${step}`);
    await expect(page.getByTestId('wizard-body')).toHaveAttribute('data-step', step);
    await expect(page.getByTestId('wizard-body')).not.toBeEmpty();
  }

  // And an integration is connected and then checked, in the browser, through
  // the same two routes the deployment serves. Both halves are asserted on
  // their outcome rather than on a control having appeared.
  await page.goto('/first-run?step=integrations');
  const offer = page.getByTestId('integration-offer').first();
  await offer.locator('input[type="password"]').first().fill('a-vendor-token');
  await offer.getByTestId('store-credential').click();
  await expect(offer.getByTestId('credential-result')).toHaveText(/Stored\./);
  await expect(page.getByTestId('integrations-summary')).toContainText('metrics-store');

  // Every navigation stayed inside the shell. Not one of them was a bounce to a
  // route outside it, which is the whole of the revised model.
  for (const path of seen) {
    expect(path === '/' || path.startsWith('/first-run')).toBe(true);
  }
});

test('the sentinel reaches the vault and appears nowhere else', async ({ page }) => {
  const { bodies, addresses } = collectBodies(page);

  await page.goto('/first-run?step=credential&provider=anthropic');
  await page.getByTestId('credential').locator('input').first().fill(SENTINEL);
  await page.getByTestId('store-credential').click();
  await expect(page.getByTestId('credential-result')).toBeVisible();
  await page.goto('/first-run');
  await page.goto('/');

  // Not in an address, not in a query, not in a redirect.
  for (const address of addresses) {
    expect(address, 'a credential reached a URL').not.toContain(SENTINEL);
  }

  // Not in any response body, and not in any request body but the one write.
  for (const body of bodies) {
    expect(body.slice(0, 200), 'a credential was echoed').not.toContain(SENTINEL);
    expect(body).not.toContain(SENTINEL);
  }

  // Not in the rendered document, and not in the server-component payload —
  // which is in the page source as text and is the place a masked field would
  // still be a value.
  const source = await page.content();
  expect(source).not.toContain(SENTINEL);

  // Not in anything the browser kept.
  const stored = await page.evaluate(() => ({
    local: JSON.stringify(window.localStorage),
    session: JSON.stringify(window.sessionStorage),
    cookie: document.cookie,
  }));
  expect(stored.local).not.toContain(SENTINEL);
  expect(stored.session).not.toContain(SENTINEL);
  expect(stored.cookie).not.toContain(SENTINEL);
});

test('killing the browser mid-flow loses nothing, because nothing was kept', async ({
  browser,
  baseURL,
}) => {
  const first = await browser.newContext();
  await signIn(first, baseURL ?? 'http://127.0.0.1:8423');
  const page = await first.newPage();
  // Deliberately parked on a step that is *not* the one the deployment implies,
  // and a credential typed and stored, so a browser that remembered anything
  // would have something to remember.
  await page.goto('/first-run?step=verify&provider=anthropic');
  const derived = await page
    .goto('/first-run')
    .then(() => page.getByTestId('wizard-body').getAttribute('data-step'));
  await page.goto('/first-run?step=credential&provider=anthropic');
  await page.getByTestId('credential').locator('input').first().fill(SENTINEL);
  await page.getByTestId('store-credential').click();
  await expect(page.getByTestId('credential-result')).toBeVisible();

  // Nothing about where the wizard is has been written down in this browser.
  const kept = await page.evaluate(() => ({
    local: Object.keys(window.localStorage),
    session: Object.keys(window.sessionStorage),
    cookie: document.cookie,
  }));
  expect(kept.local).toEqual([]);
  expect(kept.session).toEqual([]);
  expect(kept.cookie).not.toContain('step');
  expect(kept.cookie).not.toContain('first-run');

  await first.close();

  const second = await browser.newContext();
  await signIn(second, baseURL ?? 'http://127.0.0.1:8423');
  const reopened = await second.newPage();
  await reopened.goto('/first-run');

  // The same step the first context derived before any of that happened —
  // computed from the deployment, not carried over. Had the console kept a
  // cursor, this would be `verify` (where the first context was parked) or
  // `credential` (where it was last); it is neither.
  await expect(reopened.getByTestId('wizard-body')).toHaveAttribute(
    'data-step',
    derived ?? '',
  );
  await expect(reopened.getByTestId('wizard-step')).toHaveCount(7);
  await second.close();
});

test('the navigation entry appears while there is something left to do', async ({
  page,
}) => {
  await page.goto('/');
  // The tutorial is over the whole page on purpose, so it is dismissed before
  // anything behind it is clicked — which is itself the overlay working.
  await page.getByTestId('tutorial-skip').click();

  const entry = page.locator('[data-testid="nav-entry"][data-area="first-run"]');
  await expect(entry).toBeVisible();
  await entry.click();
  await expect(page).toHaveURL(/\/first-run/);
});
