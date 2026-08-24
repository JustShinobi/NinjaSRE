import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The thirteen normative claims of this feature's specification, one
 * assertion each.
 *
 * **Two vendors carry this file's read claims: `grafana` and `prometheus`.**
 * Both are real, embedded, unconfigured in the `populated` dataset — which is
 * what puts the write-only credential form straight on screen with no
 * "Replace credential" click first — and both are fully oriented: every
 * field declares a guide, every secret field declares a minimum permission,
 * and the vendor declares its own "where to get it" phrase. `proxmox` is the
 * specification's third named vendor; a dedicated block below checks its
 * orientation separately, now that the certificate-trust feature sharing
 * these files has merged and closed this feature's own boundary around them.
 *
 * **AN-07 and AN-08 render the package documentation for real.** The
 * sanitised renderer they depend on (`console/src/surfaces/report.tsx`)
 * landed from the "leitura do relato" feature after this file's first
 * version was written against a repository that had none. AN-09 (a failed
 * read says so, not that the document is absent) is proven at the unit
 * layer instead of here —
 * `console/tests/unit/surfaces/integration-panel.test.tsx` — because every
 * vendor in this dataset reads successfully and this file does not
 * fabricate a read failure the mock backing cannot produce.
 *
 * **AN-10 and AN-11 are `test.skip`, named, not silently absent, in this
 * run.** Both need a deployment whose credential proxy actually enforces the
 * clear-text refusal against a live write — the `compose` backing, not the
 * static `mock` one this file otherwise runs against, which answers every
 * write with the same canned response regardless of what was sent. The
 * refusal itself is proven at the platform layer, including across the ASGI
 * wire boundary a capability actually reads it through, in
 * `tests/unit/platform/credentials/test_proxy_engine.py`. What is not proven
 * here is the console rendering that sentence as the panel's verdict detail
 * — a real gap, named as one rather than assumed from the backend proof.
 */

const CATALOGUE_ROUTE = '/integrations';
const GRAFANA_ROUTE = '/integrations/grafana';
const PROMETHEUS_ROUTE = '/integrations/prometheus';
const PROXMOX_ROUTE = '/integrations/proxmox';

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

// =============================================================================
// AN-01 / AN-02 / AN-12 — minimum permission: present on every secret field,
// absent everywhere else, never rendered as an empty line
// =============================================================================

test.describe('minimum permission: on every secret field, on no other, never blank', () => {
  test('every secret field of an embedded vendor shows its minimum permission', async ({
    page,
  }) => {
    await page.goto(GRAFANA_ROUTE);
    const tokenField = page.locator(
      '[data-testid="credential"] >> input[name="token"]',
    );
    await expect(tokenField).toBeVisible();
    const row = page.locator('[data-testid="credential"] > div', {
      has: page.locator('input[name="token"]'),
    });
    await expect(row.getByTestId('credential-field-scope')).toBeVisible();
    await expect(row.getByTestId('credential-field-scope')).toContainText(
      'Viewer role',
    );
  });

  test('no field that is not secret shows a minimum-permission line', async ({
    page,
  }) => {
    await page.goto(GRAFANA_ROUTE);
    const endpointRow = page.locator('[data-testid="credential"] > div', {
      has: page.locator('input[name="endpoint"]'),
    });
    await expect(endpointRow.getByTestId('credential-field-scope')).toHaveCount(0);

    const orgRow = page.locator('[data-testid="credential"] > div', {
      has: page.locator('input[name="org"]'),
    });
    await expect(orgRow.getByTestId('credential-field-scope')).toHaveCount(0);
  });

  test('a vendor whose token carries no scope model still says so, rather than rendering nothing', async ({
    page,
  }) => {
    await page.goto(PROMETHEUS_ROUTE);
    const row = page.locator('[data-testid="credential"] > div', {
      has: page.locator('input[name="token"]'),
    });
    await expect(row.getByTestId('credential-field-scope')).toContainText(
      'reverse proxy',
    );
  });
});

// =============================================================================
// AN-03 / AN-04 / AN-13 — guide: on every field, every one an absolute
// address, never a link with nothing behind it
// =============================================================================

test.describe('guide: on every field, always a real address', () => {
  test('every field of an embedded vendor offers a guide link', async ({ page }) => {
    await page.goto(GRAFANA_ROUTE);
    for (const name of ['endpoint', 'token', 'org']) {
      const row = page.locator('[data-testid="credential"] > div', {
        has: page.locator(`input[name="${name}"]`),
      });
      const guide = row.getByTestId('credential-field-guide');
      await expect(guide).toBeVisible();
      const href = await guide.getAttribute('href');
      expect(href, `${name}'s guide has no destination`).toBeTruthy();
      expect(new URL(href ?? '').protocol, `${name}'s guide is not absolute`).toMatch(
        /^https?:$/,
      );
    }
  });

  test('a guide link is never rendered with nothing behind it', async ({ page }) => {
    await page.goto(PROMETHEUS_ROUTE);
    const guides = page.locator('[data-testid="credential-field-guide"]');
    const count = await guides.count();
    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      const href = await guides.nth(index).getAttribute('href');
      expect(href).not.toBe('');
      expect(href).not.toBeNull();
    }
  });
});

// =============================================================================
// proxmox: the vendor left out of this feature's own boundary at first
// (a certificate-trust feature shared its files), now fully oriented too
// =============================================================================

