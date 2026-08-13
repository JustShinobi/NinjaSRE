import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  GrantPanel,
  type Grant,
  type GrantLabels,
  type GrantPrincipalOption,
} from '@/surfaces/grants';

import { ROLES } from '../shell/support';

/**
 * Granting and removing a role.
 *
 * The last-owner refusal is the point of this whole surface: the gateway
 * answers a removal that would leave the organisation without an owner with a
 * 409 and a sentence naming what to do about it, and that sentence has to land
 * in its own region — not folded into the same "something went wrong" a
 * dropped connection or an unknown role would produce.
 */

/**
 * `element`, or a failure naming the absence.
 *
 * A test that reaches into an array and asserts on `undefined` reports
 * "cannot read property of undefined", which says nothing about what the
 * console did. This says the element was not there.
 */
function one(element: HTMLElement | undefined): HTMLElement {
  if (element === undefined)
    throw new Error('the element this test is about is not there');
  return element;
}

/** One field of a request payload. */
function field(payload: unknown, name: string): unknown {
  return Reflect.get(Object(payload), name);
}

/** Whether a request payload carries `name` at all. */
function hasField(payload: unknown, name: string): boolean {
  return typeof payload === 'object' && payload !== null && name in payload;
}

let sent: { operation: string; payload: unknown }[] = [];

