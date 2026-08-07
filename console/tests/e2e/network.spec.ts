import { expect, test } from '@playwright/test';

/**
 * Nothing the console serves may fetch from a host the operator does not run.
 *
 * This is the assertion behind "the operator owns their data" for a front end:
 * a bundled font that is actually a stylesheet pointing at a font host is
 * indistinguishable from a bundled font until somebody watches the network.
 * So something does, on every run, and the list of what it saw is the evidence.
 */
const LOCAL = new Set(['127.0.0.1', 'localhost', '[::1]', '0.0.0.0']);

test('a production build issues no request that leaves the deployment', async ({
  page,
}) => {
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

  await page.goto('/');
  await page.waitForLoadState('networkidle');

  expect(external, `the console requested ${external.join(', ')}`).toEqual([]);
});
