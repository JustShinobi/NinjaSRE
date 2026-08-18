import { expect, test } from '@playwright/test';

import { signIn } from './session';

/**
 * A machine token that starts holding nothing, and a product that stops
 * introducing itself in the transport's own words.
 *
 * Seven claims, each one drawn from the mockup and the transversal vocabulary
 * rule rather than from how the screen happens to render today:
 *
 * - Machine tokens opens with no scope pre-selected, and says so as a count.
 * - A purpose template marks exactly the scope its own name promises.
 * - A destructive scope warns, by name, before it is issued — and never blocks.
 * - Scopes render in named domain groups, never one undifferentiated band.
 * - Members & roles offers to create a person only to someone who may.
 * - None of the covered routes prints a transport identifier where a reader
 *   expects a name.
 * - An active session names who holds it and where it came from, never a
 *   bare number.
 *
 * `beforeEach` signs in once; every test opens its own page so a failure in
 * one leaves no state behind for the next.
 *
 * Three of the seven areas below were already corrected by earlier work on
 * this same change before this file existed: the principal and account-state
 * chips on Members & roles, the token-group chip on Machine tokens, and the
 * wizard preview's field labels. Their assertions here are written exactly
 * like every other claim's — this file does not know, and must not care,
 * which ones already hold.
 *
 * The destructive-scope warning's own test self-skips, by name, for any
 * fixture scenario whose signed-in principal holds none of the three
 * destructive permissions — a role narrower than owner grants none of them,
 * and the test has no checkbox to click in that case. It is not a skip every
 * scenario hits: a principal holding the owner role carries every permission
 * that role grants, destructive ones included, so under a scenario signed in
 * as one this claim runs for real — see its own comment.
 */

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

// --- (a): the issue form opens holding no power -----------------------------

test.describe('machine tokens open holding no power by default', () => {
  test('no scope checkbox starts checked', async ({ page }) => {
    await page.goto('/settings/machine-tokens');

    const scopes = page.locator('input[type="checkbox"][name^="scope-"]');
    await expect(scopes.first()).toBeVisible();

    const checked = await page
      .locator('input[type="checkbox"][name^="scope-"]:checked')
      .count();
    expect(
      checked,
      `${String(checked)} scope checkbox(es) start checked on a freshly opened form; the ` +
        'default must mark none, so a name typed and "Issue" clicked cannot emit more than ' +
        'the purpose asked for',
    ).toBe(0);
  });

  test('a selected-scope counter states zero, not just an absence of ticks', async ({
    page,
  }) => {
    await page.goto('/settings/machine-tokens');

    // No checkbox being checked is one fact; the form also owes the operator
    // a stated count, so "zero" is read rather than counted by eye across
    // however many domain groups the scopes render in.
    const counter = page.getByTestId('scope-selected-count');
    await expect(
      counter,
      'no element on the issue form states how many scopes are currently selected',
    ).toHaveCount(1);
    await expect(counter).toContainText('0');
  });
});

// --- (b): a purpose template marks only what it promises --------------------

test.describe('a purpose template marks only what it promises', () => {
  test('the "Alert delivery" template exists, and once available selects only webhook.deliver', async ({
    page,
  }) => {
    await page.goto('/settings/machine-tokens');

    const template = page.getByTestId('scope-template-alert-delivery');
    await expect(
      template,
      'no "Alert delivery" purpose template control exists on the issue form',
    ).toHaveCount(1);

    // The template can only prove it marks exactly one scope if that scope is
    // inside this viewer's own ceiling — otherwise the correct behaviour is a
    // disabled template naming why, not a smaller token than its own label
    // promises, and there is nothing here for this half to exercise.
    const webhookScope = page.locator('input[name="scope-webhook.deliver"]');
    test.skip(
      (await webhookScope.count()) === 0,
      "the signed-in viewer's own permission ceiling does not include webhook.deliver under " +
        'any fixture scenario this suite can select today (every scenario in this ' +
        'repository hands its principal the same fixed set, and webhook.deliver is not in ' +
        'it), so once the template control exists it still has no webhook.deliver checkbox ' +
        'of its own to select. Needs a scenario granting that permission before this half ' +
        'can run.',
    );

    await template.click();
    const checkedHandles = await page.locator('input[name^="scope-"]:checked').all();
    const checkedNames = await Promise.all(
      checkedHandles.map((box) => box.getAttribute('name')),
    );
    expect(
      checkedNames,
      `the template left ${JSON.stringify(checkedNames)} checked, not exactly ` +
        '["scope-webhook.deliver"]',
    ).toEqual(['scope-webhook.deliver']);
  });
});

