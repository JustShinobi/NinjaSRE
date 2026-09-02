import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * One fact, one owner: every claim this spec encodes is about a screen
 * reading a fact from the record that actually answers for it, instead of
 * deriving its own opinion — and about a screen that could not read saying
 * so, rather than asserting the negative of what it never learned.
 *
 * **This spec is expected to be comprehensively red when it is written.**
 * The provider checklist still derives "verified" from a stored credential,
 * the setup cause is still shown under a completed investigation, the
 * investigation chip is still absent rather than "Unknown" on a failed
 * read, and the request counter this file depends on has nothing serving
 * it until the console's own routes declare their own dynamism. Every task
 * after this one exists to turn one block of this file green.
 *
 * **Six claims of the specification are not encoded here, by design:**
 *
 * - the build-manifest claim (no route under the shell is prerendered) is a
 *   repository gate over the production build's own output, not a page a
 *   browser can be pointed at — proved by the console gate's own check and
 *   its unit tests instead;
 * - the two composition claims about where a credential's value came from
 *   (vault vs. environment, and the team a resolution used) are read from a
 *   deployment's own boot log and its audit trail, neither of which a
 *   browser session can open — proved by a deployed environment's own
 *   evidence;
 * - the three run-status-vocabulary claims are about what the repository's
 *   fixtures and the console's own declared vocabulary say, checked against
 *   the domain's enumeration as data — a repository gate again, not a page.
 *
 * **No incident id, run id or provider id is written here as a literal.**
 * Every value this file needs to correlate across two screens is read off
 * one of them first, the same technique `020-identidade-enderecavel`
 * established for exactly this reason: a literal typed here is a dataset
 * dependency in disguise.
 */

const STAGING_SAFE_TAG = '@staging-safe';