function answerWith(answer: unknown, status = 200): void {
  vi.stubGlobal('fetch', (_url: unknown, init: RequestInit) => {
    const body: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    sent.push({
      operation: String(Reflect.get(Object(body), 'operation')),
      payload: Reflect.get(Object(body), 'payload'),
    });
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

const LABELS: GrantLabels = {
  principal: 'Principal',
  role: 'Role',
  node: 'Node',
  nodeHelp: 'Leave blank to grant it across the whole organisation.',
  organisation: 'Whole organisation',
  add: 'Grant this role',
  adding: 'Granting…',
  remove: 'Remove',
  removing: 'Removing…',
  removeAction: 'Remove this grant',
  removeConsequence: 'They lose this role immediately.',
  removeClose: 'Close',
  removeCancel: 'Leave it granted',
  failed: 'The deployment refused this.',
  unreachable: 'The deployment could not be reached.',
};

const PRINCIPALS: readonly GrantPrincipalOption[] = [
  { id: 'user-avery', label: 'Avery Lockhart' },
  { id: 'user-morgan', label: 'Morgan Reyes' },
];

const ROLE_OPTIONS: readonly string[] = ['viewer', 'operator', 'owner'];

const GRANTS: readonly Grant[] = [
  { grantId: 'grant-1', principalId: 'user-avery', role: 'owner', nodeId: '' },
  {
    grantId: 'grant-2',
    principalId: 'user-morgan',
    role: 'operator',
    nodeId: 'team-platform',
  },
];

function panel(
  overrides: Partial<{
    grants: readonly Grant[];
    canWrite: boolean;
    principals: readonly GrantPrincipalOption[];
    roles: readonly string[];
    roleDescriptions: Readonly<Record<string, string>>;
  }> = {},
): void {
  render(
    <GrantPanel
      grants={overrides.grants ?? GRANTS}
      principals={overrides.principals ?? PRINCIPALS}
      roles={overrides.roles ?? ROLE_OPTIONS}
      {...(overrides.roleDescriptions === undefined
        ? {}
        : { roleDescriptions: overrides.roleDescriptions })}
      canWrite={overrides.canWrite ?? true}
      labels={LABELS}
    />,
  );
}

describe('the role catalogue this form offers', () => {
  it("is the deployment's own, served rather than compiled in", () => {
    // The screen reads `/identity/roles` and hands the answer down. What this
    // holds is that the deployment's catalogue and the one the role matrix
    // walks are the same list — so a role added in Python appears on the form
    // without this console changing at all.
    panel({ roles: ROLES.order });

    const offered = Array.from(
      document.querySelectorAll('select[name="grant-role"] option'),
    ).map((option) => option.getAttribute('value'));
    expect(offered).toEqual([...ROLES.order]);
  });
});

describe('presence, decided by identity.write', () => {
  it('shows the list to a viewer who may only read', () => {
    panel({ canWrite: false });

    expect(screen.getAllByTestId('grant')).toHaveLength(2);
  });

  it('offers neither the form nor a remove control without identity.write', () => {
    panel({ canWrite: false });

    expect(screen.queryByTestId('add-grant')).toBeNull();
    expect(screen.queryByTestId('remove-grant')).toBeNull();
    expect(screen.queryByLabelText(LABELS.principal)).toBeNull();
  });

  it('offers both once identity.write is held', () => {
    panel({ canWrite: true });

    expect(screen.getByTestId('add-grant')).toBeInTheDocument();
    expect(screen.getAllByTestId('remove-grant').length).toBeGreaterThan(0);
  });
});

describe('granting a role', () => {
  it('will not grant while nobody is chosen', () => {
    panel({ principals: [] });

    expect(screen.getByTestId('add-grant')).toBeDisabled();
  });

  it('starts with nothing chosen when the deployment declares no roles', () => {
    panel({ roles: [] });

    expect(screen.getByTestId('add-grant')).toBeDisabled();
  });

  it('falls back to the generic failure when the deployment’s reason is blank', async () => {
    answerWith('', 400);
    panel();

    await userEvent.click(screen.getByTestId('add-grant'));

    expect(await screen.findByTestId('grant-failure')).toHaveTextContent(LABELS.failed);
  });

  it('treats an answer that carries no reason at all as blank, not as a crash', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        new Response(JSON.stringify({ ok: false, reachable: true }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    );
    panel();

    await userEvent.click(screen.getByTestId('add-grant'));

    expect(await screen.findByTestId('grant-failure')).toHaveTextContent(LABELS.failed);
  });

  it('sends no node_id when the field is left blank, meaning the whole organisation', async () => {
    panel();

    await userEvent.click(screen.getByTestId('add-grant'));

    expect(sent.at(-1)?.operation).toBe('add');
    const payload = sent.at(-1)?.payload;
    expect(field(payload, 'principal_id')).toBe('user-avery');
    expect(field(payload, 'role')).toBe('viewer');
    expect(hasField(payload, 'node_id')).toBe(false);
  });

  it('sends the node named, when one is', async () => {
    panel();

    await userEvent.type(screen.getByLabelText(LABELS.node), 'team-platform');
    await userEvent.click(screen.getByTestId('add-grant'));

    expect(field(sent.at(-1)?.payload, 'node_id')).toBe('team-platform');
  });

  it('adds what the deployment answered with to the list, verbatim', async () => {
    answerWith({
      grant_id: 'grant-new',
      principal_id: 'user-avery',
      role: 'viewer',
      node_id: '',
    });
    panel();

    await userEvent.click(screen.getByTestId('add-grant'));

    const rows = await screen.findAllByTestId('grant');
    expect(rows.some((element) => element.dataset.grant === 'grant-new')).toBe(true);
  });

  it('renders an unknown role as the deployment’s own message, not a generic one', async () => {
    answerWith(
      "'ceo' is not a role this deployment has; expected one of admin, operator, owner, responder, viewer",
      400,
    );
    panel();

    await userEvent.click(screen.getByTestId('add-grant'));

    expect(await screen.findByTestId('grant-failure')).toHaveTextContent(
      'expected one of admin, operator, owner, responder, viewer',
    );
  });

  it('treats a reply that is not JSON as an empty one, rather than crashing', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve(new Response('not json', { status: 200 })),
    );
    panel();

    await userEvent.click(screen.getByTestId('add-grant'));

    // Nothing to add — the deployment's own answer named no grant — and no
    // failure region either, since the request itself succeeded.
    expect(screen.getAllByTestId('grant')).toHaveLength(2);
    expect(screen.queryByTestId('grant-failure')).toBeNull();
  });

  it('says so when the deployment cannot be reached', async () => {
    panel();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.click(screen.getByTestId('add-grant'));

    expect(await screen.findByTestId('grant-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});

describe('removing a grant', () => {
  it('names the principal and the role before it removes anything', async () => {
    panel();

    await userEvent.click(one(screen.getAllByTestId('remove-grant')[0]));

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('user-avery — owner')).toBeInTheDocument();
    expect(within(dialog).getByText(LABELS.removeConsequence)).toBeInTheDocument();
    expect(sent).toHaveLength(0);
  });

  it('removes nothing when the confirmation is dismissed', async () => {
    panel();

    await userEvent.click(one(screen.getAllByTestId('remove-grant')[0]));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(
      within(dialog).getByRole('button', { name: LABELS.removeCancel }),
    );

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(sent).toHaveLength(0);
    expect(screen.getAllByTestId('grant')).toHaveLength(2);
  });

  it('removes it through the console’s own courier once confirmed', async () => {
    panel();

    await userEvent.click(one(screen.getAllByTestId('remove-grant')[0]));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(
      within(dialog).getByRole('button', { name: new RegExp(LABELS.removeAction) }),
    );

    expect(sent.at(-1)?.operation).toBe('remove');
    expect(field(sent.at(-1)?.payload, 'grant_id')).toBe('grant-1');
    expect(await screen.findAllByTestId('grant').then((rows) => rows.length)).toBe(1);
  });

  it('renders the last-owner refusal as its own message, and keeps the grant in the list', async () => {
    answerWith(
      'removing this grant would leave the organisation with no owner; grant ownership to somebody else first',
      409,
    );
    panel();

    await userEvent.click(one(screen.getAllByTestId('remove-grant')[0]));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(
      within(dialog).getByRole('button', { name: new RegExp(LABELS.removeAction) }),
    );

    expect(await screen.findByTestId('grant-last-owner')).toHaveTextContent(
      'grant ownership to somebody else first',
    );
    expect(screen.queryByTestId('grant-failure')).toBeNull();
    expect(screen.getAllByTestId('grant')).toHaveLength(2);
  });

  it('reports an ordinary refusal as the generic failure, not the last-owner message', async () => {
    answerWith('no such grant', 404);
    panel();

    await userEvent.click(one(screen.getAllByTestId('remove-grant')[0]));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(
      within(dialog).getByRole('button', { name: new RegExp(LABELS.removeAction) }),
    );

    expect(await screen.findByTestId('grant-failure')).toHaveTextContent(
      'no such grant',
    );
    expect(screen.queryByTestId('grant-last-owner')).toBeNull();
  });

  it('falls back to the generic failure when an ordinary refusal carries no reason', async () => {
    answerWith('', 404);
    panel();

    await userEvent.click(one(screen.getAllByTestId('remove-grant')[0]));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(
      within(dialog).getByRole('button', { name: new RegExp(LABELS.removeAction) }),
    );

    expect(await screen.findByTestId('grant-failure')).toHaveTextContent(LABELS.failed);
  });

  it('says so on a removal when the deployment cannot be reached, and keeps the row', async () => {
    panel();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.click(one(screen.getAllByTestId('remove-grant')[0]));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(
      within(dialog).getByRole('button', { name: new RegExp(LABELS.removeAction) }),
    );

    expect(await screen.findByTestId('grant-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
    expect(screen.getAllByTestId('grant')).toHaveLength(2);
  });

  it('shows the whole-organisation label for a grant with no node', () => {
    panel();

    expect(screen.getByText(LABELS.organisation)).toBeInTheDocument();
  });
});

describe('what a role means, at the point it is chosen', () => {
  const DESCRIPTIONS = {
    viewer: 'investigation.read, report.read',
    operator: 'config.write, credential.write',
    owner: 'org.delete, owner.assign',
  };

  it('describes the role currently selected, not just its name', () => {
    panel({ roleDescriptions: DESCRIPTIONS });

    expect(screen.getByText(DESCRIPTIONS.viewer)).toBeInTheDocument();
  });

  it('updates the description when a different role is chosen', async () => {
    panel({ roleDescriptions: DESCRIPTIONS });

    await userEvent.selectOptions(screen.getByLabelText(LABELS.role), 'owner');

    expect(screen.getByText(DESCRIPTIONS.owner)).toBeInTheDocument();
    expect(screen.queryByText(DESCRIPTIONS.viewer)).toBeNull();
  });

  it('describes nothing for a role this console was given no catalogue for', () => {
    panel();

    expect(screen.queryByText(/investigation\.read/)).toBeNull();
  });
});