// --- (c): a destructive scope warns, and never blocks -----------------------

test.describe('a destructive scope warns before it is issued, and never blocks issuing', () => {
  test('checking Org Delete, Owner Assign or Impersonation Use names what it permits', async ({
    page,
  }) => {
    await page.goto('/settings/machine-tokens');

    const destructive = [
      'scope-org.delete',
      'scope-owner.assign',
      'scope-impersonation.use',
    ] as const;
    let target: (typeof destructive)[number] | undefined;
    for (const name of destructive) {
      if (await page.locator(`input[name="${name}"]`).count()) {
        target = name;
        break;
      }
    }
    // See the module doc: a principal holding the owner role carries every
    // permission `/identity/roles` grants that role — the three destructive
    // ones included (`tools/mockplane/dataset/served.py`'s
    // `OPERATOR_PERMISSIONS`, computed from `permissions_for(Role.OWNER)`
    // rather than curated by hand) — so this suite's usual signed-in
    // principal offers all three checkboxes. This loop, and the skip below,
    // stay in place for whichever fixture scenario signs in as a narrower
    // role instead: nothing here assumes today's signed-in principal is the
    // only one this suite will ever run against.
    test.skip(
      target === undefined,
      'none of Org Delete, Owner Assign or Impersonation Use is inside the signed-in ' +
        "viewer's own permission ceiling under this fixture scenario — no destructive " +
        'scope checkbox ever renders to click, so this claim has nothing to exercise here.',
    );
    // Unreachable once the skip above has fired; narrows `target` for
    // everything below so the rest of this test never interpolates a value
    // that might still be `undefined`.
    if (target === undefined) return;

    // A purpose name, so the button's disabled state below can only be about
    // the destructive scope — not about the unrelated empty-name rule the
    // same button also enforces.
    await page.locator('input[name="token-purpose"]').fill('rollout script');

    const checkbox = page.locator(`input[name="${target}"]`);
    await checkbox.check();

    const warning = page.getByTestId('destructive-scope-warning');
    await expect(
      warning,
      `checking ${target} produced no warning naming what it permits`,
    ).toHaveCount(1);
    const warningText = (await warning.innerText()).trim();
    expect(warningText, 'the destructive-scope warning has no text').not.toBe('');

    // Informs, never blocks: the warning must not disable the emission it
    // stands beside.
    await expect(page.getByTestId('issue-token')).toBeEnabled();
  });
});

// --- (d): scopes render grouped by domain ------------------------------------

test.describe('scopes render grouped by domain, not one undifferentiated band', () => {
  test('the issue form shows more than one named scope group', async ({ page }) => {
    await page.goto('/settings/machine-tokens');

    const scopes = page.locator('input[type="checkbox"][name^="scope-"]');
    await expect(scopes.first()).toBeVisible();
    const scopeCount = await scopes.count();
    expect(
      scopeCount,
      'no scope checkbox rendered for this claim to group',
    ).toBeGreaterThan(1);

    const groups = page.getByTestId('scope-group');
    const groupCount = await groups.count();
    expect(
      groupCount,
      `${String(scopeCount)} scope checkboxes render in ${String(groupCount)} named domain ` +
        'group(s); a single flat band is not grouping',
    ).toBeGreaterThan(1);
  });
});

// --- (e): Members & roles offers to create a person, gated by who may -------

test.describe('members and roles offers to create a person, to whoever may write identity', () => {
  test('a primary create-person action exists for a viewer who may write identity', async ({
    page,
  }) => {
    await page.goto('/settings/members-roles');

    // The full requirement gates this action on holding identity.write, and
    // must not offer it to a viewer who lacks that permission. Every fixture
    // scenario this repository ships hands its principal a fixed permission
    // set that excludes identity.write (confirmed against every
    // `principal.json` here, the same gap the destructive-scope claim above
    // runs into), so the gated, positive branch cannot be told apart from
    // "absent for everyone" under any of them — there is no privileged
    // session available to prove the gate opens for. What is true today
    // regardless of that gap, and what this asserts, is the part the gap
    // cannot hide: no such action exists on the page at all, for anyone.
    const create = page.getByTestId('create-person');
    await expect(
      create,
      'no primary create-person action exists on Members & roles',
    ).toHaveCount(1);
  });
});