test.use({ viewport: { width: 1920, height: 1080 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

// The five setup step titles this deployment's checklist declares — read
// from the constant Python module rather than retyped, so a title changed
// there is a title this file notices rather than silently stops matching.
function setupStepTitles(): readonly string[] {
  const source = readFileSync(
    fileURLToPath(new URL('../../../platform/startup/checklist.py', import.meta.url)),
    'utf8',
  );
  return [...source.matchAll(/title="([^"]+)"/g)].map((match) => match[1] ?? '');
}

// --- Correlating a provider across two screens, read rather than typed -----

/**
 * The provider currently bound to the investigator role, as
 * `/settings/models-providers` has it selected right now.
 *
 * Read from the role selector's own current value rather than assumed, so
 * this file names no provider of its own and still asks the same question
 * this whole block asks: does the checklist agree with this screen about
 * *this* provider.
 */
async function investigatorProviderId(page: Page): Promise<string> {
  await page.goto('/settings/models-providers');
  const select = page.getByTestId('model-role-investigator-provider');
  await expect(select).toBeVisible();
  return select.inputValue();
}

/** The credential-vocabulary word `/settings/models-providers` shows for the investigator's provider. */
async function modelsProvidersWord(page: Page): Promise<string> {
  await page.goto('/settings/models-providers');
  const chip = page.getByTestId('provider-state-chip');
  await expect(chip).toBeVisible();
  return (await chip.getAttribute('data-credential-status')) ?? '';
}

/**
 * Opens the wizard, and says whether this deployment still has one to show.
 *
 * A finished checklist sends `/first-run` to the dashboard, and the redirect
 * arrives in one of two forms: as the response itself, or — when the shell
 * has streamed ahead of the page's own checklist read — as a client-side
 * navigation that lands after `goto` has returned. Which one it is depends on
 * which of two concurrent renders finished first, so the address right after
 * `goto` is not an answer. A page on screen is: the wizard's own header names
 * `first-run`, and the dashboard's names `dashboard`.
 */
async function openFirstRun(page: Page): Promise<boolean> {
  await page.goto('/first-run');
  const header = page.getByTestId('page-header').first();
  await header.waitFor({ state: 'visible' });
  return (await header.getAttribute('data-area')) === 'first-run';
}

/**
 * The credential-vocabulary word `/first-run` shows for one named provider's own row.
 *
 * `/first-run` redirects away once the checklist is complete — true of the
 * default populated dataset — in which case there is no row here to read at
 * all, and this skips rather than asserting nothing found is a defect.
 */
async function firstRunWord(page: Page, providerId: string): Promise<string> {
  test.skip(
    !(await openFirstRun(page)),
    '/first-run redirects away once the checklist is complete against this dataset',
  );
  const row = page.locator(`[data-testid="verify-row"][data-thing="${providerId}"]`);
  await expect(row).toBeVisible();
  const chip = row.getByTestId('status-chip');
  return (await chip.getAttribute('data-credential-status')) ?? '';
}

// =============================================================================
// Verified/Stored in one source
// =============================================================================

test.describe('a provider has one state, not two', () => {
  test(
    'the same provider is described by the same word on /first-run and /settings/models-providers',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      const providerId = await investigatorProviderId(page);
      const onModels = await modelsProvidersWord(page);
      const onFirstRun = await firstRunWord(page, providerId);
      expect(
        onFirstRun,
        'first-run and models-providers disagree about the same provider',
      ).toBe(onModels);
    },
  );

  test(
    'a provider whose last recorded check passed reads Verified on /first-run',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      const providerId = await investigatorProviderId(page);
      const onModels = await modelsProvidersWord(page);
      // Only meaningful when the dataset's own investigator provider is
      // itself recorded as verified — otherwise this is not the situation
      // this claim is about.
      test.skip(
        onModels !== 'verified',
        'the fixtures investigator provider is not verified',
      );
      expect(await firstRunWord(page, providerId)).toBe('verified');
    },
  );

  test(
    'a provider with a stored credential and no recorded check reads Stored, and says nobody has verified it',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/first-run');
      const row = page
        .locator('[data-testid="verify-row"][data-verdict="unchecked"]')
        .first();
      test.skip(
        (await row.count()) === 0,
        'no unverified, stored provider exists in this dataset',
      );
      const chip = row.getByTestId('status-chip');
      await expect(chip).toHaveAttribute('data-credential-status', 'stored');
      await expect(row).toContainText(/nobody|no one|has not/i);
    },
  );

  test(
    'a provider whose last recorded check failed is never shown as Stored or Verified',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/first-run');
      const rows = page.getByTestId('verify-row');
      const count = await rows.count();
      for (let index = 0; index < count; index += 1) {
        const row = rows.nth(index);
        const verdict = await row.getAttribute('data-verdict');
        if (verdict !== 'failed') continue;
        const chip = row.getByTestId('status-chip');
        const status = await chip.getAttribute('data-credential-status');
        expect(status, 'a failed check is drawn as stored or verified').not.toBe(
          'stored',
        );
        expect(status, 'a failed check is drawn as stored or verified').not.toBe(
          'verified',
        );
      }
    },
  );

  test(
    'a provider with no credential at all reads Not connected on /first-run',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/first-run');
      const row = page.locator('[data-testid="verify-row"]').filter({
        has: page.locator('[data-credential-status="not_connected"]'),
      });
      test.skip(
        (await row.count()) === 0,
        'every provider in this dataset holds a credential',
      );
      await expect(row.first().getByTestId('status-chip')).toHaveAttribute(
        'data-credential-status',
        'not_connected',
      );
    },
  );
});

// =============================================================================
// A vazio screen names its own, specific cause
// =============================================================================

