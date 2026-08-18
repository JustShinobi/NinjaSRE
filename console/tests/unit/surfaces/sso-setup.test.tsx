import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SsoSetupFlow, type SsoSetupLabels } from '@/surfaces/sso-setup';
import { SSO_FIELDS, type SsoField } from '@/surfaces/sso-fields';

/**
 * Single sign-on as a flow: configure, test against real claims, and only
 * then activate — the fluxo em etapas this replaces the flat, eight-field
 * form with, on the same server contract.
 */

const LABELS: SsoSetupLabels = {
  field: {
    provider: 'Provider',
    issuer: 'Issuer',
    client_id: 'Client id',
    authorisation_endpoint: 'Authorisation endpoint',
    token_endpoint: 'Token endpoint',
    jwks_uri: 'Key set',
    redirect_uri: 'Redirect back to',
    default_node_id: 'Default team',
  },
  fieldHelp: {
    provider: 'What you call this identity provider.',
    issuer: 'The issuer URL your provider documents, exactly as it appears there.',
    client_id: 'The client id this deployment registered with the provider.',
    authorisation_endpoint: "Where the provider's own sign-in page lives.",
    token_endpoint: 'Where a code is exchanged for a token.',
    jwks_uri: 'Where the provider publishes the keys that sign its tokens.',
    redirect_uri: 'Where the provider sends somebody back to, after signing in.',
    default_node_id:
      'Where somebody lands when their groups map nowhere in particular.',
  },
  stepConfigure: 'Configure',
  stepTest: 'Test',
  stepActivate: 'Activate',
  save: 'Save this configuration',
  saving: 'Saving…',
  test: 'Test it with a real claim set',
  testing: 'Testing…',
  claims: 'The claims your provider returned',
  claimsHelp: 'Paste what the provider sent back for one test user.',
  activate: 'Make this the way in',
  activating: 'Activating…',
  active: 'Active. People sign in through this provider.',
  verified: 'Tested. It has not been made the way in yet.',
  notVerified: 'Not tested. It cannot be made the way in until it is.',
  notConfigured: 'Not configured yet',
  testFirst: 'Test this configuration before making it the way in.',
  pendingEdit: 'Save this change, then test it again.',
  failed: 'The deployment refused this.',
  unreachable: 'The deployment could not be reached.',
  problems: 'This configuration cannot be used:',
  resultSubject: 'Subject',
  resultEmail: 'Email',
  resultTeam: 'Team',
  resultTeamDefault: 'default',
  resultFailed: 'This claim set failed the test:',
  fallback:
    'Local sign-in stays available as a fallback, whatever this provider is set to.',
};

const SETTINGS: Readonly<Record<SsoField, string>> = Object.fromEntries(
  SSO_FIELDS.map((field) => [field, '']),
) as Record<SsoField, string>;

let sent: { operation: string; payload: unknown }[] = [];

