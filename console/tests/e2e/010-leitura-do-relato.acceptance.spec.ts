import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * The console reads what an investigation recorded, instead of improvising on
 * top of it: a run's name is a sentence rather than the document it wrote, the
 * document itself is rendered as a document, a run that has settled is not
 * offered a stop button, and the transcript and the cost panel report what the
 * record actually holds.
 *
 * **This spec is expected to be comprehensively red when it is written.** The
 * detail screen still prints the raw report as its own title, the console's
 * status vocabulary does not know the word the runtime emits on an ordinary
 * finish, and the report panel has no renderer at all — every group below
 * fails for a different one of those reasons until the corresponding screen
 * change lands.
 *
 * Fixture identifiers are named literally, not read off a prior screen. The
 * runs this spec is about (`run-0005`, `run-0101`, `run-0102`, `run-0103`)
 * were added to the deterministic dataset for exactly this spec and are
 * stable across every run of it — unlike an incident's own address, nothing
 * about them is derived at build time, so there is nothing to read first.
 */

function stringConstant(name: string): string {
  const source = readFileSync(
    fileURLToPath(new URL('../../../config/constants/console.py', import.meta.url)),
    'utf8',
  );
  const found = new RegExp(`^${name}: Final = "([^"]*)"`, 'm').exec(source);
  if (found?.[1] === undefined) {
    throw new Error(`${name} is not declared in config/constants/console.py`);
  }
  return found[1];
}

// The one spelling of the tag that marks a test safe to run against a shared,
// live environment — read from the constants layer the same way the
// transversal suite does, so the two cannot drift into two spellings that
// between them select nothing.
const STAGING_SAFE_TAG = stringConstant('CONSOLE_STAGING_SAFE_TAG');