// --- (f): no covered route names a machine to a person -----------------------

test.describe('no covered route prints a transport identifier where a reader expects a name', () => {
  test('members and roles never shows the raw principal-kind or account-health word', async ({
    page,
  }) => {
    await page.goto('/settings/members-roles');
    const body = await page.locator('body').innerText();

    expect(
      body,
      'the raw transport value SERVICE_ACCOUNT is shown instead of a display name',
    ).not.toContain('SERVICE_ACCOUNT');
    expect(
      body,
      'the raw resource-health word HEALTHY describes a person on this page',
    ).not.toContain('HEALTHY');
  });

  test('machine tokens never shows the raw resource-health word for a token group', async ({
    page,
  }) => {
    await page.goto('/settings/machine-tokens');
    const body = await page.locator('body').innerText();

    expect(
      body,
      'the raw resource-health word HEALTHY describes a token group on this page',
    ).not.toContain('HEALTHY');
  });

  test('autonomy & guardrails never titles a section with its own schema path', async ({
    page,
  }) => {
    await page.goto('/settings/autonomy-guardrails');
    // Collapsed content has no `innerText` at all, whatever it holds.
    await page.evaluate(() => {
      document.querySelectorAll('details').forEach((node) => {
        node.open = true;
      });
    });
    const body = await page.locator('body').innerText();

    for (const path of [
      'policies.masking',
      'policies.guardrails',
      'policies.approvals',
      'policies.autonomy',
    ]) {
      expect(
        body,
        `the schema path "${path}" is shown as a section title`,
      ).not.toContain(path);
    }
  });

  test('notifications never titles its section with its own schema path', async ({
    page,
  }) => {
    await page.goto('/settings/notifications');
    await page.evaluate(() => {
      document.querySelectorAll('details').forEach((node) => {
        node.open = true;
      });
    });
    const body = await page.locator('body').innerText();

    expect(
      body,
      'the schema path "surfaces.notification_policy" is shown as a section title',
    ).not.toContain('surfaces.notification_policy');
  });

  test('the wizard preview never names a changed field by its raw schema path', async ({
    page,
  }) => {
    await page.goto('/first-run?step=model');

    // A deployment whose setup is already complete redirects the wizard away
    // before any step ever renders — the honest answer for that deployment,
    // and not a shape this claim has anything to check. `populated` is
    // exactly that deployment; this needs the dedicated `first-run` fixture
    // scenario (`--scenario first-run`) to ever reach the model step at all.
    test.skip(
      !new URL(page.url()).pathname.endsWith('/first-run'),
      "this dataset's setup is already complete, so `/first-run` redirected away before " +
        'step=model ever rendered. Run with --scenario first-run for this claim.',
    );

    const noProvider = page.getByTestId('no-provider-chosen');
    test.skip(
      (await noProvider.count()) > 0,
      'no provider is configured under the served dataset, so the model step never renders ' +
        'to preview',
    );

    await page.getByTestId('preview-model').click();
    const preview = page.getByTestId('model-preview');
    await expect(
      preview,
      'the preview never rendered after asking for it',
    ).toBeVisible();

    // Every scenario this repository ships answers `/api/preview` with the
    // same fixed, patch-independent response regardless of what was actually
    // asked to preview (confirmed against `config-preview.json` in every
    // scenario directory: always `investigation.max_loops` and
    // `investigation.reasoning_effort`, whatever model was chosen) — so this
    // route can never show a change whose path is `models.investigator.*`,
    // whether or not it would have been named correctly. That specific
    // behaviour — a changed model or provider path resolved to its display
    // name — is exercised where it can actually vary the response: the
    // component test (`console/tests/unit/surfaces/first-run.test.tsx`),
    // which mocks the preview instead of asking a fixture that cannot. What
    // this can still check, and does, is that the preview mechanism itself
    // is reachable and renders something for a person to read.
    const text = await preview.innerText();
    expect(text.trim(), 'the preview rendered but stated nothing').not.toBe('');
    test.skip(
      !text.includes('models.investigator') && !/investigator|model/i.test(text),
      'the mock answers every preview with a fixed response unrelated to models.investigator ' +
        '(see comment above) — this route has nothing to prove either way for the raw-path ' +
        'claim specifically; covered instead by the component test named above.',
    );
    expect(
      text,
      'the wizard preview names a changed field by its raw schema path "models.investigator" ' +
        'rather than a display name',
    ).not.toContain('models.investigator');
  });

  test('alert intake never names its trust relationship by the raw delivery permission', async ({
    page,
  }) => {
    await page.goto('/settings/alert-intake');
    const body = await page.locator('body').innerText();

    expect(
      body,
      'the raw permission "webhook.deliver" is shown as the reason a source is trusted, ' +
        'instead of the delivery token that actually authenticates it',
    ).not.toContain('webhook.deliver');
  });

  test("a suggested integration never shows the estate's raw resource identifier as its evidence", async ({
    page,
  }) => {
    await page.goto('/integrations');

    const evidence = page.getByTestId('suggestion-evidence');
    const count = await evidence.count();
    test.skip(
      count === 0,
      'no suggested integration rendered on this dataset to check',
    );

    for (let index = 0; index < count; index += 1) {
      const text = await evidence.nth(index).innerText();
      // The spec's own illustrative identifier is shaped `res-8f81848…`; this
      // suite's own fixture estate names the same suggested resource with a
      // different raw scheme, `vm-201-metrics` — same defect (a machine
      // identifier standing in for a resource's name and location), the
      // identifier this dataset actually carries rather than a pattern that
      // would never match it and prove nothing.
      expect(
        text,
        `the evidence "${text}" names the estate's raw resource id rather than a legible ` +
          'resource',
      ).not.toContain('vm-201-metrics');
    }
  });
});