function answerWith(body: unknown, ok = true): void {
  vi.stubGlobal('fetch', (_url: unknown, init: RequestInit) => {
    const raw = typeof init.body === 'string' ? init.body : '{}';
    const request = JSON.parse(raw) as { operation: string; payload: unknown };
    sent.push(request);
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: ok ? 200 : 400,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  sent = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the three steps', () => {
  it('renders configure, test and activate in that order', () => {
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    const sections = screen
      .getAllByRole('heading', { level: 3 })
      .map((h) => h.textContent);
    expect(sections).toEqual(['Configure', 'Test', 'Activate']);
  });

  it('every field carries what it is and where to find it', () => {
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(
      screen.getByText(
        'The issuer URL your provider documents, exactly as it appears there.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('The client id this deployment registered with the provider.'),
    ).toBeInTheDocument();
  });

  it('declares the local fallback on the page', () => {
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.getByTestId('sso-fallback')).toHaveTextContent(
      'Local sign-in stays available',
    );
  });

  it('draws one control per field the provider is described by', () => {
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    for (const field of SSO_FIELDS) {
      expect(screen.getByLabelText(LABELS.field[field])).toBeInTheDocument();
    }
  });
});

describe('an unconfigured deployment', () => {
  it('shows a neutral summary rather than the not-tested state, and no way to activate', () => {
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    // Genuinely nothing recorded and nothing touched: "Not configured yet",
    // not "Not tested" — the two are different facts about the deployment.
    expect(screen.getByTestId('sso-state')).toHaveTextContent(LABELS.notConfigured);
    expect(screen.queryByTestId('activate-sso')).toBeNull();
    expect(screen.getByTestId('sso-test-first')).toHaveTextContent(LABELS.testFirst);
  });
});

describe('testing against real claims', () => {
  it('shows what each claim resolved to on success', async () => {
    answerWith({
      ok: true,
      answer: {
        succeeded: true,
        subject: 'f81d4fae',
        email: 'avery@example.invalid',
        groups: ['sre'],
        mapped_node_id: 'team-platform',
        used_default: false,
      },
    });
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    fireEvent.change(screen.getByLabelText(LABELS.claims), {
      target: { value: '{"sub":"f81d4fae"}' },
    });
    await user.click(screen.getByTestId('test-sso'));

    const result = await screen.findByTestId('sso-test-result');
    expect(within(result).getByTestId('sso-result-subject')).toHaveTextContent(
      'f81d4fae',
    );
    expect(within(result).getByTestId('sso-result-email')).toHaveTextContent(
      'avery@example.invalid',
    );
    expect(within(result).getByTestId('sso-result-team')).toHaveTextContent(
      'team-platform',
    );
  });

  it('names the fallback team when the default was used', async () => {
    answerWith({
      ok: true,
      answer: {
        succeeded: true,
        subject: 's',
        email: 'e@x.test',
        groups: [],
        mapped_node_id: 'org-root',
        used_default: true,
      },
    });
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );
    fireEvent.change(screen.getByLabelText(LABELS.claims), { target: { value: '{}' } });
    await user.click(screen.getByTestId('test-sso'));

    expect(await screen.findByTestId('sso-result-team')).toHaveTextContent('default');
  });

  it('reports why a claim set failed, naming the missing claim', async () => {
    answerWith({
      ok: true,
      answer: { succeeded: false, problems: ["the claim named 'email' is missing"] },
    });
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );
    fireEvent.change(screen.getByLabelText(LABELS.claims), { target: { value: '{}' } });
    await user.click(screen.getByTestId('test-sso'));

    expect(await screen.findByTestId('sso-test-result')).toHaveTextContent(
      "the claim named 'email' is missing",
    );
    expect(screen.queryByTestId('activate-sso')).toBeNull();
  });

  it('sends the claim set the operator pasted, parsed', async () => {
    answerWith({
      ok: true,
      answer: { succeeded: true, mapped_node_id: 'team-platform' },
    });
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    fireEvent.change(screen.getByLabelText(LABELS.claims), {
      target: { value: '{"sub":"f81d4fae"}' },
    });
    await user.click(screen.getByTestId('test-sso'));

    expect(sent.at(-1)?.operation).toBe('test');
    expect(sent.at(-1)?.payload).toEqual({ claims: { sub: 'f81d4fae' } });
  });

  it('will not test an edit that has not been saved', async () => {
    // The deployment tests what it holds. Testing a form nobody has saved
    // would report a pass for a document that is not the one being activated.
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    fireEvent.change(screen.getByLabelText(LABELS.claims), { target: { value: '{}' } });
    await user.type(screen.getByLabelText(LABELS.field.client_id), 'x');

    expect(screen.getByTestId('test-sso')).toBeDisabled();
  });

  it('still names the failure when a failing test named no specific problem', async () => {
    answerWith({ ok: true, answer: { succeeded: false } });
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );
    fireEvent.change(screen.getByLabelText(LABELS.claims), { target: { value: '{}' } });
    await user.click(screen.getByTestId('test-sso'));

    expect(await screen.findByTestId('sso-test-result')).toHaveTextContent(
      LABELS.resultFailed,
    );
  });
});