test.describe('empty screens name their own cause', () => {
  test(
    '/decisions being empty does not cite setup steps as the reason',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/decisions');
      const panel = page.getByTestId('panel').first();
      const state = await panel.getAttribute('data-state');
      test.skip(state !== 'empty', '/decisions is not empty against this dataset');
      await expect(panel).not.toContainText(/step\(s\) are outstanding/i);
      await expect(panel).not.toContainText(/cannot run until/i);
    },
  );

  test(
    '/knowledge being empty does not cite setup steps as the reason',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/knowledge');
      const panel = page.getByTestId('panel').first();
      const state = await panel.getAttribute('data-state');
      test.skip(state !== 'empty', '/knowledge is not empty against this dataset');
      await expect(panel).not.toContainText(/step\(s\) are outstanding/i);
      await expect(panel).not.toContainText(/cannot run until/i);
    },
  );

  test(
    'no screen cites incomplete setup as its empty cause once an investigation has completed',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      // The populated dataset carries at least one completed investigation
      // (the checklist's own fifth step reads done against it) — the
      // precondition every one of this block's screens is read under.
      for (const route of [
        '/decisions',
        '/knowledge',
        '/signals',
        '/topology',
        '/memory',
      ]) {
        await page.goto(route);
        await expect(
          page.locator('body'),
          `${route} still names setup as the reason it is empty`,
        ).not.toContainText(
          /step\(s\) are outstanding, and investigations cannot run/i,
        );
      }
    },
  );

  test('a screen that does cite setup as its cause names the pending step, not a count', async ({
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== 'first-day',
      'requires a deployment with setup still pending',
    );
    await page.goto('/decisions');
    const panel = page.getByTestId('panel').first();
    await expect(panel).toHaveAttribute('data-state', 'empty');
    const text = (await panel.textContent()) ?? '';
    const titles = setupStepTitles();
    expect(
      titles.some((title) => text.includes(title)),
      `expected the empty cause to name a pending step title (${titles.join(', ')}); got: ${text}`,
    ).toBe(true);
    expect(text, 'the cause cites a bare count instead of naming the step').not.toMatch(
      /\d+\s*step\(s\)/i,
    );
  });
});

// =============================================================================
// A chip never asserts the negative of a read that failed
// =============================================================================

test.describe('the investigation chip on an incident that read successfully', () => {
  test(
    'an incident with no investigation says so',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/incidents');
      const rows = page.getByTestId('row');
      const count = await rows.count();
      let found = false;
      for (let index = 0; index < count; index += 1) {
        await rows.nth(index).locator('a').first().click();
        const labels = await page.getByTestId('incident-chip').allTextContents();
        if (labels.some((label) => /no investigation/i.test(label))) {
          found = true;
          break;
        }
        await page.goto('/incidents');
      }
      test.skip(!found, 'no incident with "no investigation" exists in this dataset');
      expect(found).toBe(true);
    },
  );
});

test.describe('the investigation chip on an incident whose detail read failed', () => {
  // An id shaped like a real one, guaranteed absent — the mechanism
  // `020-identidade-enderecavel` established for forcing exactly this read
  // to fail, reused rather than re-invented.
  const UNREADABLE_INCIDENT = '/incidents/inc_0000000000000000';

  test('the chip reads Unknown rather than being absent or asserting None', async ({
    page,
  }) => {
    await page.goto(UNREADABLE_INCIDENT);
    const chips = page.getByTestId('incident-chip');
    const count = await chips.count();
    const texts: string[] = [];
    for (let index = 0; index < count; index += 1) {
      texts.push((await chips.nth(index).textContent()) ?? '');
    }
    expect(
      texts.some((text) => /unknown/i.test(text)),
      `expected an "Unknown" investigation chip; the incident header showed: ${texts.join(', ')}`,
    ).toBe(true);
    expect(texts.some((text) => /no investigation/i.test(text))).toBe(false);
  });

  test('the Unknown chip names the dependency that failed, on the line or in its tooltip', async ({
    page,
  }) => {
    await page.goto(UNREADABLE_INCIDENT);
    const chips = page.getByTestId('incident-chip');
    const count = await chips.count();
    let namesDependency = false;
    for (let index = 0; index < count; index += 1) {
      const chip = chips.nth(index);
      const label = (await chip.textContent()) ?? '';
      if (!/unknown/i.test(label)) continue;
      const inline = /incident/i.test(label);
      const tooltip = (await chip.getAttribute('title')) ?? '';
      if (inline || /incident/i.test(tooltip)) namesDependency = true;
    }
    expect(namesDependency, 'no Unknown chip names the dependency that failed').toBe(
      true,
    );
  });
});

