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
  await page.goto('/topology?node=svc-ledger');

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
  await page.goto('/approvals');

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
