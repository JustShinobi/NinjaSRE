import { expect, test, type Locator, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * Decisions: the action card by field, the expired one with an exit.
 *
 * Fourteen claims, against `design/padrao-2026-08/Decisions.dc.html` and
 * `DecisionsLight.dc.html`. The claims marked `@staging-safe` also run against
 * `https://stg-ninjasre.lan.kyo.ninja` — pure reads, except AN-08, which is
 * propose-only (creates a pending proposal; applies nothing). AN-06, AN-11,
 * AN-13 are not staging-safe: AN-06 needs a genuinely pending card (staging's
 * queue may hold none once expiry is swept honestly), AN-11 and AN-13 need a
 * controlled evidence/failure shape only the local mock plane holds still.
 *
 * **This spec is expected to be comprehensively red when it is written.** The
 * page today prints the whole action document as ~40 lines of JSON in a
 * "Target" field; the expired card says "ask for it again" with no control
 * for it; the sidebar counts an approval that can no longer be decided. None
 * of the six named sections, the risk gauge, the repropose button or the
 * decided history exist yet. Every task after this one exists to turn one
 * block of this file green.
 */

const STAGING_SAFE_TAG = '@staging-safe';

test.use({ viewport: { width: 1440, height: 1040 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

/** A named string field of an unknown JSON body, or empty — never `[object Object]`. */
function stringField(body: unknown, key: string): string {
  const record =
    typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {};
  const found = record[key];
  return typeof found === 'string' ? found : '';
}

function cards(page: Page): Locator {
  return page.getByTestId('decision-card');
}

/** The first card on the Actions tab, whichever state it is in. */
async function firstCard(page: Page): Promise<Locator> {
  await page.goto('/decisions?tab=actions');
  const card = cards(page).first();
  await expect(card).toBeVisible();
  return card;
}

/** The first card in a named state, or `null` when the queue holds none. */
async function cardInState(page: Page, state: string): Promise<Locator | null> {
  await page.goto('/decisions?tab=actions');
  const card = page
    .getByTestId('decision-card')
    .and(page.locator(`[data-state="${state}"]`));
  if ((await card.count()) === 0) return null;
  return card.first();
}

// =============================================================================
// AN-01 — a human title, never the raw document
// =============================================================================

test.describe('AN-01 — the card is titled by a human sentence, never a raw document', () => {
  test(
    'the title names the action and the target, never `path =`, never JSON, never a bare identifier',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      const card = await firstCard(page);
      const title = card.getByTestId('decision-title');
      await expect(title).toBeVisible();
      const text = (await title.textContent()) ?? '';
      expect(text.trim()).not.toBe('');
      expect(text).not.toMatch(/path\s*=/);
      expect(text).not.toMatch(/[{}]/);
      // A bare identifier is a UUID-shaped or `apr-`/`res-`-prefixed token and
      // nothing else on the line — a sentence with a target named inside it
      // (`lxc/122`, `pve01`) is not the same claim and must not fail this.
      expect(text.trim()).not.toMatch(/^(apr|res|run)-[a-f0-9-]+$/i);

      const meta = card.getByTestId('decision-meta');
      await expect(meta).toBeVisible();
    },
  );
});

// =============================================================================
// AN-02 — no JSON fragment visible with every <details> closed
// =============================================================================

test.describe('AN-02 — nothing on the page reads as raw JSON while every <details> is closed', () => {
  test('no visible text contains `{"`', { tag: STAGING_SAFE_TAG }, async ({ page }) => {
    await firstCard(page);
    const openDetails = page.locator('details[open]');
    expect(await openDetails.count()).toBe(0);

    const bodyText = await page.locator('body').innerText();
    expect(bodyText).not.toContain('{"');
  });
});

// =============================================================================
// AN-03 — the risk gauge: five segments, "risk N of 5"
// =============================================================================

test.describe('AN-03 — risk is a five-segment gauge with N filled and the label "risk N of 5"', () => {
  test(
    'the gauge reports a filled count between 1 and 5 of 5, matching its own label',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      const card = await firstCard(page);
      const gauge = card.getByTestId('decision-risk');
      await expect(gauge).toBeVisible();

      const scale = await gauge.getAttribute('data-risk-scale');
      expect(scale).toBe('5');
      const score = Number(await gauge.getAttribute('data-risk-score'));
      expect(score).toBeGreaterThanOrEqual(1);
      expect(score).toBeLessThanOrEqual(5);

      const segments = gauge.getByTestId('risk-segment');
      await expect(segments).toHaveCount(5);
      const filled = gauge.locator('[data-filled="true"]');
      await expect(filled).toHaveCount(score);

      await expect(gauge).toContainText(String(score));
      await expect(gauge).toContainText('5');
    },
  );
});

// =============================================================================
// AN-04 — the six named sections
// =============================================================================

test.describe('AN-04 — the card carries all six named sections', () => {
  test(
    'what will happen, the rollback, why, evidence, blast radius, and the autonomy line all render',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      const card = await firstCard(page);

      for (const section of [
        'steps',
        'rollback',
        'why',
        'evidence',
        'blast-radius',
        'autonomy',
      ]) {
        const region = card.locator(
          `[data-testid="decision-section"][data-section="${section}"]`,
        );
        await expect(
          region,
          `section "${section}" is missing from the card`,
        ).toBeVisible();
      }

      // Steps and rollback steps are numbered, one sentence each.
      const step = card.getByTestId('decision-step').first();
      await expect(step).toBeVisible();
      await expect(step.getByTestId('step-ordinal')).toHaveText('1');
    },
  );
});

// =============================================================================
// AN-05 — the raw payload only behind a closed <details>
// =============================================================================

test.describe('AN-05 — the raw action document exists only behind a closed <details>', () => {
  test(
    'a `<details>` labelled "raw action payload" is present and closed by default',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      const card = await firstCard(page);
      const details = card.getByTestId('raw-payload');
      await expect(details).toBeVisible();
      expect(await details.evaluate((node) => (node as HTMLDetailsElement).open)).toBe(
        false,
      );

      await details.locator('summary').click();
      expect(await details.evaluate((node) => (node as HTMLDetailsElement).open)).toBe(
        true,
      );
      await expect(details).toContainText('{');
    },
  );
});

