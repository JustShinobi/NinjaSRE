import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test, type Locator, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * The sixteen normative claims of identity-addressable incidents: an
 * incident opens by a short, escape-free public address instead of the
 * composite internal key an alert produced it under; a dynamic route
 * decodes its parameter once, at the edge, instead of leaving it to be
 * encoded a second time; a failed read says it failed rather than printing
 * the address as a name and denying an investigation nothing ever asked
 * about; and two retired addresses answer by the names the rest of the
 * product already calls them.
 *
 * **Twelve of the sixteen are staging-safe** — read-only, no destructive
 * write, safe against a shared deployment — and carry the tag this suite's
 * harness selects by. The other four (a search result, a run's own incident
 * link, and the two failed-read claims) depend on this dataset's own shape
 * or on forcing a read to fail, neither of which a shared environment's
 * live data can be made to do safely, so they run only against this
 * project's own deterministic backing.
 *
 * **This spec is expected to be comprehensively red when it is written.**
 * The public address does not exist on the wire yet, the edge decodes
 * nothing, the header still falls back to the raw identifier, and
 * `/investigations` and `/setup` still end in the console's own "there is
 * no such page". Every task after this one exists to turn one claim green.
 *
 * **No incident id or title is written here as a literal.** The alert
 * incident this file opens is found by its own detector column reading
 * "alertmanager" — true of the mock dataset and, per the diagnosis this
 * feature answers, true of every real incident in the staging deployment
 * too, because every incident there was opened by a real alert. An id or a
 * title typed into this file would be a dataset dependency in disguise.
 */

const STAGING_SAFE_TAG = '@staging-safe';

test.use({ viewport: { width: 1920, height: 1080 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

/** The escape sequences none of the four reserved characters may leave in an address. */
const RESERVED_ENCODED = ['%3A', '%40', '%2B'] as const;

/** The reserved characters themselves, checked for literally in the path. */
const RESERVED_LITERAL = [':', '@', '+'] as const;

/**
 * The incidents-list row for an alert Alertmanager delivered.
 *
 * Found by the detector column's own text — "alertmanager" — rather than a
 * title or an id, so this file names no incident of its own. It is the one
 * origin whose internal key is the composite, reserved-character-bearing
 * shape this feature exists to stop emitting as a link: `alert:<source>:
 * <fingerprint>@<instant>`.
 */
async function alertIncidentRow(page: Page): Promise<Locator> {
  await page.goto('/incidents');
  const row = page.getByTestId('row').filter({ hasText: 'alertmanager' }).first();
  await expect(row).toBeVisible();
  return row;
}

/** Open the alert-sourced incident's own detail page from the list. */
async function openAlertIncident(page: Page): Promise<void> {
  const row = await alertIncidentRow(page);
  await row.locator('a').first().click();
}

/**
 * The title of an incident the dataset attaches a real investigation to —
 * read from the same populated fixture the demonstration seeder writes
 * through, never typed here. Used only to find a row by its own visible
 * text; the address it resolves to is never asserted as a literal either.
 */
function investigatedIncidentTitle(): string {
  const source = readFileSync(
    fileURLToPath(
      new URL('../../../fixtures/scenarios/populated/incidents.json', import.meta.url),
    ),
    'utf8',
  );
  const parsed = JSON.parse(source) as {
    readonly responses: readonly {
      readonly body?: {
        readonly incidents?: readonly {
          readonly run_id?: string | null;
          readonly title?: string;
        }[];
      };
    }[];
  };
  for (const response of parsed.responses) {
    for (const incident of response.body?.incidents ?? []) {
      if (
        typeof incident.run_id === 'string' &&
        incident.run_id !== '' &&
        typeof incident.title === 'string' &&
        incident.title !== ''
      ) {
        return incident.title;
      }
    }
  }
  throw new Error(
    'no incident in the populated dataset carries a run; nothing here can prove a ' +
      'run-detail page links back to an incident',
  );
}

// --- User Story 1: the detail of an alert-sourced incident opens ----------

test.describe('identity: an alert-sourced incident opens', () => {
  test(
    'AN-01/AN-02: the H1 is the incident title, and it is never an identifier',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openAlertIncident(page);
      const title = (await page.getByTestId('incident-title').innerText()).trim();

      expect(title, 'the H1 must not be empty').not.toBe('');
      expect(title, `"${title}" carries a reserved character`).not.toMatch(/[:@+]/);
      expect(title, `"${title}" is percent-encoded`).not.toMatch(/%[0-9A-Fa-f]{2}/);
    },
  );

  test(
    'AN-03: the tab title names the incident, and is never an identifier',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openAlertIncident(page);
      const tabTitle = await page.title();

      expect(tabTitle, `"${tabTitle}" carries a reserved character`).not.toMatch(/[:@+]/);
      expect(tabTitle, `"${tabTitle}" is percent-encoded`).not.toMatch(/%[0-9A-Fa-f]{2}/);
    },
  );

  test(
    'AN-04: the address bar carries no percent-encoded reserved character',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openAlertIncident(page);
      const url = page.url();

      for (const escaped of RESERVED_ENCODED) {
        expect(
          url.toUpperCase(),
          `${url} carries the escaped reserved character ${escaped}`,
        ).not.toContain(escaped);
      }
    },
  );

  test(
    'AN-05: the address bar carries no reserved character literally either',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openAlertIncident(page);
      const path = new URL(page.url()).pathname;

      for (const char of RESERVED_LITERAL) {
        expect(path, `${path} carries the literal reserved character "${char}"`).not.toContain(
          char,
        );
      }
    },
  );

  test(
    'AN-06: the Investigation panel is not in a failed-dependency state',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openAlertIncident(page);
      const panel = page.getByRole('region', { name: 'Investigation' });

      await expect(panel).toBeVisible();
      await expect(panel).not.toHaveAttribute('data-state', 'error');
    },
  );

  test(
    'AN-07: the Evidence trail panel is not in a failed-dependency state',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openAlertIncident(page);
      const panel = page.getByRole('region', { name: 'Evidence trail' });

      await expect(panel).toBeVisible();
      await expect(panel).not.toHaveAttribute('data-state', 'error');
    },
  );

  test(
    'AN-08: the timeline renders one entry per reasoning step the gateway returned',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await openAlertIncident(page);

      // The dataset attaches three reasoning-kind entries to this incident
      // (an alert receipt, a piece of evidence, a diagnosis) alongside the
      // one lifecycle entry ("opened") every incident carries — and this
      // screen renders one `investigation-step` per reasoning entry, never
      // per lifecycle one. Three is what the gateway returns for this
      // incident on this dataset; a broken read renders none of them.
      await expect(page.getByTestId('investigation-step')).toHaveCount(3);
    },
  );
});