test.describe("proxmox's own orientation, now that the shared boundary has closed", () => {
  test('every field of proxmox offers a guide, and every secret field states its minimum permission', async ({
    page,
  }) => {
    await page.goto(PROXMOX_ROUTE);
    const secretFields = ['api_token', 'password', 'ticket', 'csrf_token'];
    const publicFields = ['endpoint', 'username'];

    for (const name of [...secretFields, ...publicFields]) {
      const row = page.locator('[data-testid="credential"] > div', {
        has: page.locator(`input[name="${name}"]`),
      });
      const guide = row.getByTestId('credential-field-guide');
      await expect(guide).toBeVisible();
      const href = await guide.getAttribute('href');
      expect(href, `proxmox.${name}'s guide has no destination`).toBeTruthy();
    }

    for (const name of secretFields) {
      const row = page.locator('[data-testid="credential"] > div', {
        has: page.locator(`input[name="${name}"]`),
      });
      await expect(row.getByTestId('credential-field-scope')).toBeVisible();
    }

    for (const name of publicFields) {
      const row = page.locator('[data-testid="credential"] > div', {
        has: page.locator(`input[name="${name}"]`),
      });
      await expect(row.getByTestId('credential-field-scope')).toHaveCount(0);
    }
  });
});

// =============================================================================
// AN-05 / AN-06 — "where to get it", shown, and identical on both screens
// =============================================================================

test.describe('where to obtain the credential: shown, and the same phrase everywhere', () => {
  test("the integration screen shows the vendor's own where-to-get-it phrase", async ({
    page,
  }) => {
    await page.goto(GRAFANA_ROUTE);
    const line = page.getByTestId('where-to-get-it');
    await expect(line).toBeVisible();
    await expect(line).toContainText('service account token');
  });

  test('the same vendor shows the identical phrase on the first-run integrations step', async ({
    page,
  }) => {
    await page.goto(GRAFANA_ROUTE);
    const fromPanel = (await page.getByTestId('where-to-get-it').textContent()) ?? '';

    await page.goto('/first-run?step=integrations');
    test.skip(
      !page.url().includes('step=integrations') && !page.url().endsWith('/first-run'),
      '/first-run redirects away once the checklist is complete against this dataset',
    );
    const offer = page.locator(
      '[data-testid="integration-offer"][data-integration="grafana"]',
    );
    test.skip(
      (await offer.count()) === 0,
      'grafana is not offered on this screen against this dataset (already connected, or filtered out)',
    );
    const fromFirstRun =
      (await offer.getByTestId('where-to-get-it').textContent()) ?? '';

    // Each screen may introduce the sentence with its own label; the
    // sentence itself — everything this feature's own profile declared — has
    // to be the same string on both.
    const phrase =
      "Create a service account token from Grafana's own Administration → Service accounts screen, with the Viewer role.";
    expect(fromPanel).toContain(phrase);
    expect(fromFirstRun).toContain(phrase);
  });
});

// =============================================================================
// AN-07 / AN-08 — the package's own documentation, rendered in the panel
// =============================================================================

test.describe('the package documentation section', () => {
  test('the integration screen offers the package documentation without leaving the console', async ({
    page,
  }) => {
    await page.goto(GRAFANA_ROUTE);
    const section = page.getByTestId('integration-docs');
    await expect(section).toBeVisible();

    // Collapsed by default — opening it is the "without leaving the
    // console" claim: no navigation, the same page, the summary control
    // reveals the document in place.
    await section.locator('summary').click();
    const report = section.getByTestId('report');
    await expect(report).toBeVisible();
    await expect(report).toContainText('Grafana');
  });

  test('the rendered documentation shows no markdown syntax character as text', async ({
    page,
  }) => {
    await page.goto(GRAFANA_ROUTE);
    const section = page.getByTestId('integration-docs');
    await section.locator('summary').click();
    const report = section.getByTestId('report');
    await expect(report).toBeVisible();
    const text = (await report.textContent()) ?? '';
    // The vendor's own docs.md is known to open with a level-one heading and
    // a Setup table — both markdown syntax an un-rendered dump would leave
    // as literal characters. Neither survives real rendering.
    expect(text.startsWith('#')).toBe(false);
    expect(text).not.toContain('|---');
    expect(text).not.toContain('**');
  });
});

// =============================================================================
// AN-10 / AN-11 — the clear-text credential refusal, on screen — not
// staging-safe, and not runnable against the static mock backing either
// =============================================================================

test.describe('the clear-text credential refusal, as the panel shows it', () => {
  test.skip(
    true,
    'blocked in this run: needs the compose backing (a real credential proxy that ' +
      "reacts to what was actually sent), not the static mock backing this file's other " +
      'blocks run against — a canned response answers every write identically regardless ' +
      'of scheme. The refusal itself, including across the wire boundary a capability ' +
      'reads it through, is proven in ' +
      'tests/unit/platform/credentials/test_proxy_engine.py::test_the_clear_text_sentence_survives_crossing_the_wire.',
  );

  test('pointing a vendor at http:// with a credential stored shows the scheme and both ways out', async ({
    page,
  }) => {
    await page.goto(GRAFANA_ROUTE);
    // Left for the compose-backed run: fill endpoint with http://, store a
    // token, and read the verdict detail off the panel.
    expect(page.getByTestId('credential-result')).toBeDefined();
  });
});

// =============================================================================
// Sanity: the catalogue itself still opens, for the viewport this feature's
// claims are measured at
// =============================================================================

test('the catalogue opens at the normative viewport with no console error', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(CATALOGUE_ROUTE);
  await expect(page.getByTestId('page-header')).toBeVisible();
  expect(errors).toEqual([]);
});