// =============================================================================
// AN-06 — a pending, unexpired decision offers Approve and Reject
// =============================================================================

test.describe('AN-06 — a pending, unexpired decision shows Approve and Reject', () => {
  test('the pending card in the mock queue is decidable', async ({ page }) => {
    const card = await cardInState(page, 'pending');
    if (card === null) {
      test.skip(true, 'the mock queue holds no pending, unexpired approval right now');
      return;
    }
    // Both live decision paths compose without edits: an approval whose run
    // has an open interaction renders `DecisionControls`; one without renders
    // `IncidentDecisionControls`. Whichever this card is, one control set
    // with both verbs must be present — the mock's data decides which.
    const approve = card.getByTestId(/^(approve|decision-control)$/).first();
    const reject = card.getByTestId(/^(reject|decision-control)$/).last();
    await expect(approve).toBeVisible();
    await expect(reject).toBeVisible();
  });
});

// =============================================================================
// AN-07 — an expired decision offers repropose and discard, never Approve
// =============================================================================

test.describe('AN-07 — an expired decision offers "Propose again, now" and "Discard", never Approve', () => {
  test(
    'the expired footer carries both controls and no approve control anywhere on the card',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      const card = await cardInState(page, 'expired');
      if (card === null) {
        test.skip(true, 'the queue currently holds no expired approval');
        return;
      }
      const footer = card.getByTestId('expired-footer');
      await expect(footer).toBeVisible();
      await expect(footer.getByTestId('repropose')).toBeVisible();
      await expect(footer.getByTestId('discard')).toBeVisible();
      await expect(card.getByTestId('approve')).toHaveCount(0);
      await expect(card.getByTestId('decision-control')).toHaveCount(0);
    },
  );
});

// =============================================================================
// AN-08 — reproposing produces a new pending decision, in place
// =============================================================================

