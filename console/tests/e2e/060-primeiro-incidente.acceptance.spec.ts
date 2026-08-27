import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * What one incident's page has to show once this deployment can investigate:
 * the alert arriving, the reasoning that followed it, the evidence each
 * conclusion rests on, and a proposed action that declares its blast radius
 * and waits for a person.
 *
 * **Backing: `compose`.** A real gateway against a real database, not the
 * simulated data plane. This screen's whole subject is what an investigation
 * actually produced — how many steps it took, how long it ran, what it cost,
 * and which query supports which conclusion. Against a mock those numbers
 * prove only that somebody wrote a fixture with the right field names. The
 * two planes are also known to disagree here in a way that matters: the
 * demonstration seeder gives a timeline to exactly ONE incident — the one the
 * incident-detail capture details — and writes every other incident with an
 * empty timeline whatever the dataset holds for it. A timeline claim aimed at
 * any other incident would pass on the simulated plane and fail forever
 * against a real deployment.
 *
 * That is why the incident under test is not named here as a literal. It is
 * read from the dataset, from the same capture the seeder reads, so this file
 * keeps pointing at whichever incident is the detailed one. Making that
 * incident the investigated one the claims below describe is the fixture
 * task's job, not this file's.
 *
 * **This spec is expected to be comprehensively red when it is written**, and
 * that is its purpose. The five reasoning step kinds do not exist yet — the
 * incident timeline records lifecycle only. No investigated incident exists in
 * the dataset. The screen is still the previous one. Every other task in this
 * feature exists to turn one of these claims green. A claim weakened to pass
 * today would be a claim nobody ever has to satisfy.
 *
 * **Conventions this file invents, because the screen carries almost no test
 * hooks today and the implementation is expected to adopt these rather than
 * invent a second set:**
 *
 * - `incident-chip` — one per header chip. The count is asserted, not just
 *   the presence of two known words, so a third chip appearing is a failure.
 * - `investigation-step` — one per timeline step, each carrying `data-kind`
 *   of `receipt`, `hypotheses`, `evidence`, `diagnosis` or `delivery`, and
 *   each containing a `step-time`.
 * - `evidence-query` and `evidence-result` — the executed query and what came
 *   back, inside an evidence step. Two elements rather than one, because the
 *   claim is that both are shown, and one block containing both cannot tell
 *   the difference between that and a query with its result omitted.
 * - `decision-control` — one per control on the proposed-action card. The
 *   count is asserted at exactly two: the claim is that nothing else is
 *   offered at the moment of decision, and "Approve and Reject are both
 *   present" does not say that.
 *
 * Where a claim is about something being ABSENT or BOUNDED, it is written as a
 * count or an exact-text match rather than as the presence of the good thing.
 * An assertion that the right element exists proves nothing about the wrong
 * one being gone, and that specific gap is the most repeated defect this
 * console's test suite has produced.
 */

/**
 * The incident the dataset details, and so the only one seeded with a
 * timeline — both the internal key (asserted never to leak as a name) and
 * the public address the console now navigates by.
 */
function detailedIncident(): {
  readonly incidentId: string;
  readonly publicId: string;
} {
  const source = readFileSync(
    fileURLToPath(
      new URL(
        '../../../fixtures/scenarios/populated/incident-detail.json',
        import.meta.url,
      ),
    ),
    'utf8',
  );
  const captured = JSON.parse(source) as {
    responses: {
      body?: {
        incident?: { incident_id?: string; public_id?: string };
        investigation?: unknown;
      };
    }[];
  };
  // The investigated one specifically — never "whichever response happens
  // to be first once the file is written", which stopped being the same
  // thing the day the file started keying its own records by the public
  // address rather than the internal one, and sorted by it.
  for (const response of captured.responses) {
    const incidentId = response.body?.incident?.incident_id;
    const publicId = response.body?.incident?.public_id;
    if (
      typeof incidentId === 'string' &&
      incidentId !== '' &&
      typeof publicId === 'string' &&
      publicId !== '' &&
      response.body?.investigation !== null &&
      response.body?.investigation !== undefined
    ) {
      return { incidentId, publicId };
    }
  }
  throw new Error(
    'the incident-detail capture names no investigated incident, so no timeline is ever seeded',
  );
}

const { incidentId: INCIDENT_ID, publicId: INCIDENT_PUBLIC_ID } = detailedIncident();
const INCIDENT_ROUTE = `/incidents/${INCIDENT_PUBLIC_ID}`;