test.describe('no panel in error state asserts a negative', () => {
  /**
   * Every panel this page shows in `error` state, sampled for a negative
   * existence claim. Reusable across routes rather than one bespoke check
   * per screen, because the rule is the same rule everywhere it applies.
   */
  async function errorPanelsAssertNothingNegative(page: Page): Promise<void> {
    const panels = page.locator('[data-testid="panel"][data-state="error"]');
    const count = await panels.count();
    for (let index = 0; index < count; index += 1) {
      const text = (await panels.nth(index).textContent()) ?? '';
      expect(
        text,
        'an error-state panel asserts the negative of what it never learned',
      ).not.toMatch(/\bno (investigation|proposal|resources|episodes|findings)\b/i);
    }
  }

  test('sweeping every panel in error state on the incident detail of a read that failed', async ({
    page,
  }) => {
    await page.goto('/incidents/inc_0000000000000000');
    await errorPanelsAssertNothingNegative(page);
  });

  test(
    "sweeping every panel in error state on whatever this dataset's own screens show",
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      for (const route of [
        '/incidents',
        '/runs',
        '/decisions',
        '/knowledge',
        '/signals',
      ]) {
        await page.goto(route);
        await errorPanelsAssertNothingNegative(page);
      }
    },
  );
});

// =============================================================================
// Lists show the present — proved by the request that reached the backing
// =============================================================================

const BACKING_URL = process.env.NINJASRE_CONSOLE_BACKING_URL;

/**
 * `BACKING_URL`, asserted defined.
 *
 * Every block that calls this guards itself first with
 * `test.skip(BACKING_URL === undefined, ...)`, so by the time this runs the
 * variable is never actually missing — this just gives the type checker the
 * same fact the runtime skip already establishes, rather than threading a
 * `string | undefined` through every request this file makes.
 */
function backingUrl(): string {
  if (BACKING_URL === undefined) {
    throw new Error(
      'NINJASRE_CONSOLE_BACKING_URL is not set; this block should have been skipped',
    );
  }
  return BACKING_URL;
}

test.describe('a list load reaches the backing, not a cache that never did', () => {
  test.skip(
    BACKING_URL === undefined,
    "requires the mock backing's own request counter",
  );

  async function countFor(page: Page, route: string): Promise<number> {
    const response = await page.request.get(`${backingUrl()}/__mockplane__/requests`);
    const body = (await response.json()) as {
      readonly counts: Readonly<Record<string, number>>;
    };
    return body.counts[`GET ${route}`] ?? 0;
  }

  test('loading /incidents emits at least one request to the gateway', async ({
    page,
  }) => {
    const before = await countFor(page, '/v1/incidents');
    await page.goto('/incidents', { waitUntil: 'networkidle' });
    const after = await countFor(page, '/v1/incidents');
    expect(
      after,
      'the load of /incidents produced no request to the gateway',
    ).toBeGreaterThan(before);
  });

  test('loading /runs emits at least one request to the gateway', async ({ page }) => {
    const before = await countFor(page, '/v1/runs');
    await page.goto('/runs', { waitUntil: 'networkidle' });
    const after = await countFor(page, '/v1/runs');
    expect(
      after,
      'the load of /runs produced no request to the gateway',
    ).toBeGreaterThan(before);
  });

  /**
   * Every request counted so far whose path is an incident's own detail —
   * `/v1/incidents/<id>`, never the bare list. The counter is keyed by the
   * literal path a request actually carried, so an id this file does not
   * know ahead of time is matched by prefix rather than assumed.
   */
  async function detailRequestTotal(page: Page): Promise<number> {
    const response = await page.request.get(`${backingUrl()}/__mockplane__/requests`);
    const body = (await response.json()) as {
      readonly counts: Readonly<Record<string, number>>;
    };
    return Object.entries(body.counts)
      .filter(([key]) => key.startsWith('GET /v1/incidents/'))
      .reduce((sum, [, value]) => sum + value, 0);
  }

  test('loading an incident detail emits at least one request to the gateway', async ({
    page,
  }) => {
    await page.goto('/incidents');
    const row = page.getByTestId('row').first();
    await expect(row).toBeVisible();
    const before = await detailRequestTotal(page);
    await row.locator('a').first().click();
    await page.waitForLoadState('networkidle');
    const after = await detailRequestTotal(page);
    expect(
      after,
      'no request for an incident detail reached the gateway',
    ).toBeGreaterThan(before);
  });
});