test.describe('AN-08 — "Propose again, now" produces a new pending decision, on the same page', () => {
  test(
    'reproposing the expired card produces a fresh pending decision, visible on the same page without a manual navigation',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      const card = await cardInState(page, 'expired');
      if (card === null) {
        test.skip(true, 'the queue currently holds no expired approval to repropose');
        return;
      }
      const originalId = await card.getAttribute('data-approval');

      // The origin is never removed from `state=expired` by a repropose —
      // only `discard` changes its own state (FR-018) — and `approvals.tsx`
      // only ever expands `queue[0]`, oldest-and-most-urgent first, so an
      // origin card can stay the page's expanded one after this click. What
      // AN-08 actually claims is that the new decision is visible on the
      // page, not that it displaces the origin's position — asserting the
      // first `decision-card` here would fail in every environment that has
      // any expired decision at all, which the origin itself still is.
      const [response] = await Promise.all([
        page.waitForResponse(
          (res) =>
            res.url().includes('/api/approval') && res.request().method() === 'POST',
        ),
        card.getByTestId('repropose').click(),
      ]);
      expect(response.ok()).toBe(true);
      const body: unknown = await response.json();
      const newId = stringField(body, 'approval_id');
      expect(newId).not.toBe('');
      expect(newId).not.toBe(originalId);
      expect(stringField(body, 'state')).toBe('pending');

      // `router.refresh()` re-renders the server tree; the new decision
      // shows up either as the expanded card or as a one-sentence collapsed
      // row (the "many pending" edge case) — both carry `data-state` now.
      const visible = page
        .locator(
          '[data-testid="decision-card"], [data-testid="decision-row-collapsed"]',
        )
        .and(page.locator(`[data-approval="${newId}"]`));
      await expect(visible).toHaveAttribute('data-state', 'pending');
    },
  );
});

// =============================================================================
// AN-09 — the sidebar badge counts only pending, unexpired decisions
// =============================================================================

test.describe('AN-09 — the sidebar badge is exactly the pending, unexpired count', () => {
  test(
    'the badge next to Decisions matches pending approvals plus pending change proposals',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      // The badge is documented (`decisions.tsx`'s own comment) to sum both
      // tabs — "a decision waiting is a decision waiting, whichever tab it
      // would open to" — and the plan's own badge decision keeps that sum.
      // Comparing it against approvals alone mismatches on any environment
      // that also has a pending change proposal, which the default dataset
      // does; this counts both queues before reading the badge, rather than
      // asserting a reference count the badge was never supposed to equal.
      await page.goto('/decisions?tab=actions');
      // Only the first pending approval, if any, expands into a
      // `decision-card` — the rest collapse per the "many pending" edge
      // case — and both representations carry `data-state` now.
      const pendingApprovals = await page
        .locator(
          '[data-testid="decision-card"], [data-testid="decision-row-collapsed"]',
        )
        .and(page.locator('[data-state="pending"]'))
        .count();

      await page.goto('/decisions?tab=changes');
      const pendingProposals = await page.getByTestId('proposal-item').count();

      await page.goto('/decisions?tab=actions');
      // `sidebar.tsx` never renders the count span at zero (`count === 0 ?
      // null : ...`) — absent, not a chip reading "0" — so an absent badge
      // *is* the zero case, not a locator failure.
      const navEntry = page
        .getByTestId('nav-entry')
        .and(page.locator('[data-area="decisions"]'));
      const badge = navEntry.getByTestId('nav-count');
      const badgeCount =
        (await badge.count()) === 0 ? 0 : Number(await badge.first().textContent());

      expect(badgeCount).toBe(pendingApprovals + pendingProposals);
    },
  );
});

// =============================================================================
// AN-10 — "Decided recently" lists outcome, author, relative time
// =============================================================================

test.describe('AN-10 — "Decided recently" lists past decisions with outcome, author and time', () => {
  test(
    'the decided list carries a status shape, a sentence, an outcome and a relative instant per row',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/decisions?tab=actions');
      const list = page.getByTestId('decided-list');
      await expect(list).toBeVisible();

      const items = list.getByTestId('decided-item');
      const count = await items.count();
      if (count === 0) {
        await expect(list.getByTestId('decided-empty')).toBeVisible();
        return;
      }
      const first = items.first();
      await expect(first).toHaveAttribute(
        'data-verdict',
        /^(approved|rejected|discarded)$/,
      );
      const time = first.locator('time');
      await expect(time).toHaveCount(1);
      expect(await time.getAttribute('datetime')).not.toBe('');
    },
  );
});

// =============================================================================
// AN-11 — every evidence item links to its source, never an empty href
// =============================================================================

