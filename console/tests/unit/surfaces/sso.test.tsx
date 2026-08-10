import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SsoForm, SSO_FIELDS, type SsoField } from '@/surfaces/sso';

/**
 * A provider cannot be activated without a test that passed on the same document.
 *
 * The one requirement this form exists for. SSO is the path every human uses,
 * so a broken one is not a degraded feature — it is every operator locked out
 * of the tool they would use to fix it. The activate control is therefore
 * absent rather than disabled, and its absence is decided by the deployment's
 * own answer rather than by anything this component remembers.
 */

let sent: { operation: string; payload: unknown }[] = [];

function answerWith(answer: unknown, status = 200): void {
  vi.stubGlobal('fetch', (_url: unknown, init: RequestInit) => {
    const body: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    sent.push({
      operation: String(Reflect.get(Object(body), 'operation')),
      payload: Reflect.get(Object(body), 'payload'),
    });
    return Promise.resolve(
      new Response(JSON.stringify({ ok: status < 400, reachable: true, answer }), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  sent = [];
  answerWith({ succeeded: true, mapped_node_id: 'team-platform' });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const FIELD_LABELS: Record<SsoField, string> = {
  provider: 'Provider',
  issuer: 'Issuer',
  client_id: 'Client id',
  authorisation_endpoint: 'Authorisation endpoint',
  token_endpoint: 'Token endpoint',
  jwks_uri: 'Key set',
  redirect_uri: 'Redirect back to',
  default_node_id: 'Default team',
};

const LABELS = {
  field: FIELD_LABELS,
  save: 'Save',
  saving: 'Saving…',
  test: 'Test with a real claim set',
  testing: 'Testing…',
  claims: 'The claims your provider returned',
  claimsHelp: 'Paste what the provider sent back for a test user.',
  activate: 'Make this the way in',
  activating: 'Activating…',
  active: 'Active. People sign in through this provider.',
  verified: 'Tested. It has not been made the way in yet.',
  notVerified: 'Not tested.',
  testFirst: 'Test this configuration before making it the way in.',
  pendingEdit: 'Save this change, then test it again.',
  failed: 'The deployment refused this.',
  unreachable: 'The deployment could not be reached.',
  problems: 'This configuration cannot be used:',
};

const SETTINGS: Record<SsoField, string> = {
  provider: 'keycloak',
  issuer: ['https:', '//id.example.invalid/realms/main'].join(''),
  client_id: 'ninjasre',
  authorisation_endpoint: ['https:', '//id.example.invalid/auth'].join(''),
  token_endpoint: ['https:', '//id.example.invalid/token'].join(''),
  jwks_uri: ['https:', '//id.example.invalid/certs'].join(''),
  redirect_uri: ['https:', '//ninjasre.example.invalid/auth/callback'].join(''),
  default_node_id: 'org-northwind',
};

function form(
  over: { verified?: boolean; isActive?: boolean; problems?: string[] } = {},
): void {
  render(
    <SsoForm
      settings={SETTINGS}
      isActive={over.isActive ?? false}
      verified={over.verified ?? false}
      problems={over.problems ?? []}
      labels={LABELS}
    />,
  );
}

describe('the order that keeps somebody from being locked out', () => {
  it('offers no way to activate an untested provider', () => {
    form();

    expect(screen.queryByTestId('activate-sso')).toBeNull();
    expect(screen.getByTestId('sso-test-first')).toHaveTextContent(LABELS.testFirst);
  });

  it('offers it once the deployment says a test passed on these settings', () => {
    form({ verified: true });

    expect(screen.getByTestId('activate-sso')).toBeInTheDocument();
  });

  it('takes it away again the moment a field is edited', async () => {
    form({ verified: true });

    await userEvent.type(screen.getByLabelText('Client id'), 'x');

    expect(screen.queryByTestId('activate-sso')).toBeNull();
    expect(screen.getByTestId('sso-test-first')).toHaveTextContent(LABELS.pendingEdit);
  });

  it('will not test an edit that has not been saved', async () => {
    // The deployment tests what it holds. Testing a form nobody has saved would
    // report a pass for a document that is not the one being activated.
    form();

    await userEvent.type(screen.getByLabelText(LABELS.claims), '{{}');
    await userEvent.type(screen.getByLabelText('Client id'), 'x');

    expect(screen.getByTestId('test-sso')).toBeDisabled();
  });

  it('takes the verified answer from the deployment rather than from the save', async () => {
    // A save always clears the deployment's test result. A console that assumed
    // otherwise would offer activation on a document nobody had tested.
    form({ verified: true });
    answerWith({ is_active: false, verified: false, problems: [] });

    await userEvent.type(screen.getByLabelText('Client id'), 'x');
    await userEvent.click(screen.getByTestId('save-sso'));

    expect(sent.at(-1)?.operation).toBe('save');
    expect(await screen.findByTestId('sso-test-first')).toBeInTheDocument();
    expect(screen.queryByTestId('activate-sso')).toBeNull();
  });
});

describe('testing and activating', () => {
  it('sends the claim set the operator pasted, parsed', async () => {
    form();

    await userEvent.type(screen.getByLabelText(LABELS.claims), '{{"sub":"f81d4fae"}');
    await userEvent.click(screen.getByTestId('test-sso'));

    expect(sent.at(-1)?.operation).toBe('test');
    expect(sent.at(-1)?.payload).toEqual({ claims: { sub: 'f81d4fae' } });
  });

  it('says where a passing test landed the user', async () => {
    form();

    await userEvent.type(screen.getByLabelText(LABELS.claims), '{{}');
    await userEvent.click(screen.getByTestId('test-sso'));

    expect(await screen.findByTestId('sso-test-result')).toHaveTextContent(
      'team-platform',
    );
    expect(screen.getByTestId('activate-sso')).toBeInTheDocument();
  });

  it('reports a failing test in the deployment’s own words, and offers no activation', async () => {
    form();
    answerWith({
      succeeded: false,
      problems: ["it carried no 'email' claim"],
    });

    await userEvent.type(screen.getByLabelText(LABELS.claims), '{{}');
    await userEvent.click(screen.getByTestId('test-sso'));

    expect(await screen.findByTestId('sso-test-result')).toHaveTextContent(
      "no 'email' claim",
    );
    expect(screen.queryByTestId('activate-sso')).toBeNull();
  });

  it('activates and adopts what the deployment says it became', async () => {
    form({ verified: true });
    answerWith({ is_active: true, verified: true, problems: [] });

    await userEvent.click(screen.getByTestId('activate-sso'));

    expect(sent.at(-1)?.operation).toBe('activate');
    expect(await screen.findByTestId('sso-state')).toHaveTextContent(LABELS.active);
  });

  it('lists everything wrong with the configuration, not the first thing', () => {
    form({ problems: ['issuer is required', 'default_node_id is required'] });

    const problems = screen.getByTestId('sso-problems');
    expect(problems).toHaveTextContent('issuer is required');
    expect(problems).toHaveTextContent('default_node_id is required');
  });

  it('draws one control per field the provider is described by', () => {
    form();

    for (const field of SSO_FIELDS) {
      expect(screen.getByLabelText(LABELS.field[field])).toBeInTheDocument();
    }
  });
});

describe('when the deployment will not answer', () => {
  it('says it could not be reached rather than that it refused', async () => {
    form({ verified: true });
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.click(screen.getByTestId('activate-sso'));

    expect(await screen.findByTestId('sso-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });

  it('carries a refusal reason back in the deployment’s own words', async () => {
    form({ verified: true });
    answerWith({}, 400);
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        new Response(
          JSON.stringify({ ok: false, reachable: true, reason: 'run the test first' }),
          { status: 400, headers: { 'content-type': 'application/json' } },
        ),
      ),
    );

    await userEvent.click(screen.getByTestId('activate-sso'));

    expect(await screen.findByTestId('sso-failure')).toHaveTextContent(
      'run the test first',
    );
  });

  it('refuses a claim set that is not a document, without asking anything', async () => {
    form();

    await userEvent.type(screen.getByLabelText(LABELS.claims), 'not json');
    await userEvent.click(screen.getByTestId('test-sso'));

    expect(sent).toHaveLength(0);
    expect(screen.getByTestId('sso-failure')).toHaveTextContent(LABELS.failed);
  });

  it('falls back to its own words when a failing test named no problem', async () => {
    form();
    answerWith({ succeeded: false });

    await userEvent.type(screen.getByLabelText(LABELS.claims), '{{}');
    await userEvent.click(screen.getByTestId('test-sso'));

    expect(await screen.findByTestId('sso-test-result')).toHaveTextContent(
      LABELS.failed,
    );
  });

  it('says a test passed even where it mapped nowhere in particular', async () => {
    form();
    answerWith({ succeeded: true, mapped_node_id: '' });

    await userEvent.type(screen.getByLabelText(LABELS.claims), '{{}');
    await userEvent.click(screen.getByTestId('test-sso'));

    expect(await screen.findByTestId('sso-test-result')).toHaveTextContent(
      LABELS.verified,
    );
  });

  it('shows the tested state where the deployment says tested but not active', () => {
    form({ verified: true });

    expect(screen.getByTestId('sso-state')).toHaveTextContent(LABELS.verified);
  });
});
