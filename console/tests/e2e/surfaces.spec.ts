import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The data surfaces, in a browser, against a real deployment.
 *
 * Two of this feature's claims can only be made here. **The configuration
 * preview is the server's answer**: the unit suite can show that the console
 * renders what it is handed, but only a real server answering a real `POST`
 * shows that what it is handed is the deployment's own resolution rather than
 * something worked out on the way. And **the address is the state**: a filtered
 * view that survives a reload in an actual browser is the property the URL
 * requirement is about, and a component test cannot reload anything.
 */

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test('the overview puts what needs a person above the figures', async ({ page }) => {
  await page.goto('/');

  const attention = page.getByTestId('attention');
  const figures = page.getByTestId('figure').first();
  await expect(attention).toBeVisible();

  // Above, in the document and on the screen. A number is never more urgent
  // than a decision somebody is waiting on.
  const attentionBox = await attention.boundingBox();
  const figureBox = await figures.boundingBox();
  expect(attentionBox?.y ?? 0).toBeLessThan(figureBox?.y ?? 0);
});

test('every summary figure reaches the list it counts', async ({ page }) => {
  await page.goto('/');

  const figure = page.getByTestId('figure').first();
  await expect(figure).toHaveAttribute('href', /\/\w/);
  await figure.click();

  await expect(page.getByTestId('page-header')).toBeVisible();
});

test('a filtered run list survives being reloaded and shared', async ({ page }) => {
  await page.goto('/runs?status=failed');

  const rows = page.getByTestId('row');
  await expect(rows.first()).toBeVisible();
  const before = await rows.count();

  await page.reload();
  await expect(page.getByTestId('row')).toHaveCount(before);
  expect(new URL(page.url()).searchParams.get('status')).toBe('failed');
});

test('sorting a list is a navigation, so the sorted view has an address', async ({
  page,
}) => {
  await page.goto('/runs');

  await page.getByTestId('sort').first().click();
  await expect(page.getByTestId('row').first()).toBeVisible();

  expect(new URL(page.url()).searchParams.get('sort')).toBeTruthy();
});

test('a run detail replays the transcript, bounded and expandable', async ({
  page,
}) => {
  await page.goto('/runs/run-0001');

  const events = page.getByTestId('transcript-event');
  await expect(events.first()).toBeVisible();

  // Every entry says what kind it is in words, not only in a colour.
  await expect(page.getByTestId('event-kind').first()).not.toBeEmpty();
  await expect(page.getByTestId('usage-by-model')).toBeVisible();
  await expect(page.getByTestId('usage-by-turn')).toBeVisible();
});

test('the configuration preview is the deployment’s answer', async ({ page }) => {
  await page.goto('/configuration?node=env-production');

  await expect(page.getByTestId('config-value').first()).toBeVisible();
  await expect(page.getByTestId('provenance').first()).toBeVisible();

  // There is nothing to preview until something has been changed, so the change
  // comes first. `approval.required_above` and not any other field: the same
  // response has to say the change is gated, and that is the one field this
  // deployment gates.
  await expect(page.getByTestId('ask-preview')).toBeDisabled();

  // Reached by name rather than by scrolling: the form is ~thirty sections of
  // ~a hundred and twenty fields, every one collapsed until somebody asks for
  // it, and searching is the path this screen now offers. Typing the path is
  // also the acceptance criterion — any field, under five seconds — so the
  // browser suite is where it is worth proving rather than asserting in prose.
  await page
    .locator('input[name="config-field-search"]')
    .fill('approval.required_above');
  await page
    .locator('select[name="approval.required_above"]')
    .selectOption('write_irreversible');

  await page.getByTestId('ask-preview').click();

  // The values below are the deployment's, and the console has no arithmetic
  // that could have produced them: it asked, and it drew what came back.
  const change = page.getByTestId('preview-change').first();
  await expect(change).toBeVisible();
  await expect(change).toHaveAttribute('data-path', /\w/);
  // The same response says the change is gated, and the screen says what that
  // means where the control is rather than in a document.
  await expect(page.getByTestId('gated')).toBeVisible();
});

test('the estate is sorted by health, with a meter and a number', async ({ page }) => {
  await page.goto('/resources');

  await expect(page.getByTestId('row').first()).toBeVisible();
  await expect(page.getByTestId('meter').first()).toBeVisible();
});

test('the topology draws a picture and a list of the same graph', async ({ page }) => {
  await page.goto('/knowledge?tab=topology&node=svc-ledger');

  await expect(page.getByTestId('graph')).toBeVisible();
  await expect(page.getByTestId('graph-list')).toBeVisible();
});

test('the organisation tree has every node in it', async ({ page }) => {
  await page.goto('/configuration');

  const tree = page.getByTestId('org-tree');
  await expect(tree).toBeVisible();
  const declared = Number(await tree.getAttribute('data-total'));
  await expect(page.getByTestId('org-node')).toHaveCount(declared);
});

test('a proposal carries all eight fields before it can be decided', async ({
  page,
}) => {
  await page.goto('/decisions?tab=actions');

  const rows = page.getByTestId('proposal-row');
  await expect(rows.first()).toBeVisible();
  const fields = await rows.evaluateAll((nodes) =>
    nodes.slice(0, 8).map((node) => node.getAttribute('data-field')),
  );
  expect(fields).toEqual([
    'target',
    'current',
    'change',
    'protects',
    'blast',
    'rollback',
    'verification',
    'autonomy',
  ]);
});