describe('activation is blocked until a test on these exact settings has passed', () => {
  it('offers the control once verified is true', () => {
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={true}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.getByTestId('activate-sso')).toBeInTheDocument();
  });

  it('names the tested-but-not-active state on its own, before any interaction', () => {
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={true}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.getByTestId('sso-state')).toHaveTextContent(LABELS.verified);
  });

  it('an edit after a passing test hides the control again, with its own explanation', async () => {
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={true}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );
    expect(screen.getByTestId('activate-sso')).toBeInTheDocument();

    await user.type(
      screen.getByLabelText(LABELS.field.issuer),
      ['https:', '//new.example.invalid'].join(''),
    );

    expect(screen.queryByTestId('activate-sso')).toBeNull();
    expect(screen.getByTestId('sso-test-first')).toHaveTextContent(LABELS.pendingEdit);
  });

  it('activating asks the deployment and adopts what it answers', async () => {
    answerWith({
      ok: true,
      answer: { is_active: true, verified: true, problems: [] },
    });
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={true}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByTestId('activate-sso'));

    expect(await screen.findByTestId('sso-state')).toHaveTextContent(LABELS.active);
    expect(sent.some((request) => request.operation === 'activate')).toBe(true);
  });

  it('leaves the state alone when activation is refused', async () => {
    answerWith({ reason: 'the settings changed since the test' }, false);
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={true}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByTestId('activate-sso'));

    expect(await screen.findByTestId('sso-failure')).toHaveTextContent(
      'the settings changed since the test',
    );
    // A refused activation adopts nothing — the state stays exactly what it
    // was before the attempt, never silently switched to "not tested".
    expect(screen.getByTestId('sso-state')).toHaveTextContent(LABELS.verified);
  });

  it('says an unreachable deployment could not be reached, not that it refused', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={true}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByTestId('activate-sso'));

    expect(await screen.findByTestId('sso-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });

  it('takes the verified answer from a save rather than keeping what was there', async () => {
    // A save always clears the deployment's test result. A console that
    // assumed otherwise would offer activation on a document nobody had
    // tested against these exact claims.
    answerWith({
      ok: true,
      answer: { is_active: false, verified: false, problems: [] },
    });
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={true}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );
    expect(screen.getByTestId('activate-sso')).toBeInTheDocument();

    await user.type(screen.getByLabelText(LABELS.field.client_id), 'x');
    await user.click(screen.getByTestId('save-sso'));

    expect(sent.at(-1)?.operation).toBe('save');
    expect(await screen.findByTestId('sso-test-first')).toBeInTheDocument();
    expect(screen.queryByTestId('activate-sso')).toBeNull();
  });
});

describe('a deployment already carrying problems', () => {
  it('shows nothing when there is nothing wrong', () => {
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.queryByTestId('sso-problems')).toBeNull();
  });

  it('shows none of them on a virgin form — no field is marked, no list appears', () => {
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={['issuer is required', 'default_node_id is required']}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.queryByTestId('sso-problems')).toBeNull();
    expect(screen.queryByText(/is required/)).toBeNull();
  });

  it('reveals only the problem of the field a person actually left, humanised', async () => {
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={['issuer is required', 'default_node_id is required']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByLabelText(LABELS.field.issuer));
    await user.tab();

    expect(screen.getByText('Issuer is required')).toBeInTheDocument();
    // The label's own words, never the payload key.
    expect(screen.queryByText('issuer is required')).toBeNull();
    // The field nobody left yet stays quiet.
    expect(screen.queryByText(/default_node_id/)).toBeNull();
    expect(screen.queryByText(/Default team is required/)).toBeNull();
  });

  it('leaving a second field reveals that field’s own problem too, without hiding the first', async () => {
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={['issuer is required', 'default_node_id is required']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByLabelText(LABELS.field.issuer));
    await user.tab();
    await user.click(screen.getByLabelText(LABELS.field.default_node_id));
    await user.tab();

    expect(screen.getByText('Issuer is required')).toBeInTheDocument();
    expect(screen.getByText('Default team is required')).toBeInTheDocument();
  });

  it('leaving the same field a second time keeps it exactly as touched, not touched twice', async () => {
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={['issuer is required']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByLabelText(LABELS.field.issuer));
    await user.tab();
    await user.click(screen.getByLabelText(LABELS.field.issuer));
    await user.tab();

    // Still shown exactly once — leaving an already-touched field a second
    // time neither drops it nor duplicates its problem.
    expect(screen.getAllByText('Issuer is required')).toHaveLength(1);
  });

  it('submitting reveals every pending problem at once, humanised', async () => {
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={['issuer is required', 'default_node_id is required']}
        labels={LABELS}
        locale="en"
      />,
    );

    // An edit is what makes the save control clickable at all.
    await user.type(screen.getByLabelText(LABELS.field.provider), 'keycloak');
    await user.click(screen.getByTestId('save-sso'));

    expect(screen.getByText('Issuer is required')).toBeInTheDocument();
    expect(screen.getByText('Default team is required')).toBeInTheDocument();
  });

  it('a problem naming no field this form declares only appears once the form is submitted', async () => {
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={['the issuer and the token endpoint must share a host']}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.queryByTestId('sso-problems')).toBeNull();

    await user.type(screen.getByLabelText(LABELS.field.provider), 'keycloak');
    await user.click(screen.getByTestId('save-sso'));

    expect(screen.getByTestId('sso-problems')).toHaveTextContent(
      'the issuer and the token endpoint must share a host',
    );
  });
});