/** The five reasoning steps, in the order an investigation produces them. */
const STEP_ORDER = [
  'receipt',
  'hypotheses',
  'evidence',
  'diagnosis',
  'delivery',
] as const;

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? '');
});

test.describe('the incident page names what happened and what is proposed', () => {
  test('the header carries the trail, the title, and exactly two chips', async ({
    page,
  }) => {
    await page.goto(INCIDENT_ROUTE);

    await expect(page.getByTestId('incident-trail')).toBeVisible();
    await expect(page.getByTestId('incident-trail')).toContainText('Incidents');

    const title = page.getByTestId('incident-title');
    await expect(title).toBeVisible();
    await expect(title).not.toHaveText(INCIDENT_ID);

    // Exactly two: the incident's own state, and whether the investigation
    // finished. A third chip here is the header growing a status vocabulary
    // of its own, which is the thing this wave spent a feature removing.
    await expect(page.getByTestId('incident-chip')).toHaveCount(2);
    await expect(page.getByTestId('incident-chip').nth(0)).toHaveText('Open');
    await expect(page.getByTestId('incident-chip').nth(1)).toHaveText(
      'Investigation finished',
    );
  });

  test('the subtitle names the rule, the source, the instant, the zone and the host', async ({
    page,
  }) => {
    await page.goto(INCIDENT_ROUTE);

    const subtitle = page.getByTestId('incident-subtitle');
    await expect(subtitle).toBeVisible();

    // Five separate facts, each asserted on its own, so a subtitle that
    // dropped one of them fails on that one rather than on a whole string
    // somebody would have to diff by eye.
    await expect(subtitle.getByTestId('subtitle-rule')).not.toBeEmpty();
    await expect(subtitle.getByTestId('subtitle-source')).not.toBeEmpty();
    await expect(subtitle.getByTestId('subtitle-instant')).not.toBeEmpty();
    await expect(subtitle.getByTestId('subtitle-zone')).not.toBeEmpty();
    await expect(subtitle.getByTestId('subtitle-host')).not.toBeEmpty();
  });

  test('the page is two columns', async ({ page }) => {
    await page.goto(INCIDENT_ROUTE);

    await expect(page.getByTestId('incident-column')).toHaveCount(2);
  });
});

