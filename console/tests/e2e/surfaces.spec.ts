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
  // The agent's own advanced section, not the retired generic editor. The
  // claim is the one it always was — the console draws what the deployment
  // resolved, never a figure of its own — and it belongs on a page that owns
  // its fields, because that is where every change is made now.
  //
  // `agents.tool_budget` specifically: this deployment's field catalogue is
  // what decides which controls exist, and that is one of the few it serves
  // that the real schema also declares.
  await page.goto('/agent?tab=topology');

  const advanced = page.getByTestId('advanced-config-agents');
  await expect(advanced).toBeVisible();
  // Collapsed on arrival, as every advanced section is; opened here because
  // this test is about what the control does, not about where it starts.
  // `.first()`: the editor inside groups its own fields into `<details>` too,
  // so the section's own summary is the one this opens.
  await advanced.locator('summary').first().click();

  // The effective value and where it was set, shown before anything is edited.
  await expect(advanced.getByTestId('effective-field').first()).toBeVisible();

  // Nothing to preview until something changes.
  await expect(advanced.getByTestId('ask-preview')).toBeDisabled();

  // Reached by name rather than by scrolling — the search is the path a page
  // with a hundred-odd fields offers, and typing the path is the acceptance
  // criterion this suite exists to hold to a real browser.
  await advanced
    .locator('input[name="config-field-search"]')
    .fill('agents.tool_budget');
  await advanced.locator('input[name="agents.tool_budget"]').fill('36');

  await advanced.getByTestId('ask-preview').click();

  // The values below are the deployment's, and the console has no arithmetic
  // that could have produced them: it asked, and it drew what came back.
  const change = advanced.getByTestId('preview-change').first();
  await expect(change).toBeVisible();
  await expect(change).toHaveAttribute('data-path', /\w/);
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

test('the four advanced policy sections stay collapsed and name their own fields', async ({
  page,
}) => {
  // A real production build, not a component render: this is exactly the
  // terrain where a server component consuming a `'use client'` module's
  // export has broken before — passing every unit test and only failing here.
  await page.goto('/knowledge');

  const changes = page.getByTestId('advanced-config-policies-changes');
  const access = page.getByTestId('advanced-config-policies-knowledge');
  const memory = page.getByTestId('advanced-config-policies-memory');
  const strategy = page.getByTestId('advanced-config-policies-strategy');

  for (const details of [changes, access, memory, strategy]) {
    await expect(details).toBeVisible();
    await expect(details).not.toHaveAttribute('open', '');
  }

  await changes.locator('summary').click();
  await expect(changes).toHaveAttribute('open', '');
  await expect(changes.getByText('Repository path')).toBeVisible();
});

test('the organisation tree has every node in it', async ({ page }) => {
  // The agent's Team tab, which is where the tree lives now that the raw
  // editor it used to share a screen with is retired.
  await page.goto('/agent?tab=team');

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
 *
 * Skipped, not deleted: the hybrid navigation redirects
 * `/signals?tab=intake` to Alert intake and `/signals?tab=destinations` to
 * Schedules & destinations (its own acceptance criteria require exactly
 * this), and neither Settings page has a screen of its own yet — each
 * renders the honest "not built" empty state until a later feature builds
 * it, so none of `ingress-source`, `simulate-payload`, `failed-delivery` or
 * `provenance` exists at any address a browser can reach any more. The
 * property every one of these six tests is proving — the deployment's own
 * answer for a webhook simulation, the save lock, the resend action, the
 * provenance chain — is unchanged in the screen underneath
 * (`console/src/surfaces/screens/data.tsx`, reached directly by
 * `console/tests/unit/surfaces/*.test.tsx`); only the address that used to
 * reach it in a browser is gone. Un-skip this block once Alert intake and
 * Schedules & destinations render that screen again.
 */
test.describe.skip('retired by the hybrid navigation, pending the Data pages', () => {
  test('a silent receiver is the first thing on the transit screen', async ({
    page,
  }) => {
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
    await expect(page.getByTestId('simulate-rule')).toContainText(
      'critical-to-platform',
    );
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
    await expect(live.getByTestId('provenance-run')).toHaveAttribute(
      'href',
      /^\/runs\//,
    );
  });
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