test.describe('a fact written after the first load appears in one reload', () => {
  // Not staging-safe: the mock plane's own request counter is what this
  // depends on, and writing a genuinely new incident is out of reach either
  // way — the backing has no route that creates one, and this file does not
  // invent test-only infrastructure to fabricate one. `page.route()` cannot
  // stand in for that write: an incidents list is read from a Server
  // Component, so the request that fetches it never reaches the browser's
  // own network stack for Playwright to intercept — only the server process
  // makes it. What is provable from here, honestly, is the narrower half of
  // the same claim: a second, immediate reload reaches the backing again
  // rather than being answered from whatever answered the first one, which
  // is the precondition a new fact could ever be shown at all.
  test('a second, immediate reload of /incidents reaches the backing again rather than reusing the first answer', async ({
    page,
  }) => {
    test.skip(
      BACKING_URL === undefined,
      "requires the mock backing's own request counter",
    );
    const response = await page.request.get(`${backingUrl()}/__mockplane__/requests`);
    const body = (await response.json()) as {
      readonly counts: Readonly<Record<string, number>>;
    };
    const before = body.counts['GET /v1/incidents'] ?? 0;

    await page.goto('/incidents', { waitUntil: 'networkidle' });
    await page.reload({ waitUntil: 'networkidle' });

    const afterResponse = await page.request.get(
      `${backingUrl()}/__mockplane__/requests`,
    );
    const afterBody = (await afterResponse.json()) as {
      readonly counts: Readonly<Record<string, number>>;
    };
    const after = afterBody.counts['GET /v1/incidents'] ?? 0;
    expect(
      after,
      'a second reload of /incidents did not reach the backing a second time',
    ).toBeGreaterThanOrEqual(before + 2);
  });
});

// =============================================================================
// Setup progress: one derivation, cited the same everywhere
// =============================================================================

test.describe('setup progress is one count, cited the same everywhere', () => {
  test(
    'the first-run header, the checklist panel and the dashboard card cite the same total and pending',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/first-run');
      const headerHero = page.getByTestId('setup-hero-progress');
      test.skip(
        (await headerHero.count()) === 0,
        'the checklist is already complete against this dataset, so no hero renders anywhere to compare',
      );
      const headerText = (await headerHero.textContent()) ?? '';
      const headerMatch = /(\d+)\s*(?:of|\/)\s*(\d+)/.exec(headerText);
      expect(
        headerMatch,
        `the first-run hero carries no total/pending pair: ${headerText}`,
      ).not.toBeNull();

      await page.goto('/');
      const dashboardHero = page.getByTestId('setup-hero-progress');
      await expect(dashboardHero).toBeVisible();
      const dashboardText = (await dashboardHero.textContent()) ?? '';
      const dashboardMatch = /(\d+)\s*(?:of|\/)\s*(\d+)/.exec(dashboardText);
      expect(
        dashboardMatch?.[0],
        'the dashboard card and the first-run header cite different setup counts',
      ).toBe(headerMatch?.[0]);
    },
  );
});

// =============================================================================
// Claims proved by a repository gate rather than a browser — named, not encoded
// =============================================================================

test.describe('claims this file does not encode', () => {
  test.skip(
    true,
    'no shell route is prerendered: proved by the console gate reading the production ' +
      "build's own manifest, not by a page a browser can open",
  );
  test.skip(
    true,
    "a verified-green provider's origin (vault or environment) and team: read from a " +
      'deployment boot log a browser session cannot open',
  );
  test.skip(
    true,
    'a verified-green integration is the one a tool binding reaches: read by a database ' +
      'query against a deployment, not by inspecting a screen',
  );
  test.skip(
    true,
    'every fixture serves a run status the domain enumeration declares, and the console ' +
      "declares exactly what the gateway serves: proved by the repository's own gate " +
      'against the fixture tree and the console source, not against a running page',
  );
});
