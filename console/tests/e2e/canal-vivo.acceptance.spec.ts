import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * The deployment-wide channel, from the browser: a run appears on the Painel
 * without a reload, the chip tells the truth when the channel drops, and a
 * reconnection does not duplicate what was already shown.
 *
 * Backing: `mock`. The claim under test is the console's own wiring —
 * `AutoRefresh` opening `DeploymentConnection`, the chip reading its state,
 * a route interception standing in for the deployment going away — none of
 * which needs a real gateway, and `tools/mockplane/server.py`'s
 * `_serve_deployment_stream` exists precisely so this file does not need one.
 *
 * The Painel has no per-run card yet — that arrives with a later feature in
 * this wave, on top of this same channel. What it has today, and what this
 * file asserts against, is the Guardian band's "em execução agora" list
 * (`guardian-flight`, one row per running investigation) and its own count
 * (`tally-flight`) — the concrete, already-rendered proxy for "the run
 * appearing" until the card exists to assert on directly.
 *
 * **Two ways of forcing a drop, used for two different moments.** US2 needs
 * the *first* connection this test ever makes to fail, so `page.route()` —
 * which only ever governs a request made after it is registered — is exactly
 * right there. US3 needs a connection that is *already open and healthy* to
 * drop, and `page.route()` cannot do that: it does not intercept a request
 * already in flight, and neither does `context.setOffline()` sever this
 * mock's already-established response (both were tried against this exact
 * harness). `DROP_DEPLOYMENT_STREAM_PATH` is the mock's own answer — a
 * control route that ends the caller's open deployment stream on its next
 * poll tick, the live-server equivalent of the unit-level
 * `StreamControl.disconnect_after` the per-run stream already has.
 */

const BACKING_URL = process.env.NINJASRE_CONSOLE_BACKING_URL;

/** Where this test's own mock plane answers, asserted present: this file only ever runs against `--backing mock`. */
function backingUrl(): string {
  if (BACKING_URL === undefined) {
    throw new Error(
      'NINJASRE_CONSOLE_BACKING_URL is not set; this spec requires the mock backing',
    );
  }
  return BACKING_URL;
}

/** End the signed-in session's own open deployment stream, once, from the mock's control surface. */
async function dropDeploymentStream(page: Page): Promise<void> {
  const response = await page.request.post(
    `${backingUrl()}/__mockplane__/drop-deployment-stream`,
  );
  expect(response.status()).toBe(204);
}

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

// --- US1: a run started on another page appears here, without a reload -------

test('a run started from another page appears on the Painel without a reload', async ({
  context,
  page,
}) => {
  await page.goto('/');
  await expect(page.getByTestId('freshness')).toHaveAttribute('data-state', 'live', {
    timeout: 10_000,
  });

  const before = await page.getByTestId('guardian-flight').count();
  const objective = `canal vivo probe ${String(Date.now())}`;

  // A second page, the same signed-in context: the operator watching the
  // Painel is not the one who starts the investigation.
  const other = await context.newPage();
  await other.goto('/runs');
  await other.getByTestId('investigate').click();
  await other.getByTestId('investigate-drawer').waitFor({ state: 'visible' });
  await other.locator('textarea[name="objective"]').fill(objective);
  await other.getByTestId('start-investigation').click();
  await other.close();

  // No `page.reload()`, no navigation — the Painel is polled for the DOM
  // settling on its own, which is what proves the channel drove it there.
  await expect
    .poll(async () => page.getByTestId('guardian-flight').count(), { timeout: 10_000 })
    .toBeGreaterThan(before);

  // The chip never left `live` while this happened — a stale/fallback chip
  // claiming to be current would be the one thing this feature must not do.
  await expect(page.getByTestId('freshness')).toHaveAttribute('data-state', 'live');
});

// --- US2: the channel drops, the chip says fallback, the timer still covers --

test('the chip falls back honestly when the channel drops, and content keeps moving', async ({
  page,
}) => {
  await page.route('**/api/events/stream', async (route) => {
    await route.fulfill({ status: 502, body: '{"streaming":false}' });
  });

  await page.goto('/');

  // Refused from the very first attempt, so the fallback path this test
  // measures is "the channel never opens", not "it opened and then dropped"
  // — both are the same client behaviour (the timer covers), and the first
  // is the one a single route interception, in place before navigation,
  // actually produces.
  await expect(page.getByTestId('freshness')).toHaveAttribute('data-state', 'stale', {
    timeout: 30_000,
  });

  // The fallback's whole point: the page is not frozen. Un-route and let the
  // ordinary timer (already running, per the fallback contract) bring a
  // fresh read in on its own next tick.
  await page.unroute('**/api/events/stream');
  await expect(page.getByTestId('freshness')).toHaveAttribute('data-state', 'live', {
    timeout: 30_000,
  });
});

// --- US3: reconnection does not duplicate what was already shown -------------

test('a reconnection does not duplicate a run already shown', async ({
  context,
  page,
}) => {
  await page.goto('/');
  const objective = `canal vivo reconnect probe ${String(Date.now())}`;

  const other = await context.newPage();
  await other.goto('/runs');
  await other.getByTestId('investigate').click();
  await other.getByTestId('investigate-drawer').waitFor({ state: 'visible' });
  await other.locator('textarea[name="objective"]').fill(objective);
  await other.getByTestId('start-investigation').click();
  await other.close();

  await expect
    .poll(async () => page.getByTestId('guardian-flight').count(), { timeout: 10_000 })
    .toBeGreaterThan(0);
  const afterFirstRun = await page.getByTestId('guardian-flight').count();

  // Force exactly one disconnect/reconnect cycle on the connection that is
  // already open — see the module docstring for why this is the mock's own
  // control route rather than `page.route()` or `context.setOffline()`.
  await dropDeploymentStream(page);
  await expect(page.getByTestId('freshness')).toHaveAttribute('data-state', 'stale', {
    timeout: 30_000,
  });
  await expect(page.getByTestId('freshness')).toHaveAttribute('data-state', 'live', {
    timeout: 30_000,
  });

  // The same run, once — not shown a second time because the reconnection
  // replayed or re-triggered something the first connection already caused.
  expect(await page.getByTestId('guardian-flight').count()).toBe(afterFirstRun);
});