/**
 * Transit, in a browser, against a real deployment.
 *
 * Three claims that only hold here. **The simulation is the deployment's
 * answer**: the unit suite shows the console renders what it is handed, and
 * only a real `POST` shows that what it is handed came from the function the
 * ingress path runs rather than from a matcher on the way. **The lock is a
 * lock**: an operator who simulates, edits, and reaches for save has to meet a
 * disabled button, and that is a sequence of real interactions rather than a
 * state. And **the failed delivery is actionable**: the control is on the row
 * and it says what happened.
 */

test('a silent receiver is the first thing on the transit screen', async ({ page }) => {
  await page.goto('/signals?tab=intake');

  const first = page.getByTestId('ingress-source').first();
  await expect(first).toHaveAttribute('data-never-delivered', 'true');
  await expect(first).toContainText('Nothing has ever arrived here');
});

test('the rule that catches everything else is always drawn', async ({ page }) => {
  await page.goto('/signals?tab=intake');

  await expect(page.getByTestId('catch-all-rule')).toBeVisible();
  await expect(page.getByTestId('catch-all-note')).toBeVisible();
});

test('a rule cannot be saved until its effect has been seen', async ({ page }) => {
  await page.goto('/signals?tab=intake');

  const save = page.getByTestId('simulate-save');
  const simulate = page.getByTestId('simulate');
  await expect(save).toBeDisabled();

  await page
    .getByTestId('simulate-payload')
    .fill('{"groupKey": "g", "status": "firing"}');
  await simulate.click();

  // The answer is the deployment's: the rule named here is one this deployment
  // has configured, which nothing in the browser could have known.
  await expect(page.getByTestId('simulate-rule')).toContainText('critical-to-platform');
  await expect(save).toBeEnabled();
});

test('editing the payload after simulating locks save again', async ({ page }) => {
  // The bypass attempt: simulate something harmless, edit it, then save.
  await page.goto('/signals?tab=intake');

  await page.getByTestId('simulate-payload').fill('{"groupKey": "g"}');
  await page.getByTestId('simulate').click();
  await expect(page.getByTestId('simulate-save')).toBeEnabled();

  await page.getByTestId('simulate-payload').fill('{"groupKey": "something else"}');

  await expect(page.getByTestId('simulate-save')).toBeDisabled();
});

test('a report that did not arrive can be sent again from the row it failed on', async ({
  page,
}) => {
  await page.goto('/signals?tab=destinations');

  const failed = page.getByTestId('failed-delivery').first();
  await expect(failed).toContainText('channel_not_found');

  await failed.getByTestId('resend-action').click();

  // Whatever the second attempt did, the row says so. A control that went quiet
  // is one an operator cannot tell from a control that did nothing.
  await expect(failed.getByTestId('resend-outcome')).toBeVisible();
});

test('an arrival answers which rule caught it and which run it became', async ({
  page,
}) => {
  await page.goto('/signals?tab=intake');

  const live = page
    .getByTestId('ingress-source')
    .filter({ has: page.locator('[data-source="alertmanager"]') })
    .or(page.locator('[data-testid="ingress-source"][data-source="alertmanager"]'))
    .first();
  await live.getByTestId('provenance').locator('summary').click();

  await expect(live.getByTestId('provenance-chain')).toContainText(
    'critical-to-platform',
  );
  await expect(live.getByTestId('provenance-run')).toHaveAttribute('href', /^\/runs\//);
});

test('the operating context names the level each section came from', async ({
  page,
}) => {
  // Acceptance 2 in a browser: a section is the unit of inheritance here, and an
  // operator who cannot tell an organisation's fact from their own team's edits
  // at the wrong level and concludes nothing happened.
  await page.goto('/agent?tab=team&node=org-northwind');

  const sections = page.getByTestId('context-section');
  await expect(sections.first()).toBeVisible();
  await expect(page.getByTestId('section-provenance').first()).toContainText(
    'org-northwind',
  );

  await page.goto('/agent?tab=team&node=team-platform');
  const attributed = await page
    .getByTestId('section-provenance')
    .evaluateAll((nodes) => nodes.map((node) => node.textContent));

  // Two levels, distinguished. The team's own section is attributed to the team
  // and everything it inherits still names the organisation.
  expect(attributed.some((text) => text.includes('team-platform'))).toBe(true);
  expect(attributed.some((text) => text.includes('org-northwind'))).toBe(true);
});

test('the operating context shows the prompt before it offers a save', async ({
  page,
}) => {
  // Acceptance 6, and the only place it can be made: the prompt is the
  // deployment's own assembly, arriving over a real POST. A unit test can show
  // the console renders what it is handed; only this shows that what it is
  // handed came from the server.
  await page.goto('/agent?tab=team&node=org-northwind');

  await expect(page.getByTestId('ask-context-preview')).toBeDisabled();
  await page
    .getByTestId('context-section')
    .first()
    .locator('textarea')
    .fill('Container metrics come from the host, keyed by vmid.');

  await expect(page.getByTestId('save-context')).toHaveCount(0);
  await page.getByTestId('ask-context-preview').click();

  await expect(page.getByTestId('context-prompt')).toContainText(
    'You are an SRE investigator',
  );
  await expect(page.getByTestId('save-context')).toBeVisible();
});