describe('saving reports its own refusal', () => {
  it('names the deployment’s own reason for refusing a save', async () => {
    answerWith({ reason: 'issuer must be https' }, false);
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.type(screen.getByLabelText(LABELS.field.provider), 'keycloak');
    await user.click(screen.getByTestId('save-sso'));

    expect(await screen.findByTestId('sso-failure')).toHaveTextContent(
      'issuer must be https',
    );
  });

  it('reports an unreachable deployment as its own message', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new Error('network down')));
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.type(screen.getByLabelText(LABELS.field.provider), 'keycloak');
    await user.click(screen.getByTestId('save-sso'));

    expect(await screen.findByTestId('sso-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});

describe('testing rejects a claim set that is not valid JSON', () => {
  it('reports it as a failure rather than sending it', async () => {
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    fireEvent.change(screen.getByLabelText(LABELS.claims), {
      target: { value: 'not json' },
    });
    await user.click(screen.getByTestId('test-sso'));

    expect(await screen.findByTestId('sso-failure')).toHaveTextContent(LABELS.failed);
    expect(sent).toHaveLength(0);
  });

  it('leaves the previous test result alone when the deployment cannot be reached', async () => {
    answerWith({
      ok: true,
      answer: { succeeded: true, mapped_node_id: 'team-platform' },
    });
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );
    fireEvent.change(screen.getByLabelText(LABELS.claims), { target: { value: '{}' } });
    await user.click(screen.getByTestId('test-sso'));
    await screen.findByTestId('sso-result-team');

    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));
    await user.click(screen.getByTestId('test-sso'));

    expect(await screen.findByTestId('sso-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
    // The result from the successful test a moment ago is still what shows —
    // an unreachable retry does not blank out an answer already on screen.
    expect(screen.getByTestId('sso-result-team')).toBeInTheDocument();
  });
});

describe('the shared machinery underneath save and activate', () => {
  it('adopts an answer that omits its problems list as carrying none, not as a crash', async () => {
    answerWith({ ok: true, answer: { is_active: true, verified: true } });
    const user = userEvent.setup();
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={true}
        problems={['issuer is required']}
        labels={LABELS}
        locale="en"
      />,
    );

    await user.click(screen.getByTestId('activate-sso'));

    expect(await screen.findByTestId('sso-state')).toHaveTextContent(LABELS.active);
    // The activation answered with no problems field at all — adopted as
    // empty, so the stale pre-activation problem does not linger.
    await user.click(screen.getByLabelText(LABELS.field.issuer));
    await user.tab();
    expect(screen.queryByText(/is required/)).toBeNull();
  });
});

describe('vocabulary', () => {
  it('never shows the raw resource-health word once this provider is the way in', () => {
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={true}
        verified={true}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    const flow = screen.getByTestId('sso-setup-flow');
    expect(flow.textContent).not.toMatch(/healthy/i);
    // The named chip itself, in single sign-on's own words — not a schedule's
    // "Enabled" and not a resource's "Healthy".
    expect(screen.getByTestId('sso-state-chip')).toHaveTextContent('Active');
  });

  it('reads as inactive, not "disabled", the same chip when nothing is active yet', () => {
    render(
      <SsoSetupFlow
        settings={SETTINGS}
        isActive={false}
        verified={false}
        problems={[]}
        labels={LABELS}
        locale="en"
      />,
    );

    expect(screen.getByTestId('sso-state-chip')).toHaveTextContent('Inactive');
  });
});
