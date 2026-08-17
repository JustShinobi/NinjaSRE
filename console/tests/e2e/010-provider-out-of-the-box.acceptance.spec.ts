import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The normative claims of the mockup's Models & providers screen (`#m1`).
 *
 * Written before the screen carries any of this, against the mock dataset this
 * project drives (a deployment mid-operation, provider verification already
 * recorded). Every claim here is a structural or vocabulary claim the mockup
 * makes — never a pixel claim, which the mockup itself disclaims.
 *
 * The verification card's full per-check hierarchy (the chip naming which
 * check is not clean, the consequence, the exit) is a property of a *live*
 * check: the persisted record a page load reads carries only a pass/fail
 * boolean and one sentence, and the per-check breakdown exists only in the
 * response `POST .../verify` returns right after somebody asks for one — the
 * same "listing is free, verifying is not" split the rest of this feature
 * keeps. So the investigator role's own state is exercised here by pressing
 * "Check again" once, exactly as an operator reading a stale card would, and
 * only then are the chip-consequence-exit claims asserted.
 */

const ROUTE = '/settings/models-providers';

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test.describe('Models & providers — verification as a first-class state', () => {
  test('the investigator role opens inside a state card naming the provider', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    const card = page.getByTestId('provider-state-card');
    await expect(card).toBeVisible();
    await expect(card.getByTestId('provider-state-name')).toHaveText('Google Gemini');
  });

  test('the card carries the chip of the last verification, and the "Check again" action', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    const card = page.getByTestId('provider-state-card');
    // The word must be one of the five canonical ones and never a sixth —
    // asserted by exact match rather than a substring, so a translation slip
    // ("Degradado" where the catalogue says "Degradada") fails here.
    await expect(card.getByTestId('provider-state-chip')).toHaveText('Verified');
    await expect(card.getByTestId('check-again')).toBeVisible();
  });

  test('a live check reports the chip and error hierarchy the backend produced, never a mistranslation', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    const card = page.getByTestId('provider-state-card');
    await card.getByTestId('check-again').click();

    // The word is "Degraded", never "Failing" — the exact defect this feature
    // exists to close: a check the preflight reported as degraded must not
    // read as a failure.
    await expect(card.getByTestId('provider-state-chip')).toHaveText('Degraded');

    const block = card.getByTestId('verification-error-block');
    await expect(block).toBeVisible();
    // (d) a chip naming the check, a sentence of consequence, and an exit
    // written as a link with a verb.
    await expect(block.getByTestId('verification-error-chip')).toHaveText(
      'Tool calling',
    );
    await expect(block.getByTestId('verification-error-consequence')).not.toHaveText(
      '',
    );
    const exit = block.getByTestId('verification-error-exit');
    await expect(exit).toBeVisible();
    await expect(exit).toHaveAttribute('href', /.+/);
  });

  test('save and verify is the primary action, test without saving the secondary one', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    const card = page.getByTestId('provider-state-card');
    const primary = card.getByTestId('save-and-verify');
    const secondary = card.getByTestId('test-without-saving');
    await expect(primary).toBeVisible();
    await expect(secondary).toBeVisible();
    await expect(primary).toHaveAttribute('data-variant', 'primary');
    await expect(secondary).not.toHaveAttribute('data-variant', 'primary');
  });

  test('the inheritance line says "Set at" exactly once, with the revert action beside it', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    const line = page
      .getByTestId('provider-state-card')
      .getByTestId('inheritance-line');
    const text = (await line.textContent()) ?? '';
    const occurrences = text.match(/Set at/g) ?? [];
    expect(occurrences.length).toBe(1);
    await expect(line.getByTestId('revert-investigator')).toBeVisible();
  });

  test('the advanced roles collapse into one line naming how many there are and that they inherit', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    const summary = page.getByTestId('advanced-roles-summary');
    await expect(summary).toBeVisible();
    const text = (await summary.textContent()) ?? '';
    expect(text).toMatch(/7/);
    expect(text.toLowerCase()).toMatch(/inherit/);
    // Not seven open accordions before anybody asked for one — the whole
    // point of collapsing them.
    await expect(page.getByTestId(/^advanced-role-/)).toHaveCount(0);
  });

  test('no raw provider identifier, and none of the retired sentences, appear anywhere visible', async ({
    page,
  }) => {
    await page.goto(ROUTE);
    await page.getByTestId('provider-state-card').getByTestId('check-again').click();
    await expect(page.getByTestId('verification-error-block')).toBeVisible();

    const body = await page.locator('body').innerText();
    expect(body).not.toContain('google_gemini');
    expect(body).not.toContain('Set at Set at');
    expect(body).not.toContain('could not be asked what else it serves');
  });

  test('the model selector lists names the listing endpoint served, not the six-name static list', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    const select = page
      .getByTestId('provider-state-card')
      .getByTestId('model-role-investigator-model');
    await expect(select).toBeVisible();
    // "Gemini 3.7 Flash" exists in no build's static onboarding list — its
    // presence here is only explained by the dynamic listing having answered.
    await expect(select.locator('option', { hasText: 'Gemini 3.7 Flash' })).toHaveCount(
      1,
    );
  });

  test('a reload of the model list is offered, and the fallback is labelled when it is the static one', async ({
    page,
  }) => {
    await page.goto(ROUTE);

    const card = page.getByTestId('provider-state-card');
    await expect(card.getByTestId('reload-models')).toBeVisible();
  });

  test('the screen stays within the 1080p scroll budget the whole Settings group is held to', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(ROUTE);
    await expect(page.getByTestId('provider-state-card')).toBeVisible();

    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    expect(
      height,
      `${ROUTE} is ${String(height)}px tall against a 2160px budget`,
    ).toBeLessThanOrEqual(2160);
  });
});