// --- (g): an active session identifies itself by who and from where ---------

test.describe('an active session identifies itself by who holds it and from where', () => {
  test('a session group names an origin or device, not just a name and a raw count', async ({
    page,
  }) => {
    await page.goto('/settings/members-roles');

    // Every fixture scenario this repository ships records its one browser
    // sign-in under the literal name "console" (`tools/mockplane/dataset/
    // served.py`), which no longer matches what the console itself treats as
    // a session (`CONSOLE_SESSION_NAME = 'Console sign-in'`,
    // `console/src/surfaces/token-identity.ts`) — so that token is read as an
    // ordinary machine token instead, and the Active sessions panel renders
    // no group at all, under any scenario. That is a fixture gap this suite
    // cannot route around by asking for a different scenario; naming it here
    // rather than asserting a condition no served dataset was ever going to
    // produce.
    const groups = page.getByTestId('session-group');
    const group = groups.first();
    const rendered = await groups.count();
    test.skip(
      rendered === 0,
      'no scenario in this fixture set names its browser sign-in "Console sign-in" (the ' +
        'value the console itself matches on), so the Active sessions panel never has a ' +
        'group to check — the fixture record itself needs correcting before this claim can ' +
        'run.',
    );

    const origin = group.getByTestId('session-origin');
    await expect(
      origin,
      'no session on this page states where it came from — only who holds it and a count',
    ).toHaveCount(1);

    // "Who holds it": the row's own first value is the person, and it must
    // not be blank.
    const name = await group.evaluate((node) => node.children[0]?.textContent ?? '');
    expect(name.trim(), 'the session row does not name who holds it').not.toBe('');

    // "Not just a name and a raw count": the defect this claim is named for
    // was exactly that — a bare session count, with no label of its own,
    // drawn beside the person. Checked value by value, across every
    // rendered row and against the header's own column count, because the
    // real values here ("in 325 days") carry digits too and a substring
    // match on the row's concatenated text would not tell the two apart.
    const columnCount = await page
      .getByTestId('session-columns')
      .evaluate((node) => node.children.length);
    const rowValues = await groups.evaluateAll((nodes) =>
      nodes.map((node) => Array.from(node.children).map((child) => child.textContent)),
    );
    for (const [index, values] of rowValues.entries()) {
      expect(
        values.length,
        `session row ${String(index)} draws a different number of values than the header declares`,
      ).toBe(columnCount);
      for (const value of values) {
        expect(
          value.trim(),
          `session row ${String(index)} draws a bare, unlabelled number ("${value.trim()}") beside the person`,
        ).not.toMatch(/^\d+$/);
      }
    }
  });
});
