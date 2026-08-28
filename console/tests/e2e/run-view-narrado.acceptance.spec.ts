import { expect, test, type Locator, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * The run's own page, telling what it did in sentences instead of JSON.
 *
 * Fourteen claims, one block each, against `design/padrao-2026-08/RunView.dc.html`
 * and `Investigations.dc.html`. The claims marked `@staging-safe` are read-only
 * and reuse the slot's one shared live run rather than opening a second one; the
 * rest need a controlled fixture (a settled run and a live run with the same
 * vocabulary of events) that only the local mock plane can hold still, so they
 * run here against `run-0001` (settled) and `run-0003` (live) without that tag.
 *
 * **This spec is expected to be comprehensively red when it is written.** The
 * six-stage rail does not exist on this page at all; the transcript prints a raw
 * detail line and a `{...}` payload block open by default with no toggle; the
 * cost and "what it touched" panels show their empty state on a live run that has
 * already recorded a turn and an observation; "Descobertas até agora" does not
 * exist; and `/runs` draws every row the same way regardless of whether it is
 * still going. Every task after this one exists to turn one block of this file
 * green.
 */

const STAGING_SAFE_TAG = '@staging-safe';

const LIVE_RUN = 'run-0003';
const SETTLED_RUN = 'run-0001';
const FAILED_RUN = 'run-0004';

/** The six stages, canonical order, mirroring `core/state/types.py::StageName`. */
const STAGE_ORDER = [
  'resolve_integrations',
  'intake',
  'plan_evidence',
  'gather_evidence',
  'diagnose',
  'deliver',
] as const;

test.use({ viewport: { width: 1920, height: 1080 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

function stageItems(page: Page): Locator {
  return page.getByTestId('stage-item');
}

// =============================================================================
// AN-01 / AN-02 — the six stages, on top, the active one distinct
// =============================================================================

test.describe('AN-01/AN-02 — the pipeline rail names every stage, in order, with the active one distinct', () => {
  test(
    'a live run shows the six stages, in pipeline order, at the top of the page',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto(`/runs/${LIVE_RUN}`);
      const rail = page.getByTestId('stage-rail');
      await expect(rail).toBeVisible();

      const items = stageItems(page);
      await expect(items).toHaveCount(STAGE_ORDER.length);
      for (const [index, stage] of STAGE_ORDER.entries()) {
        await expect(items.nth(index)).toHaveAttribute('data-stage', stage);
      }
    },
  );

  test(
    'a completed stage shows its own duration; the active one is visually distinct; a future one shows its number',
    async ({ page }) => {
      await page.goto(`/runs/${LIVE_RUN}`);

      // resolve_integrations, intake and plan_evidence had already finished by
      // the time this run was opened — the replay this fixture serves says so.
      for (const stage of ['resolve_integrations', 'intake', 'plan_evidence']) {
        const row = page.locator(`[data-testid="stage-item"][data-stage="${stage}"]`);
        await expect(row).toHaveAttribute('data-state', 'done');
        await expect(row.getByTestId('stage-duration')).not.toHaveText('');
      }

      const active = page.locator('[data-testid="stage-item"][data-state="active"]');
      await expect(active).toHaveCount(1);
      await expect(active).toHaveAttribute('data-stage', 'gather_evidence');

      const futures = page.locator('[data-testid="stage-item"][data-state="future"]');
      await expect(futures).toHaveCount(2);
      // A future stage names its own position rather than a duration.
      await expect(futures.first().getByTestId('stage-number')).toHaveText('5');
    },
  );

  test('a failed stage shows its own failure shape, and the stages after it stay future', async ({
    page,
  }) => {
    await page.goto(`/runs/${FAILED_RUN}`);
    const failed = page.locator('[data-testid="stage-item"][data-state="failed"]');
    await expect(failed).toHaveCount(1);
    await expect(failed).toHaveAttribute('data-stage', 'plan_evidence');

    const futures = page.locator('[data-testid="stage-item"][data-state="future"]');
    await expect(futures).toHaveCount(3);
  });
});

// =============================================================================
// AN-03 / AN-04 / AN-05 — narrated by default, payload behind a closed disclosure
// =============================================================================

test.describe('AN-03/AN-04/AN-05 — the transcript narrates; the payload is one control away', () => {
  test(
    'in Narrado, no JSON payload block is visible anywhere in the transcript body',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto(`/runs/${SETTLED_RUN}`);
      const toggle = page.getByTestId('transcript-view-toggle');
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute('data-view', 'narrated');

      await expect(page.getByTestId('payload').first()).not.toBeVisible();
    },
  );

  test(
    'every event renders a narrated sentence naming the kind, with the raw payload behind a closed disclosure',
    async ({ page }) => {
      await page.goto(`/runs/${SETTLED_RUN}`);
      const narrations = page.getByTestId('event-narration');
      await expect(narrations.first()).toBeVisible();
      const count = await narrations.count();
      expect(count).toBeGreaterThan(0);
      for (let index = 0; index < count; index += 1) {
        const text = await narrations.nth(index).innerText();
        expect(text.trim().startsWith('{')).toBe(false);
      }

      const disclosure = page.getByTestId('event-payload-disclosure').first();
      await expect(disclosure).toBeVisible();
      expect(await disclosure.getAttribute('open')).toBeNull();
    },
  );

  test('switching to Bruto shows the full payloads, and switching back loses and duplicates nothing', async ({
    page,
  }) => {
    await page.goto(`/runs/${SETTLED_RUN}`);
    const before = Number(await page.getByTestId('transcript').getAttribute('data-total'));

    await page.getByTestId('transcript-view-raw').click();
    await expect(page.getByTestId('transcript-view-toggle')).toHaveAttribute(
      'data-view',
      'raw',
    );
    await expect(page.getByTestId('payload').first()).toBeVisible();
    const duringRaw = Number(await page.getByTestId('transcript').getAttribute('data-total'));
    expect(duringRaw).toBe(before);

    await page.getByTestId('transcript-view-narrated').click();
    const afterBack = Number(await page.getByTestId('transcript').getAttribute('data-total'));
    expect(afterBack).toBe(before);
  });
});

// =============================================================================
// AN-06 / AN-07 / AN-08 — the rail is honest while the run is live
// =============================================================================

test.describe('AN-06/AN-07/AN-08 — the rail never claims absence about a run still writing', () => {
  test(
    'a live run with a recorded turn shows tokens and a turn count, never the settled empty state',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto(`/runs/${LIVE_RUN}`);
      // The fixture's stream carries one finished turn (`turn_completed`,
      // 1840 tokens) before the page is even opened.
      await expect
        .poll(async () => page.getByTestId('usage-tokens').textContent())
        .not.toBe(null);
      const tokens = await page.getByTestId('usage-tokens').innerText();
      expect(tokens.trim()).not.toBe('');
      expect(tokens.replace(/[^\d]/g, '')).not.toBe('0');
      // The panel chrome's own `data-state` is what decides whether the
      // settled "empty" presentation — heading, body and a call-to-action
      // link back to the list (`Panel`, `console/src/surfaces/panel.tsx`) —
      // renders at all. A live run's cost panel must read `ready`, never
      // `empty`, however little of the run has arrived.
      const costPanel = page.locator('[data-testid="panel"]', {
        has: page.getByTestId('usage-tokens'),
      });
      await expect(costPanel).toHaveAttribute('data-state', 'ready');
    },
  );

  test('a resource a live run touches appears in "what it touched" without a reload', async ({
    page,
  }) => {
    await page.goto(`/runs/${LIVE_RUN}`);
    // `estate.failed_units` is called with `{"node": "node01"}` on this
    // fixture's stream — a resource argument key the console already knows.
    await expect
      .poll(async () => page.getByTestId('touched-resource').count())
      .toBeGreaterThan(0);
    await expect(page.getByTestId('touched-resource').first()).toContainText('node01');
  });

  test('findings from completed stages are listed as the run goes, each with its own status shape', async ({
    page,
  }) => {
    await page.goto(`/runs/${LIVE_RUN}`);
    const findings = page.getByTestId('finding-item');
    await expect
      .poll(async () => findings.count())
      .toBeGreaterThanOrEqual(3);
    await expect(findings.first().locator('[data-shape]')).toHaveCount(1);
  });

  // A fifth claim was here — a settled run with nothing to spend showing
  // one honest line rather than the empty-panel call-to-action — and was
  // removed rather than left red for the wrong reason: `run-0004`'s summary
  // ("The investigation could not reach the metrics agent...") reads as a
  // sentence somebody wrote, not as a raised exception
  // (`console/src/surfaces/failures.ts::looksRaised`), so `readFailure`
  // returns `technical: ''` and `failedBeforeStart` is false for it — the
  // *settled*, permanently-empty branch this claim wanted was never reached
  // by this fixture. This is not one of the fourteen normative claims; the
  // mechanism itself (`run.usage.empty.heading` inside a `ready` panel,
  // unchanged by this feature) is pre-existing and outside this feature's
  // file scope to re-fixture safely. Recorded in the control file rather
  // than asserted here on a false premise.
});

// =============================================================================
// AN-09 — the header count is the rendered count
// =============================================================================

test.describe('AN-09 — the transcript header count is the list actually rendered', () => {
  for (const runId of [SETTLED_RUN, LIVE_RUN]) {
    test(
      `on ${runId}, the header count equals the number of rendered entries`,
      { tag: STAGING_SAFE_TAG },
      async ({ page }) => {
        await page.goto(`/runs/${runId}`);
        await expect
          .poll(async () => page.getByTestId('transcript-event').count())
          .toBeGreaterThan(0);
        const rendered = await page.getByTestId('transcript-event').count();
        const total = Number(await page.getByTestId('transcript').getAttribute('data-total'));
        expect(total).toBe(rendered);
      },
    );
  }
});

// =============================================================================
// AN-10 / AN-11 — one funnel: same kind, same lead phrase, live or replayed;
// an unknown kind never falls back to JSON
// =============================================================================

test.describe('AN-10/AN-11 — replay and stream narrate the same vocabulary the same way', () => {
  test('a tool_called event narrates with the same lead phrase whether it was replayed or streamed', async ({
    page,
  }) => {
    await page.goto(`/runs/${SETTLED_RUN}`);
    const replayedCall = page
      .locator('[data-testid="transcript-event"][data-raw-kind="tool_called"]')
      .first();
    await expect(replayedCall).toBeVisible();
    const replayedText = (
      await replayedCall.getByTestId('event-narration').innerText()
    ).trim();

    await page.goto(`/runs/${LIVE_RUN}`);
    const streamedCall = page
      .locator('[data-testid="transcript-event"][data-raw-kind="tool_called"]')
      .first();
    await expect(streamedCall).toBeVisible();
    const streamedText = (
      await streamedCall.getByTestId('event-narration').innerText()
    ).trim();

    // Not asserted equal in full — the two fixtures name different
    // capabilities, and the interpolated name is part of the lead itself
    // ("Called {name}") rather than separated from it — but the fixed lead
    // word the template reaches for is a fact about the code rather than
    // about which fixture happened to be open. Full identity on one shared
    // fixture is what the unit suite proves.
    expect(replayedText.startsWith('Called ')).toBe(true);
    expect(streamedText.startsWith('Called ')).toBe(true);
  });

  test('a kind this console has never met still renders a sentence naming it, never JSON', async ({
    page,
  }) => {
    // `stage_completed` is on the wire (this feature puts it there) but is
    // not one of the seventeen kinds the transcript's own vocabulary
    // declares — the console's honest unknown-kind path, exercised for
    // real rather than injected.
    await page.goto(`/runs/${LIVE_RUN}`);
    const unknown = page.locator(
      '[data-testid="transcript-event"][data-raw-kind="stage_completed"]',
    );
    await expect
      .poll(async () => unknown.count())
      .toBeGreaterThan(0);
    const text = (await unknown.first().getByTestId('event-narration').innerText()).trim();
    expect(text).toContain('stage_completed');
    expect(text.startsWith('{')).toBe(false);
  });
});

// The artboard's own `.newRow` annotation on a transcript entry that just
// arrived has no AN number of its own — a gap in the normative list, not a
// reason to skip it — but it is proved as a unit test
// (`tests/unit/surfaces/transcript.test.tsx`, describe block "an entry that
// arrives after the transcript already rendered"), not here. The local mock
// plane serves a live run's whole catch-up read as one HTTP response with no
// observable delay before the last of it, so there is no in-between instant
// this suite can poll for between "eleven events" and "twelve" — every
// attempt at that either raced the poll against a burst that already
// finished, or asserted nothing a browser could disagree with. What a
// browser test cannot time reliably, a unit test controls exactly: it
// renders the component, then re-renders it with one appended event, and
// reads the same `data-just-arrived` attribute this spec would have.

// =============================================================================
// AN-12 — conduct controls live, absent settled
// =============================================================================

test.describe('AN-12 — the conduct controls exist on a live run and nowhere on a settled one', () => {
  test('a live run offers Assume, Stop and "Say something…"', { tag: STAGING_SAFE_TAG }, async ({
    page,
  }) => {
    await page.goto(`/runs/${LIVE_RUN}`);
    await expect(page.getByTestId('takeover')).toBeVisible();
    await expect(page.getByTestId('add-context')).toBeVisible();
  });

  test('a settled run offers none of them', async ({ page }) => {
    await page.goto(`/runs/${SETTLED_RUN}`);
    await expect(page.getByTestId('takeover')).toHaveCount(0);
    await expect(page.getByTestId('add-context')).toHaveCount(0);
  });
});

// =============================================================================
// AN-14 — the run list: live cards, whole headlines, shaped chips, failed rows
// =============================================================================

test.describe('AN-14 — the run list groups live runs first and never truncates a headline mid-word', () => {
  test('a live run is drawn as a card with a stage bar and an elapsed time, ahead of the settled rows', {
    tag: STAGING_SAFE_TAG,
  }, async ({ page }) => {
    await page.goto('/runs');
    const liveCards = page.getByTestId('run-live-card');
    await expect(liveCards.first()).toBeVisible();
    await expect(liveCards.first().getByTestId('run-live-stage-bar')).toBeVisible();
    await expect(liveCards.first().getByTestId('run-live-elapsed')).toBeVisible();
  });

  test('a completed row shows a claims chip with a filled or ringed shape, never truncated mid-word', {
    tag: STAGING_SAFE_TAG,
  }, async ({ page }) => {
    await page.goto('/runs');
    const rows = page.getByTestId('run-card');
    await expect(rows.first()).toBeVisible();
    await expect(rows.first().getByTestId('run-evidence')).toBeVisible();

    const headline = rows.first().getByTestId('run-card-subject');
    const text = (await headline.innerText()).trim();
    expect(text.length).toBeGreaterThan(0);
    // A headline this component clips does so at a line boundary (CSS
    // line-clamp on the whole sentence), never by slicing characters off a
    // fixed-width string — so the last character on screen is never the
    // truncation marker riding mid-word. `run.subject.text` (character-cut)
    // is deliberately not what this row reads.
    expect(text.endsWith('…')).toBe(false);
  });

  test('a failed run is drawn distinctly, with a direct link to its transcript', {
    tag: STAGING_SAFE_TAG,
  }, async ({ page }) => {
    // The stage a run stopped at is not asserted here: it is a summary-list
    // field (`last_completed_stage`/`stage_index`) the title-vivo feature of
    // this same wave adds to `GET /v1/runs`, not yet present — FR-021a's own
    // words are "degrading sem eles" (degrading without them) for exactly
    // this case, so the honest thing this slot can show is the failure shape
    // the list already carries (`status`) and a direct way to the narrated
    // account, never a fabricated stage name.
    await page.goto('/runs?status=failed');
    const failedRow = page.locator('[data-testid="run-card"][data-status="failed"]').first();
    await expect(failedRow).toBeVisible();
    await expect(failedRow.locator('[data-shape="square"]').first()).toHaveCount(1);
    await expect(failedRow.getByTestId('run-card-transcript-link')).toBeVisible();
  });

  test('the status and trigger filters render as chips', { tag: STAGING_SAFE_TAG }, async ({
    page,
  }) => {
    await page.goto('/runs');
    await expect(page.getByTestId('filter-chip').first()).toBeVisible();
  });
});