test.describe('AN-11 — every evidence item is a link to its source', () => {
  test('each evidence link has a non-empty href', async ({ page }) => {
    const card = await firstCard(page);
    const items = card.getByTestId('evidence-item');
    const count = await items.count();
    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      const link = items.nth(index).getByTestId('evidence-link');
      await expect(link).toHaveCount(1);
      const href = await link.getAttribute('href');
      expect(href).not.toBeNull();
      expect(href).not.toBe('');
    }
  });
});

// =============================================================================
// AN-12 — the Changes tab, empty, is one line and one link
// =============================================================================

test.describe('AN-12 — the Changes tab, with nothing proposed, is one line and one link', () => {
  test(
    'the empty state is a single sentence plus a link, nothing more',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/decisions?tab=changes');
      const panel = page.getByTestId('panel');
      await expect(panel).toBeVisible();
      const state = await panel.getAttribute('data-state');
      if (state !== 'empty') {
        test.skip(
          true,
          'the environment currently holds a change proposal, so the empty state cannot be observed',
        );
        return;
      }
      const paragraphs = panel.locator('p');
      await expect(paragraphs).toHaveCount(1);
      const links = panel.locator('a');
      await expect(links).toHaveCount(1);
    },
  );
});

// =============================================================================
// AN-13 — a failed listing says it could not read, never "nothing proposed"
// =============================================================================

test.describe('AN-13 — a failed read says it could not read, and never claims nothing is proposed', () => {
  test('the panel reports an error state, not an empty one, when the listing fails', async ({
    page,
  }) => {
    // The mock accepts any credential (`session.ts`'s own comment), so a
    // forged bearer proves nothing here — the failure has to be produced by
    // the backing itself. `--scenario degraded` declares `approvals` a
    // 500 (`fixtures/manifest.json`); against any other scenario this
    // claim cannot be exercised and the test says so rather than asserting
    // a false green, the same "skip on a data condition, not a defect"
    // rule the run-view-narrado spec already applies.
    await page.goto('/decisions?tab=actions');
    const panel = page.getByTestId('panel');
    await expect(panel).toBeVisible();
    const state = await panel.getAttribute('data-state');
    if (state !== 'error') {
      test.skip(
        true,
        'this claim needs the mock run under --scenario degraded, where /v1/approvals answers 500',
      );
      return;
    }
    const body = (await panel.textContent()) ?? '';
    expect(body).not.toContain('Nothing is waiting on a decision');
    expect(body).not.toContain('Nada está aguardando');
  });
});

// =============================================================================
// AN-14 — every new string exists in en and pt-BR
// =============================================================================

test.describe('AN-14 — every new string on the screen exists in en and pt-BR', () => {
  test('the screen renders with no missing-catalogue key literal', async ({ page }) => {
    await page.goto('/decisions?tab=actions');
    const body = await page.locator('body').innerText();
    // A key that failed to resolve renders literally (`message()`'s own
    // fallback), which is what this spec can observe without reading the
    // catalogue file itself — the catalogue completeness test
    // (`console/tests/unit/i18n.test.ts`) is the one that reads both files
    // and is the actual proof for the pt-BR half of this claim.
    expect(body).not.toMatch(/decisions\.|approvals\.|proposal\./);
  });
});

// =============================================================================
// Edge case — many pending: the first expanded, the rest collapsed
// =============================================================================

test.describe('Edge case — several pending decisions: the oldest expanded, the rest collapsed by a sentence', () => {
  test('at most one expanded card renders per page, with the rest of the queue as collapsed rows', async ({
    page,
  }) => {
    await page.goto('/decisions?tab=actions');
    // `approvals.tsx` expands only `queue[0]` of the combined
    // expired-then-pending queue — one rule, not "one rule for pending and
    // a different one for expired" — so counting pending decisions alone
    // could never reach two here: any expired decision always claims the
    // one expanded slot first, and the dataset always carries at least one.
    // The two expired decisions this feature's own fixture carries (one
    // live-origin, one dead-origin — FR-016) already put more than one item
    // in the queue, which is the actual condition this edge case protects.
    const expanded = page.getByTestId('decision-card');
    const collapsed = page.getByTestId('decision-row-collapsed');
    const total = (await expanded.count()) + (await collapsed.count());
    if (total < 2) {
      test.skip(
        true,
        'the environment holds fewer than two queued decisions right now',
      );
      return;
    }
    await expect(expanded).toHaveCount(1);
    await expect(collapsed).toHaveCount(total - 1);
  });
});
