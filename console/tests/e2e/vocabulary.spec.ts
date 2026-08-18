import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * One vocabulary for a credential's own state, everywhere it is shown.
 *
 * Before this feature the same fact — a stored, unchecked credential; a check
 * that passed; a check that failed — read as "stored, unchecked", "it
 * answered", "HEALTHY", "Verified — the last check passed" and "UNCONFIGURED"
 * depending on which screen happened to be open. An operator had to
 * retranslate the product on every page, which is the cheapest defect in the
 * "confusing" reports to fix and the one this sweep exists to keep fixed.
 *
 * Multi-word phrases are checked against the whole page: nothing legitimate on
 * these screens says "it answered" or "Nobody has checked" for an unrelated
 * reason, so a page-wide match is never a false positive. The single, bare
 * words — "HEALTHY", "UNCONFIGURED" — are checked only inside the regions that
 * actually carry a credential's state everywhere else, because the same words
 * can describe a resource's own health on a screen this sweep does not cover.
 * Administration used to be the one page that needed that same narrowing — a
 * person's own account state and a token group's own state both rendered the
 * literal word "HEALTHY" there — but both are now resolved by a dedicated
 * chip (Active/Suspended, In use/Never used) before they ever reach the page,
 * so the bare words are checked there page-wide, exactly like the phrases
 * above: nothing legitimate on Administration has a reason to print any of
 * them any more, and a page-wide match on that page is never a false
 * positive either.
 */

const FORBIDDEN_PHRASES = [
  'it answered',
  'It answered',
  'stored, unchecked',
  'Nobody has checked',
] as const;

const FORBIDDEN_WORDS = ['HEALTHY', 'UNCONFIGURED', 'DEGRADED'] as const;

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test('the integrations catalogue never shows a forbidden phrase', async ({ page }) => {
  await page.goto('/integrations');
  const body = await page.locator('body').innerText();

  for (const phrase of FORBIDDEN_PHRASES) {
    expect(body, `"${phrase}" is not the canonical vocabulary`).not.toContain(phrase);
  }
});

test('every catalogue card shows one of the five canonical words, never the raw one', async ({
  page,
}) => {
  await page.goto('/integrations');
  // Connected, Suggested and the compact grid are the three shapes a card
  // takes now; none of them may show a raw backend word anywhere in its text.
  const cards = page.locator(
    '[data-testid="connected-integration"], [data-testid="suggested-integration"], [data-testid="catalogue-item"]',
  );
  const count = await cards.count();
  expect(count, 'no integration card rendered to check').toBeGreaterThan(0);

  for (let index = 0; index < count; index += 1) {
    const card = cards.nth(index);
    const text = await card.innerText();
    for (const word of FORBIDDEN_WORDS) {
      expect(text, `card ${String(index)} shows the raw backend word`).not.toContain(
        word,
      );
    }
  }
});

test('every connected integration carries the chip, never a second line repeating it', async ({
  page,
}) => {
  await page.goto('/integrations');
  const connected = page.getByTestId('connected-integration');
  const count = await connected.count();
  expect(count, 'no connected integration rendered to check').toBeGreaterThan(0);

  for (let index = 0; index < count; index += 1) {
    // Every card carries the chip's own machine-readable state, which is one
    // of the five canonical keys — never the raw `health` word verbatim, and
    // never a second line saying the same thing in different words.
    await expect(connected.nth(index).locator('[data-credential-status]')).toHaveCount(
      1,
    );
  }
});

test('the guided first run never shows a forbidden phrase', async ({ page }) => {
  await page.goto('/first-run?step=verify');
  const body = await page.locator('body').innerText();

  for (const phrase of FORBIDDEN_PHRASES) {
    expect(body, `"${phrase}" is not the canonical vocabulary`).not.toContain(phrase);
  }
});

test('what the first run has established shows canonical chips, not raw words', async ({
  page,
}) => {
  await page.goto('/first-run?step=verify');
  const established = page.getByTestId('established');

  if ((await established.count()) === 0) {
    // Nothing configured yet on this deployment is a legitimate state — the
    // panel's own empty state covers it, and there is nothing here to sweep.
    return;
  }
  const text = await established.innerText();
  for (const word of FORBIDDEN_WORDS) {
    expect(text).not.toContain(word);
  }
});

test('the administration area never shows a forbidden phrase or word', async ({
  page,
}) => {
  await page.goto('/administration');
  const body = await page.locator('body').innerText();

  for (const phrase of FORBIDDEN_PHRASES) {
    expect(body, `"${phrase}" is not the canonical vocabulary`).not.toContain(phrase);
  }
  // Page-wide, not scoped to a region: a principal's own account state and a
  // token group's own state are the only things on this page that ever spoke
  // in this vocabulary, and both are resolved by a dedicated chip before
  // they reach here — see PrincipalKindChip/AccountStateChip/TokenGroupStateChip
  // in components/status.tsx. Nothing legitimate left on this page has a
  // reason to print the raw word.
  for (const word of FORBIDDEN_WORDS) {
    expect(body, `"${word}" is not the canonical vocabulary`).not.toContain(word);
  }
});

/**
 * A raw catalogue id — `google_gemini`, `openobserve_cloud` — in the position a
 * person reads as a title, rather than the display name every profile now
 * declares. Snake case is the tell: nothing this console titles with on
 * purpose is spelled with an underscore, so any match here is the id
 * standing in for a name.
 */
const SNAKE_CASE_ID = /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/;

test('no integration card titles itself with a raw snake_case id', async ({ page }) => {
  await page.goto('/integrations');
  const titles = page.locator(
    '[data-testid="connected-integration"] .text-strong, [data-testid="suggested-integration"] .text-strong, [data-testid="catalogue-item"] .text-strong',
  );
  const count = await titles.count();
  expect(count, 'no integration card rendered to check').toBeGreaterThan(0);

  for (let index = 0; index < count; index += 1) {
    const text = (await titles.nth(index).innerText()).trim();
    expect(
      SNAKE_CASE_ID.test(text),
      `card ${String(index)} titles itself "${text}", a raw id rather than a display name`,
    ).toBe(false);
  }
});