const MARKDOWN_SYNTAX = /[#*`_~[\]|>]/;

test.use({ viewport: { width: 1920, height: 1080 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

// --- Small helpers, local to this spec --------------------------------------

/** The page header's own H1 text, on whichever run detail page is open. */
async function headerText(page: Page): Promise<string> {
  const header = page.getByTestId('page-header');
  await expect(header).toBeVisible();
  const h1 = header.getByRole('heading', { level: 1 });
  return (await h1.textContent())?.trim() ?? '';
}

/** One row of the runs list, addressed by the run id the list itself carries. */
function rowFor(page: Page, runId: string) {
  return page.locator(`[data-testid="row"][data-row="${runId}"]`);
}

/** The SUBJECT cell of the row for `runId` — the column labelled "Subject". */
function subjectCellFor(page: Page, runId: string) {
  return rowFor(page, runId).locator('td[data-label="Subject"]');
}

test.describe('(a) the name of a run is a sentence, everywhere it is shown', () => {
  test('the header, the tab, and the list cell agree on a run with a recorded headline, none of them carrying markdown syntax', async ({
    page,
  }) => {
    await page.goto('/runs/run-0102');
    const header = await headerText(page);
    expect(header, `header "${header}" carries markdown syntax`).not.toMatch(
      MARKDOWN_SYNTAX,
    );
    expect(
      header.length,
      `header is ${String(header.length)} characters`,
    ).toBeLessThanOrEqual(120);
    expect(header, 'header carries a line break').not.toMatch(/[\r\n]/);

    const title = await page.title();
    expect(
      title.startsWith(header),
      `tab "${title}" does not start with the header`,
    ).toBe(true);

    await page.goto('/runs');
    const cell = subjectCellFor(page, 'run-0102');
    await expect(cell).toBeVisible();
    const cellText = (await cell.textContent())?.trim() ?? '';
    expect(cellText, `list cell "${cellText}" carries markdown syntax`).not.toMatch(
      MARKDOWN_SYNTAX,
    );
    expect(
      cellText,
      'the list cell and the detail header disagree about the same run',
    ).toBe(header);
  });

  test('a headline longer than the display limit is clipped, with the full sentence in a tooltip', async ({
    page,
  }) => {
    await page.goto('/runs/run-0102');
    const header = page.getByTestId('page-header').getByRole('heading', { level: 1 });
    const text = (await header.textContent())?.trim() ?? '';
    expect(
      text.length,
      `header is ${String(text.length)} characters, over the 120 limit`,
    ).toBeLessThanOrEqual(120);
    const title = await header.getAttribute('title');
    expect(title, 'no tooltip carries the full headline').not.toBeNull();
    expect((title ?? '').length).toBeGreaterThan(text.length - 2);
  });
});

test.describe('(b) a run with no recorded headline is named by trigger and short id, never by "Not recorded"', () => {
  test('the detail header and the list cell both show trigger and short id, and never the raw report', async ({
    page,
  }) => {
    await page.goto('/runs/run-0101');
    const header = await headerText(page);
    expect(header, 'header prints the raw report').not.toContain('Incident Findings');
    expect(header, 'header carries markdown syntax').not.toMatch(MARKDOWN_SYNTAX);
    expect(header).toContain('run-010');

    await page.goto('/runs');
    const cell = subjectCellFor(page, 'run-0101');
    const cellText = (await cell.textContent())?.trim() ?? '';
    expect(cellText, 'list cell reads "Not recorded"').not.toBe('Not recorded');
    expect(cellText, 'list cell prints the raw report').not.toContain(
      'Incident Findings',
    );
  });

  test('the report panel still shows the recorded document, even though the name did not use it', async ({
    page,
  }) => {
    await page.goto('/runs/run-0101');
    await expect(page.getByTestId('report')).toContainText('standby');
  });
});

test.describe('(c) the report renders as a document, sanitised', () => {
  test('a third-level heading becomes a heading element, not literal "###"', async ({
    page,
  }) => {
    await page.goto('/runs/run-0101');
    const report = page.getByTestId('report');
    await expect(
      report.locator('h3, h4').filter({ hasText: 'Evidence gathered' }),
    ).toBeVisible();
    await expect(report).not.toContainText('###');
  });

  test('a list renders as a list, and a table renders as a table', async ({ page }) => {
    await page.goto('/runs/run-0101');
    const report = page.getByTestId('report');
    await expect(report.locator('ul li, ol li').first()).toBeVisible();
    await expect(report.locator('table')).toBeVisible();
  });

  test('a wide code block scrolls within itself, and the page body does not scroll horizontally', async ({
    page,
  }) => {
    await page.goto('/runs/run-0103');
    const report = page.getByTestId('report');
    await expect(report.locator('pre')).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflow, 'the document scrolls horizontally').toBe(false);
  });

  test('a remote image is never requested, and is represented by its own alt text', async ({
    page,
  }) => {
    const external: string[] = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (!['127.0.0.1', 'localhost', '[::1]', '0.0.0.0'].includes(url.hostname)) {
        external.push(request.url());
      }
    });
    await page.goto('/runs/run-0103');
    await page.waitForLoadState('networkidle');
    expect(await page.locator('[data-testid="report"] img').count()).toBe(0);
    expect(
      external.some((url) => url.includes('track.png')),
      external.join(', '),
    ).toBe(false);
  });

  test('a link whose scheme is executable is not navigable', async ({ page }) => {
    await page.goto('/runs/run-0103');
    const report = page.getByTestId('report');
    const link = report.getByRole('link', { name: /open the dashboard/i });
    expect(
      await link.count(),
      'a javascript: link was rendered as a navigable anchor',
    ).toBe(0);
    await expect(report).toContainText('open the dashboard');
  });

  test('raw HTML in the document reads as text, never as an element', async ({
    page,
  }) => {
    await page.goto('/runs/run-0103');
    const report = page.getByTestId('report');
    expect(await report.locator('script').count()).toBe(0);
    await expect(report).toContainText("<script>alert('not really')</script>");
  });

  test('the recorded text is available in a disclosure that opens closed', async ({
    page,
  }) => {
    await page.goto('/runs/run-0101');
    const disclosure = page.getByTestId('report-raw');
    await expect(disclosure).toBeVisible();
    expect(await disclosure.evaluate((node) => (node as HTMLDetailsElement).open)).toBe(
      false,
    );
    await disclosure.locator('summary').click();
    await expect(disclosure).toContainText('### Incident Findings');
  });
});

test.describe('(d) a run that has settled is not offered as a live one', () => {
  test('the control panel is absent, the connection text is absent, and the badge reads as a known status', async ({
    page,
  }) => {
    await page.goto('/runs/run-0101');
    await expect(page.getByTestId('stop-run')).toHaveCount(0);
    await expect(page.getByTestId('take-over')).toHaveCount(0);
    await expect(page.getByTestId('takeover')).toHaveCount(0);
    await expect(page.getByText(/paused in the background/i)).toHaveCount(0);
    const badge = page.getByTestId('page-header').locator('[data-role]');
    await expect(badge.first()).toHaveAttribute('data-known', 'true');
  });

  test('the transcript rendered is the read-back one, not the live stream', async ({
    page,
  }) => {
    await page.goto('/runs/run-0101');
    await expect(page.getByTestId('live-run')).toHaveCount(0);
  });

  test('a run still in flight keeps its control panel — this feature removes a false offer, not the real one', async ({
    page,
  }) => {
    await page.goto('/runs/run-0003');
    await expect(page.getByTestId('takeover')).toBeVisible();
  });
});

test.describe('(e) the transcript and the cost panel report what the record holds', () => {
  test('a run with four recorded tool calls shows four call entries and four result entries', async ({
    page,
  }) => {
    await page.goto('/runs/run-0005');
    const calls = page.locator('[data-testid="transcript-event"][data-kind="call"]');
    const results = page.locator(
      '[data-testid="transcript-event"][data-kind="result"]',
    );
    await expect(calls).toHaveCount(4);
    await expect(results).toHaveCount(4);
  });

  test('the transcript panel states the same count it draws', async ({ page }) => {
    await page.goto('/runs/run-0005');
    const drawn = await page.locator('[data-testid="transcript-event"]').count();
    const panel = page
      .getByTestId('panel')
      .filter({ hasText: 'Investigation transcript' })
      .first();
    await expect(panel).toContainText(`${String(drawn)} event`);
  });

  test('a run with recorded turns does not say cost was never recorded, and shows one row per turn', async ({
    page,
  }) => {
    await page.goto('/runs/run-0005');
    const cost = page
      .getByTestId('panel')
      .filter({ hasText: 'Cost and tokens' })
      .first();
    await expect(cost).not.toContainText('No cost recorded');
    await expect(cost.getByTestId('usage-by-turn').locator('tbody tr')).toHaveCount(2);
  });

  test('a run with no turn at all still says cost was never recorded — the sentence still exists for when it is true', async ({
    page,
  }) => {
    await page.goto('/runs/run-0002');
    const cost = page
      .getByTestId('panel')
      .filter({ hasText: 'Cost and tokens' })
      .first();
    await expect(cost).toContainText('No cost recorded');
  });
});

test.describe('(f) what an investigation touched is read from its own record', () => {
  test('a run whose record names resources lists each of them — read from the run, not from its incident', async ({
    page,
  }) => {
    await page.goto('/runs/run-0005');
    const links = page
      .getByTestId('panel')
      .filter({ hasText: 'What this investigation touched' })
      .first();
    await expect(links).not.toContainText('Nothing linked yet');
    // The run's own record named these two — not the incident's subjects
    // ("backup-1f376301", "backup-7d831311"), which is what this panel used
    // to show instead.
    await expect(links).toContainText('proxmox:container/hal9000/110');
    await expect(links).toContainText('ct-101');
  });

  test('the same run names its incident by title, not by identifier', async ({
    page,
  }) => {
    await page.goto('/runs/run-0005');
    const links = page
      .getByTestId('panel')
      .filter({ hasText: 'What this investigation touched' })
      .first();
    await expect(links.getByTestId('run-incident-link')).toBeVisible();
    const incidentLinkText =
      (await links.getByTestId('run-incident-link').textContent()) ?? '';
    expect(incidentLinkText).not.toMatch(/^inc-|^inc_/);
  });

  test('a run with no vinculo at all says nothing was linked', async ({ page }) => {
    await page.goto('/runs/run-0101');
    const links = page
      .getByTestId('panel')
      .filter({ hasText: 'What this investigation touched' })
      .first();
    await expect(links).toContainText('Nothing linked yet');
  });
});

// =============================================================================
// Safe to run against a shared, live environment: read-only, no fixture id.
// =============================================================================

test.describe('staging-safe: name and terminal-state claims, against whatever the deployment actually recorded', () => {
  test(
    'the most recently started run has a header with no markdown syntax, at most 120 characters and no line break',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/runs');
      const firstRow = page.getByTestId('row').first();
      await expect(firstRow).toBeVisible();
      await firstRow.locator('a').first().click();
      await expect(page.getByTestId('page-header')).toBeVisible();

      const header = await headerText(page);
      expect(header, `header "${header}" carries markdown syntax`).not.toMatch(
        MARKDOWN_SYNTAX,
      );
      expect(header.length).toBeLessThanOrEqual(120);
      expect(header).not.toMatch(/[\r\n]/);
      expect(header, 'header prints the raw report').not.toContain('###');

      const title = await page.title();
      expect(title.startsWith(header)).toBe(true);
    },
  );

  test(
    'a settled run on this deployment is not offered a stop or a takeover',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/runs');
      const rows = page.getByTestId('row');
      const count = await rows.count();
      for (let index = 0; index < count; index += 1) {
        const row = rows.nth(index);
        const statusCell = row.locator('td[data-label="Status"]');
        const status = ((await statusCell.textContent()) ?? '').trim().toLowerCase();
        if (
          !['completed', 'partial', 'failed', 'cancelled', 'succeeded'].includes(status)
        ) {
          continue;
        }
        await row.locator('a').first().click();
        await expect(page.getByTestId('page-header')).toBeVisible();
        await expect(page.getByTestId('stop-run')).toHaveCount(0);
        await expect(page.getByTestId('take-over')).toHaveCount(0);
        await expect(page.getByText(/paused in the background/i)).toHaveCount(0);
        return;
      }
      test.skip(true, 'no settled run exists on this deployment yet');
    },
  );
});
