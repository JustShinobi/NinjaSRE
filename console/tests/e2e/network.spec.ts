import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * Nothing the console serves may fetch from a host the operator does not run.
 *
 * This is the assertion behind "the operator owns their data" for a front end:
 * a bundled font that is actually a stylesheet pointing at a font host is
 * indistinguishable from a bundled font until somebody watches the network.
 * So something does, on every run, and the list of what it saw is the evidence.
 */
const LOCAL = new Set(['127.0.0.1', 'localhost', '[::1]', '0.0.0.0']);

/** The run whose recorded report carries a remote image, exactly what this file exists to catch. */
const HOSTILE_REPORT_ROUTE = '/runs/run-0103';

/** Start collecting every request `page` issues that leaves the deployment. */
function trackExternalRequests(page: import('@playwright/test').Page): string[] {
  const external: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.protocol === 'data:' || url.protocol === 'blob:') {
      return;
    }
    if (!LOCAL.has(url.hostname)) {
      external.push(request.url());
    }
  });
  return external;
}

test('a production build issues no request that leaves the deployment', async ({
  page,
}) => {
  const external = trackExternalRequests(page);

  await page.goto('/');
  await page.waitForLoadState('networkidle');

  expect(external, `the console requested ${external.join(', ')}`).toEqual([]);
});

test('a report naming a remote image issues no request for it', async ({
  page,
  context,
  baseURL,
}) => {
  const external = trackExternalRequests(page);

  await signIn(context, baseURL ?? 'http://127.0.0.1:8425');
  await page.goto(HOSTILE_REPORT_ROUTE);
  await page.waitForLoadState('networkidle');

  // The claim this test exists to prove: the image in the recorded report
  // became its alt text, not an <img> the browser went and fetched.
  await expect(page.getByTestId('report').locator('img')).toHaveCount(0);
  expect(external, `the console requested ${external.join(', ')}`).toEqual([]);
});