test.describe('the investigation card shows the reasoning, in order', () => {
  test('its header carries the step count, the duration and the cost', async ({
    page,
  }) => {
    await page.goto(INCIDENT_ROUTE);

    const summary = page.getByTestId('investigation-summary');
    await expect(summary).toBeVisible();

    // Each read separately: when one of the three does not exist it is meant
    // to be omitted rather than rendered as zero, and a single combined string
    // cannot express the difference between "cost is absent" and "cost is $0".
    await expect(summary.getByTestId('summary-steps')).not.toBeEmpty();
    await expect(summary.getByTestId('summary-duration')).not.toBeEmpty();
    await expect(summary.getByTestId('summary-cost')).not.toBeEmpty();
  });

  test('the five kinds of step appear in chronological order', async ({ page }) => {
    await page.goto(INCIDENT_ROUTE);

    const steps = page.getByTestId('investigation-step');
    await expect(steps.first()).toBeVisible();

    const kinds = await steps.evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('data-kind') ?? ''),
    );

    // The order of first appearance, not the raw list: an investigation may
    // check several things, so evidence legitimately repeats. What may not
    // happen is a diagnosis before the evidence that supports it.
    const firstAppearance = [...new Set(kinds)];
    expect(firstAppearance).toEqual([...STEP_ORDER]);
  });

  test('every step says when it happened', async ({ page }) => {
    await page.goto(INCIDENT_ROUTE);

    const steps = page.getByTestId('investigation-step');
    const total = await steps.count();
    expect(total).toBeGreaterThan(0);

    for (let index = 0; index < total; index += 1) {
      await expect(steps.nth(index).getByTestId('step-time')).not.toBeEmpty();
    }
  });

  test('the receipt step shows the labels that arrived and names the delivery token', async ({
    page,
  }) => {
    await page.goto(INCIDENT_ROUTE);

    const receipt = page.locator(
      '[data-testid="investigation-step"][data-kind="receipt"]',
    );
    await expect(receipt).toHaveCount(1);

    const labels = receipt.getByTestId('step-labels');
    await expect(labels).toBeVisible();
    await expect(labels).toHaveCSS('font-family', /mono/i);

    // The credential's display name, never its value. The token is what
    // authenticated the delivery; a page that showed the secret would have
    // published it to everyone who can read the incident.
    const token = receipt.getByTestId('delivery-token-name');
    await expect(token).not.toBeEmpty();
    await expect(token).not.toContainText('nsre_');
  });

  test('the hypotheses are listed', async ({ page }) => {
    await page.goto(INCIDENT_ROUTE);

    const hypotheses = page.getByTestId('hypothesis');
    expect(await hypotheses.count()).toBeGreaterThan(1);
  });

  test('each evidence step shows the query it ran and the result it got', async ({
    page,
  }) => {
    await page.goto(INCIDENT_ROUTE);

    const evidence = page.locator(
      '[data-testid="investigation-step"][data-kind="evidence"]',
    );
    const total = await evidence.count();
    expect(total).toBeGreaterThan(0);

    for (let index = 0; index < total; index += 1) {
      await expect(evidence.nth(index).getByTestId('evidence-query')).not.toBeEmpty();
      await expect(evidence.nth(index).getByTestId('evidence-result')).not.toBeEmpty();
    }
  });

  test('the diagnosis is one sentence', async ({ page }) => {
    await page.goto(INCIDENT_ROUTE);

    const diagnosis = page.locator(
      '[data-testid="investigation-step"][data-kind="diagnosis"]',
    );
    await expect(diagnosis).toHaveCount(1);

    const said = (await diagnosis.getByTestId('step-detail').innerText()).trim();
    expect(said.length).toBeGreaterThan(0);

    // One sentence: a full stop may end it, but may not appear mid-way with
    // more text after it. A diagnosis that grew into a paragraph is a
    // diagnosis nobody can act on at a glance.
    expect(said.replace(/\.$/, '')).not.toMatch(/[.!?]\s+\S/);
  });

  test('the delivery step names where the report went', async ({ page }) => {
    await page.goto(INCIDENT_ROUTE);

    const delivery = page.locator(
      '[data-testid="investigation-step"][data-kind="delivery"]',
    );
    await expect(delivery).toHaveCount(1);
    expect(await delivery.getByTestId('delivery-destination').count()).toBeGreaterThan(
      0,
    );
  });
});

test.describe('the proposed action declares its reach and waits', () => {
  test('the card states the action, its blast radius and the posture', async ({
    page,
  }) => {
    await page.goto(INCIDENT_ROUTE);

    const card = page.getByTestId('proposed-action');
    await expect(card).toBeVisible();

    await expect(card.getByTestId('decision-state')).toHaveText('Awaiting decision');
    await expect(card.getByTestId('action-sentence')).not.toBeEmpty();

    // How many resources, in which zone, at what criticality. Three facts,
    // because "one container" without a zone or a criticality is not a blast
    // radius, it is a count.
    const radius = card.getByTestId('blast-radius');
    await expect(radius.getByTestId('radius-resources')).not.toBeEmpty();
    await expect(radius.getByTestId('radius-zone')).not.toBeEmpty();
    await expect(radius.getByTestId('radius-criticality')).not.toBeEmpty();

    await expect(card.getByTestId('posture')).toContainText('propose-only');
  });

  test('it offers exactly two controls and neither has run anything', async ({
    page,
  }) => {
    await page.goto(INCIDENT_ROUTE);

    const card = page.getByTestId('proposed-action');
    const controls = card.getByTestId('decision-control');

    // Exactly two. The claim is about what is NOT offered at the moment of
    // decision — a third control here would be a way to act that the posture
    // never announced.
    await expect(controls).toHaveCount(2);
    await expect(controls.nth(0)).toHaveText('Approve and run');
    await expect(controls.nth(1)).toHaveText('Reject');

    // Still awaiting: rendering the card must not itself have decided or
    // executed anything.
    await expect(card.getByTestId('decision-state')).toHaveText('Awaiting decision');
  });
});

test.describe('the evidence trail is reachable', () => {
  test('the card points at the full run', async ({ page }) => {
    await page.goto(INCIDENT_ROUTE);

    const trail = page.getByTestId('evidence-trail');
    await expect(trail).toBeVisible();

    const link = trail.getByRole('link');
    await expect(link).toHaveCount(1);
    await expect(link).toHaveAttribute('href', /\/runs\//);
  });
});