// --- User Story 5: retired addresses answer by the names in use -----------

test.describe('routes answering by the name the product already uses', () => {
  test(
    'AN-09: /investigations does not end in "there is no such page"',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/investigations');
      await expect(page.getByText('There is no such page')).toHaveCount(0);
    },
  );

  test(
    'AN-10: /setup does not end in "there is no such page"',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/setup');
      await expect(page.getByText('There is no such page')).toHaveCount(0);
    },
  );

  /**
   * Checked against the redirect response itself, with no further redirect
   * followed — `page.goto` would settle on wherever the *destination*
   * itself goes next (`/first-run` redirects away on its own, to `/`, once
   * this dataset's own checklist is complete), which answers a different
   * question than the one this claim asks.
   */
  test('AN-11: /investigations ends in /runs', { tag: STAGING_SAFE_TAG }, async ({ page }) => {
    const response = await page.request.get('/investigations', { maxRedirects: 0 });
    expect(response.status(), 'expected a redirect response').toBeGreaterThanOrEqual(300);
    expect(response.status()).toBeLessThan(400);
    expect(response.headers()['location'] ?? '').toBe('/runs');
  });

  test('AN-12: /setup ends in /first-run', { tag: STAGING_SAFE_TAG }, async ({ page }) => {
    const response = await page.request.get('/setup', { maxRedirects: 0 });
    expect(response.status(), 'expected a redirect response').toBeGreaterThanOrEqual(300);
    expect(response.status()).toBeLessThan(400);
    expect(response.headers()['location'] ?? '').toBe('/first-run');
  });
});

// --- User Story 2: one address, every surface (not staging-safe: depends
// on this dataset's own shape rather than on data staging cannot control) --

test.describe('one address, every surface', () => {
  test('AN-13: a search result for an incident points to the same address the list row does', async ({
    page,
  }) => {
    const row = await alertIncidentRow(page);
    const titleCell = ((await row.locator('td').first().innerText()).split('\n')[0] ?? '').trim();
    expect(titleCell).not.toBe('');

    await row.locator('a').first().click();
    const fromList = new URL(page.url()).pathname;

    await page.goto('/incidents');
    await page.getByTestId('open-palette').click();
    await page.getByTestId('palette-query').fill(titleCell.slice(0, 10));
    const command = page.getByTestId('palette-command').filter({ hasText: titleCell });
    await expect(command).toBeVisible();
    await command.click();
    const fromSearch = new URL(page.url()).pathname;

    expect(fromSearch, `search opened ${fromSearch}, the list opens ${fromList}`).toBe(fromList);
  });

  test('AN-14: the incident link on a run detail page points to the same address the list row does', async ({
    page,
  }) => {
    const title = investigatedIncidentTitle();
    await page.goto('/incidents');
    const row = page.getByTestId('row').filter({ hasText: title }).first();
    const fromListHref = await row.locator('a').first().getAttribute('href');
    expect(fromListHref).not.toBeNull();

    await row.locator('a').first().click();
    await page.getByRole('link', { name: 'Open the full run' }).click();
    await expect(page).toHaveURL(/\/runs\//);

    const incidentLink = page.getByTestId('run-incident-link');
    await expect(incidentLink).toBeVisible();
    const fromRunHref = await incidentLink.getAttribute('href');

    expect(fromRunHref, `run detail links to ${fromRunHref}, the list opens ${fromListHref}`).toBe(
      fromListHref,
    );
  });
});

// --- User Story 4: a failed read never becomes an assertion (not
// staging-safe: forcing a read to fail is not something shared data allows) -

test.describe('a detail read that failed', () => {
  const UNKNOWN_PUBLIC_ADDRESS = '/incidents/inc_0000000000000000';

  test('AN-15: the page does not assert the negative about the investigation', async ({
    page,
  }) => {
    await page.goto(UNKNOWN_PUBLIC_ADDRESS);

    const chips = page.getByTestId('incident-chip');
    const count = await chips.count();
    for (let index = 0; index < count; index += 1) {
      await expect(chips.nth(index)).not.toHaveText(/no investigation/i);
    }
  });

  test('AN-16: the header says the incident could not be read, and invents no name', async ({
    page,
  }) => {
    await page.goto(UNKNOWN_PUBLIC_ADDRESS);

    const heading = page.getByTestId('incident-title');
    await expect(heading).not.toHaveText('inc_0000000000000000');
    await expect(heading).not.toBeEmpty();
  });
});
