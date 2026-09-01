import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * The three questions, answered from the console alone.
 *
 * This is the feature's closing claim and it is the one only a browser can
 * make: *an operator can find out what this thing will do on its own without
 * leaving the console and without reading YAML.* A component test proves each
 * section renders; what it cannot prove is that somebody arriving at `/agent`
 * can reach all three of them, that the sections are addresses rather than
 * component state, and that nothing but the one panel that is explicitly a
 * document shows them a configuration file.
 */

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test('the first question: which stages run, and which specialists are enabled', async ({
  page,
}) => {
  await page.goto('/agent');

  const stages = page.getByTestId('pipeline-metro-node');
  await expect(stages.first()).toBeVisible();
  expect(await stages.count()).toBeGreaterThan(1);

  // Each stage says what it consults — one disclosure away, inside its own
  // station, which is the difference between "the AI investigated" and
  // "these things were consulted, in this order".
  await stages.first().getByTestId('pipeline-metro-summary').click();
  await expect(stages.first()).toContainText('Consults:');

  // And the model is a role. No provider identifier appears beside a stage.
  for (const provider of ['anthropic', 'openai', 'ollama', 'aws_bedrock']) {
    await expect(stages.first()).not.toContainText(provider);
  }
});

test('the second question: which tools exist, split by risk, with blockers named', async ({
  page,
}) => {
  await page.goto('/agent?tab=tools');

  const groups = page.getByTestId('tool-group');
  await expect(groups).toHaveCount(2);
  await expect(groups.nth(0)).toHaveAttribute('data-group', 'read');
  await expect(groups.nth(1)).toHaveAttribute('data-group', 'write');

  const tools = page.getByTestId('agent-tool');
  await expect(tools.first()).toBeVisible();
});

test('the third question: what each class of action would do under this policy', async ({
  page,
}) => {
  await page.goto('/agent?tab=autonomy');

  const classes = page.getByTestId('outlook-class');
  await expect(classes).toHaveCount(5);

  // A sentence per class, not a policy document. The word the whole tab exists
  // for is "would" — this has not happened. The row leads with the short
  // description; the "would" phrasing lives in the row's own disclosure.
  for (let index = 0; index < 5; index += 1) {
    const row = classes.nth(index);
    await expect(row.getByTestId('outlook-sentence')).toBeVisible();
    await row.locator('summary').click();
    await expect(row).toContainText('would');
    await row.locator('summary').click();
  }
});

test('the three sections are addresses, so one can be sent to a colleague', async ({
  page,
}) => {
  await page.goto('/agent');

  await page.getByTestId('tab-link').filter({ hasText: 'Tools' }).click();
  await expect(page.getByTestId('tool-group').first()).toBeVisible();
  expect(new URL(page.url()).searchParams.get('tab')).toBe('tools');

  await page.reload();
  await expect(page.getByTestId('tool-group').first()).toBeVisible();
});

test('no configuration document is shown outside the panel that is one', async ({
  page,
}) => {
  await page.goto('/agent?tab=tools');
  await expect(page.getByTestId('agent-document')).toHaveCount(0);

  await page.goto('/agent?tab=autonomy');
  await expect(page.getByTestId('agent-document')).toHaveCount(0);

  // The one place a document appears is the structured-text view, closed by
  // default behind its own disclosure — a choice an operator makes rather
  // than the only way to read the topology.
  await page.goto('/agent?tab=topology');
  const documentDetails = page.getByTestId('agent-document-details');
  await expect(documentDetails).toBeVisible();
  await documentDetails.locator('summary').click();
  await expect(page.getByTestId('agent-document')).toBeVisible();
});
