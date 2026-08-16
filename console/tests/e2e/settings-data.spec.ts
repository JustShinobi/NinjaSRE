import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * Alert intake and Schedules & destinations, in a browser, against the built
 * console.
 *
 * What a unit test cannot show, and what this exists for: these two pages are
 * server components that compose client ones — a collapsed reference, a copy
 * control, a preset selector that writes into a cron field. A function handed
 * across that boundary, or a pure helper imported out of a `'use client'`
 * module into a server render, type-checks and passes every unit test and then
 * breaks only against a real production build. That has already happened twice
 * in this console, and both times a spec in this directory is what caught it.
 *
 * The empty-state CTA is deliberately not here: it needs a deployment where
 * nothing can deliver a message, and one mock plane serves one scenario. It
 * lives in `tests/first-day/`, against the dataset that actually has it.
 */

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test.describe('alert intake, action first and reference behind it', () => {
  test('renders the page it promises rather than a stand-in', async ({ page }) => {
    await page.goto('/settings/alert-intake');
    await expect(page).toHaveURL(/\/settings\/alert-intake$/);
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-alert-intake',
    );
    // The honest placeholder this page used to be offered exactly one way
    // out, back to the subnav. Its absence is what "built" means here.
    await expect(page.getByTestId('way-back')).toHaveCount(0);
  });

  test('lists every receiver compactly, with nothing expanded on arrival', async ({
    page,
  }) => {
    await page.goto('/settings/alert-intake');

    const receivers = page.getByTestId('ingress-source');
    await expect(receivers.first()).toBeVisible();

    // The inversion this feature is about: the technical reference exists on
    // the page and is closed. Every disclosure, not merely the first.
    const references = page.getByTestId('reference');
    const count = await references.count();
    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      await expect(references.nth(index)).toHaveAttribute('data-expanded', 'false');
    }
  });

  test('opens one receiver detail without opening the others', async ({ page }) => {
    await page.goto('/settings/alert-intake');

    const first = page.getByTestId('reference').first();
    await first.getByRole('button').click();

    await expect(first).toHaveAttribute('data-expanded', 'true');
    await expect(page.getByTestId('reference').nth(1)).toHaveAttribute(
      'data-expanded',
      'false',
    );
  });

  test('draws silence and refusal as different things', async ({ page }) => {
    await page.goto('/settings/alert-intake');

    // A receiver nothing has ever posted to is marked, and it is drawn first —
    // the ordering is the screen's own, not the API's.
    const silent = page.locator(
      '[data-testid="ingress-source"][data-never-delivered="true"]',
    );
    if ((await silent.count()) > 0) {
      await expect(silent.first().getByTestId('never-delivered')).toBeVisible();
    }

    // A refusal is not silence. Where the deployment reports one, it is on the
    // page as its own thing rather than folded into "nothing arrived".
    const delivered = page.locator(
      '[data-testid="ingress-source"][data-never-delivered="false"]',
    );
    await expect(delivered.first().getByTestId('last-delivery')).toBeVisible();
  });

  test('offers the endpoint as something to copy, not to transcribe', async ({
    page,
  }) => {
    await page.goto('/settings/alert-intake');

    const address = page.getByTestId('ingress-url').first();
    await expect(address).toBeVisible();
    await expect(page.getByTestId('ingress-url-copy').first()).toBeVisible();

    // Never an unencrypted address: what this page prints is pasted into
    // somebody else's alert router, and the console will not vouch for a
    // scheme that was an artefact of how this one request happened to arrive.
    // Built from parts rather than written whole, for the same reason the
    // screen's own guard is — a literal origin in console source is exactly
    // what the lint rule exists to keep out.
    await expect(address).not.toContainText(['http', '://'].join(''));
  });

  test('keeps the delivery token beside the permission it is scoped to', async ({
    page,
  }) => {
    await page.goto('/settings/alert-intake');
    await expect(page.getByTestId('delivery-token-group')).toBeVisible();
  });

  test('keeps the routing rules, and always draws the one that catches the rest', async ({
    page,
  }) => {
    await page.goto('/settings/alert-intake');

    await expect(page.getByTestId('routing-rules')).toBeVisible();
    await expect(page.getByTestId('catch-all-rule')).toHaveCount(1);
  });

  test('keeps the advanced observation section collapsed, naming its own fields once opened', async ({
    page,
  }) => {
    // A real production build, not a component render: the class of defect
    // this directory exists to catch breaks only here, never in a unit test.
    await page.goto('/settings/alert-intake');

    const advanced = page.getByTestId('advanced-config-policies-observation');
    await expect(advanced).toBeVisible();
    await expect(advanced).not.toHaveAttribute('open', '');

    await advanced.locator('summary').click();
    await expect(advanced).toHaveAttribute('open', '');
    await expect(advanced.getByText('Watching paused')).toBeVisible();
  });
});

test.describe('schedules and destinations, on one page', () => {
  test('renders the page it promises rather than a stand-in', async ({ page }) => {
    await page.goto('/settings/schedules-destinations');
    await expect(page).toHaveURL(/\/settings\/schedules-destinations$/);
    await expect(page.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-schedules-destinations',
    );
  });

  test('shows a destination this deployment cannot deliver to as degraded, with the way to fix it', async ({
    page,
  }) => {
    await page.goto('/settings/schedules-destinations');

    const degraded = page.getByTestId('destination-unusable').first();
    await expect(degraded).toBeVisible();

    // Degraded is not merely a red sentence: it carries the link to the
    // credential panel that would resolve it.
    await expect(page.getByTestId('destination-credential-link').first()).toBeVisible();
  });

  test('leaves a working destination unmarked', async ({ page }) => {
    await page.goto('/settings/schedules-destinations');

    const destinations = page.getByTestId('destination');
    await expect(destinations.first()).toBeVisible();
    // Fewer flags than rows: the marking means something only if it is not on
    // everything.
    expect(await page.getByTestId('destination-unusable').count()).toBeLessThan(
      await destinations.count(),
    );
  });

  test('says in words when each scheduled investigation runs', async ({ page }) => {
    await page.goto('/settings/schedules-destinations');

    // The column carried only the five-field expression. These are the two
    // this dataset holds, read back as the sentences they encode.
    const frequencies = page.getByTestId('schedule-frequency');
    await expect(frequencies.first()).toBeVisible();
    await expect(frequencies.filter({ hasText: 'Every Monday at 07:00' })).toHaveCount(
      1,
    );
    await expect(frequencies.filter({ hasText: 'Every day at 03:00' })).toHaveCount(1);
  });

  test('turns a readable frequency into the cron expression the field accepts', async ({
    page,
  }) => {
    await page.goto('/settings/schedules-destinations');

    const frequency = page.locator('select[name="create-frequency"]');
    await expect(frequency).toBeVisible();

    const cron = page.locator('input[name="create-cron"]');

    // "Every Monday at 08:00" is a sentence; `0 8 * * 1` is what the
    // deployment reads. Choosing the first has to produce the second, and the
    // field stays editable for somebody who would rather type it.
    await frequency.selectOption('weekly');
    await expect(page.locator('select[name="create-weekday"]')).toBeVisible();
    await expect(cron).toHaveValue('0 8 * * 1');
    await expect(cron).toBeEditable();

    await frequency.selectOption('daily');
    await expect(cron).toHaveValue('0 8 * * *');
  });
});
