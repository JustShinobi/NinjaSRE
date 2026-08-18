import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  PrincipalsPanel,
  type PrincipalRow,
  type PrincipalsLabels,
} from '@/surfaces/principals';

/**
 * Creating a person from Members & roles — the primary action this page
 * never had.
 *
 * Absent for a viewer who may not write identity, present and working for one
 * who may, and the person that lands after a successful submission reads back
 * through the exact same chips every row this panel started with already
 * uses — proving the vocabulary a person was just typed into existence with is
 * the vocabulary every other row already carries, not a second, less
 * considered path to the same two words.
 */

let sent: unknown[] = [];

function answerWith(answer: unknown, status = 201): void {
  vi.stubGlobal('fetch', (_url: unknown, init: RequestInit) => {
    sent.push(JSON.parse(typeof init.body === 'string' ? init.body : '{}'));
    return Promise.resolve(
      new Response(
        JSON.stringify({
          ok: status < 400,
          reachable: true,
          reason: typeof answer === 'string' ? answer : '',
          answer,
        }),
        { status, headers: { 'content-type': 'application/json' } },
      ),
    );
  });
}

beforeEach(() => {
  sent = [];
  answerWith({});
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const LABELS: PrincipalsLabels = {
  displayName: 'Display name',
  email: 'Email',
  password: 'Initial password',
  passwordHelp: 'What this person signs in with locally.',
  create: 'Create person',
  creating: 'Creating…',
  failed: 'The deployment refused this.',
  unreachable: 'The deployment could not be reached.',
};

const PRINCIPALS: readonly PrincipalRow[] = [
  {
    userId: 'user-avery',
    displayName: 'Avery Lockhart',
    identity: 'avery@northwind.example',
    kind: 'user',
    isActive: true,
  },
];

function panel(
  overrides: Partial<{
    principals: readonly PrincipalRow[];
    canWrite: boolean;
  }> = {},
): void {
  render(
    <PrincipalsPanel
      principals={overrides.principals ?? PRINCIPALS}
      canWrite={overrides.canWrite ?? true}
      locale="en"
      labels={LABELS}
    />,
  );
}

/** Fill in every field a creation needs, none left for a caller to remember. */
async function fillForm(
  user: ReturnType<typeof userEvent.setup>,
  overrides: Partial<{ displayName: string; email: string; password: string }> = {},
): Promise<void> {
  await user.type(
    screen.getByLabelText(LABELS.displayName),
    overrides.displayName ?? 'Jordan Blake',
  );
  await user.type(
    screen.getByLabelText(LABELS.email),
    overrides.email ?? 'jordan@northwind.example',
  );
  await user.type(
    screen.getByLabelText(LABELS.password),
    overrides.password ?? 's3cret-first-pass',
  );
}

describe('presence, decided by identity.write', () => {
  it('shows the existing list to a viewer who may only read', () => {
    panel({ canWrite: false });

    expect(screen.getAllByTestId('principal')).toHaveLength(1);
  });

  it('offers no create-person control without identity.write', () => {
    panel({ canWrite: false });

    expect(screen.queryByTestId('create-person')).toBeNull();
    expect(screen.queryByLabelText(LABELS.displayName)).toBeNull();
    expect(screen.queryByLabelText(LABELS.email)).toBeNull();
    expect(screen.queryByLabelText(LABELS.password)).toBeNull();
  });

  it('offers the create-person control once identity.write is held', () => {
    panel({ canWrite: true });

    expect(screen.getByTestId('create-person')).toBeInTheDocument();
  });
});

describe('creating a person', () => {
  it('will not create while a required field is empty', () => {
    panel();

    expect(screen.getByTestId('create-person')).toBeDisabled();
  });

  it('stays disabled for a password of only spaces, the one field the server never trims', () => {
    panel();

    expect(screen.getByTestId('create-person')).toBeDisabled();
  });

  it('posts the three fields the server asks for, the two names trimmed', async () => {
    const user = userEvent.setup();
    panel();

    await fillForm(user, { displayName: '  Jordan Blake  ' });
    await user.click(screen.getByTestId('create-person'));

    expect(sent).toEqual([
      {
        email: 'jordan@northwind.example',
        display_name: 'Jordan Blake',
        password: 's3cret-first-pass',
      },
    ]);
  });

  it('the created person appears in the list, in the same vocabulary as every other row', async () => {
    answerWith({
      user_id: 'user-jordan',
      email: 'jordan@northwind.example',
      display_name: 'Jordan Blake',
      kind: 'user',
      is_active: true,
    });
    const user = userEvent.setup();
    panel();

    await fillForm(user);
    await user.click(screen.getByTestId('create-person'));

    expect(await screen.findByText('Jordan Blake')).toBeInTheDocument();
    expect(screen.getAllByTestId('principal')).toHaveLength(2);
    // Never the raw transport words this deployment just sent over the wire —
    // the same two chips every row this panel started with already carries.
    expect(screen.getAllByTestId('principal-kind').at(-1)).toHaveTextContent('Person');
    expect(screen.getAllByTestId('principal-state').at(-1)).toHaveTextContent('Active');
  });

  it('clears every field, including the password, after a successful creation', async () => {
    answerWith({
      user_id: 'user-jordan',
      email: 'jordan@northwind.example',
      display_name: 'Jordan Blake',
      kind: 'user',
      is_active: true,
    });
    const user = userEvent.setup();
    panel();

    await fillForm(user);
    await user.click(screen.getByTestId('create-person'));
    await screen.findByText('Jordan Blake');

    expect(screen.getByLabelText(LABELS.displayName)).toHaveValue('');
    expect(screen.getByLabelText(LABELS.email)).toHaveValue('');
    expect(screen.getByLabelText(LABELS.password)).toHaveValue('');
  });

  it("names the deployment's own refusal rather than inventing a generic one", async () => {
    answerWith(
      "a principal already exists with the email 'jordan@northwind.example'",
      409,
    );
    const user = userEvent.setup();
    panel();

    await fillForm(user);
    await user.click(screen.getByTestId('create-person'));

    expect(
      await screen.findByText(
        "a principal already exists with the email 'jordan@northwind.example'",
      ),
    ).toBeInTheDocument();
  });

  it('names an unreachable deployment rather than a generic failure', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new Error('network down')));
    const user = userEvent.setup();
    panel();

    await fillForm(user);
    await user.click(screen.getByTestId('create-person'));

    expect(await screen.findByText(LABELS.unreachable)).toBeInTheDocument();
  });

  it('never sends the password back to the browser for anyone to read', async () => {
    answerWith({
      user_id: 'user-jordan',
      email: 'jordan@northwind.example',
      display_name: 'Jordan Blake',
      kind: 'user',
      is_active: true,
    });
    const user = userEvent.setup();
    panel();

    await fillForm(user, { password: 'a-password-nobody-should-see-again' });
    await user.click(screen.getByTestId('create-person'));
    await screen.findByText('Jordan Blake');

    expect(document.body.innerHTML).not.toContain('a-password-nobody-should-see-again');
  });
});
