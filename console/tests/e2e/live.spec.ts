import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The live layer, in a browser, against a running deployment.
 *
 * Everything else about this feature is provable without one — that is the
 * whole point of the reducer being pure. What is not provable without one is
 * that the pieces are actually connected: that a page opens a stream, that the
 * deployment answers it, that frames become entries in the transcript a replay
 * would have filled, and that the drawer which starts an investigation is
 * reachable without leaving the page you are on.
 */

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test('a run that is still going is watched rather than read back', async ({ page }) => {
  await page.goto('/runs/run-0003');

  const live = page.getByTestId('live-run');
  await expect(live).toBeVisible();
  // Whether it is arriving is on the screen, always. A live transcript that
  // said nothing about its connection would be indistinguishable from a stale
  // one the moment the connection went.
  await expect(page.getByTestId('connection')).toBeVisible();

  // The events came from the stream: the replay is not rendered for a run that
  // has not finished, so anything on screen arrived over the wire.
  await expect(page.getByTestId('transcript-event').first()).toBeVisible();
  await expect(live).toHaveAttribute('data-phase', 'running');
});

test('the transcript fills as frames arrive, in sequence order', async ({ page }) => {
  await page.goto('/runs/run-0003');

  const entries = page.getByTestId('transcript-event');
  await expect(entries.first()).toBeVisible();
  // The first thing a run does is start. If the ordering were wrong this is
  // where it would show, because the deployment sends them fastest at the top.
  await expect(entries.first()).toHaveAttribute('data-raw-kind', 'run_started');

  // Polled rather than read once: the deployment sends frames at its own rate,
  // and asserting on the count at an arbitrary instant is a test that passes on
  // a fast machine and fails on a loaded one.
  await expect
    .poll(async () =>
      Number(await page.getByTestId('transcript').getAttribute('data-total')),
    )
    .toBeGreaterThan(1);
});

test('a run that has finished is read back through the same transcript', async ({
  page,
}) => {
  await page.goto('/runs/run-0001');

  await expect(page.getByTestId('transcript-event').first()).toBeVisible();
  // No stream, no connection badge, and the same entries: a replayed view and a
  // live view are the same component and differ only in whether one is arriving.
  await expect(page.getByTestId('live-run')).toHaveCount(0);
  await expect(page.getByTestId('connection')).toHaveCount(0);
});

test('an investigation can be started from anywhere, without leaving the page', async ({
  page,
}) => {
  await page.goto('/runs');
  const before = page.url();

  await page.getByTestId('investigate').click();

  await expect(page.getByTestId('investigate-drawer')).toBeVisible();
  // Still on the run list. The thing an operator is looking at when they decide
  // to investigate is the reason they are investigating.
  expect(page.url()).toBe(before);
  await expect(page.getByTestId('row').first()).toBeVisible();
});

test('a live run offers control of it, and stopping it asks first', async ({
  page,
}) => {
  await page.goto('/runs/run-0003');

  await expect(page.getByTestId('takeover')).toBeVisible();
  await page.getByTestId('stop-run').click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  // Named target, named consequence, and the safe option beside the dangerous
  // one rather than behind it.
  await expect(dialog.getByText('run-0003')).toBeVisible();
});
