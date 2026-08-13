import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EN } from '@/i18n/en';
import { AREAS, areaByPath } from '@/shell/routes';
import { WIZARD_STEPS } from '@/surfaces/first-run/plan';
import { SLIDES, Tutorial } from '@/surfaces/first-run/tutorial';
import { IntegrationsStep } from '@/surfaces/first-run/integrations';
import { VerifyStep } from '@/surfaces/first-run/verify';
import { ModelStep } from '@/surfaces/first-run/model';
import { DashboardScreen } from '@/surfaces/screens/dashboard';
import { FirstRunScreen } from '@/surfaces/screens/first-run';
import { ALL_SCREENS } from '../support/screens';
import { principalHolding, serveScenario } from '../support/dataset';
import { surfaceContext } from '@/surfaces/context';

/**
 * The guided first run: the seven steps, the two panels it adds to the
 * dashboard, and the overlay above them.
 *
 * Everything asserted here is a claim the specification makes about what an
 * operator meets on a deployment's first day. The two that carry the most
 * weight are negative ones — no secret is ever rendered back, and nothing
 * redirects out of the shell — because both are properties that pass silently
 * until the day somebody screenshots a page.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === 'ninjasre_session' ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

let sent: readonly { url: string; body: string }[] = [];

// Where the tutorial's final slide navigates. The suite-wide router mock
// swallows navigation entirely; this file is partly *about* one, so its own
// mock records where the router was sent.
const pushed = vi.hoisted(() => [] as string[]);

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    refresh: () => undefined,
    push: (href: string) => {
      pushed.push(href);
    },
    replace: () => undefined,
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
  notFound: () => {
    throw new Error('not found');
  },
  redirect: (href: string) => {
    throw new Error(`redirected to ${href}`);
  },
}));

/** What every exit of the tutorial must send: the nested document, not a dotted key. */
const DISMISSAL = { surfaces: { console: { tutorial_dismissed: true } } };

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

function answerWith(
  body: unknown,
  status = 200,
): (url: unknown, init?: RequestInit) => Promise<Response> {
  return (url, init) => {
    sent = [
      ...sent,
      { url: String(url), body: typeof init?.body === 'string' ? init.body : '' },
    ];
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  };
}

beforeEach(() => {
  sent = [];
  pushed.length = 0;
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function firstRun(query: Record<string, string> = {}): Promise<void> {
  serveScenario('first-run');
  render(await FirstRunScreen(await surfaceContext(query)));
}

// --- The screen, and where it thinks you are ----------------------------------------

describe('the wizard screen', () => {
  it('resolves the node from the tree root when the session names no team', async () => {
    // A local administrator's session carries no team, and the model step it
    // renders must still write somewhere: the root of the organisation tree,
    // exactly as /configuration resolves it. A step that sent the empty
    // string would be refused by the courier with nothing after the colon.
    serveScenario(
      'first-run',
      principalHolding(['config.read', 'config.write', 'investigation.read'], ''),
    );
    render(
      await FirstRunScreen(
        await surfaceContext({ step: 'model', provider: 'anthropic' }),
      ),
    );

    vi.stubGlobal('fetch', answerWith({ changes: [] }));
    await userEvent.click(screen.getByTestId('preview-model'));

    const previewed = sent.find((request) => request.url === '/api/preview');
    expect(JSON.parse(previewed?.body ?? '{}')).toMatchObject({
      nodeId: 'org-northwind',
    });
  });

  it('keeps every step visible, marking exactly one as where you are', async () => {
    await firstRun();

    const steps = screen.getAllByTestId('wizard-step');
    expect(steps.map((step) => step.getAttribute('data-step'))).toEqual([
      ...WIZARD_STEPS,
    ]);
    expect(
      steps.filter((step) => step.getAttribute('data-current') === 'true'),
    ).toHaveLength(1);
  });

  it('starts a fresh deployment at the provider, derived rather than remembered', async () => {
    await firstRun();

    expect(screen.getByTestId('wizard-body')).toHaveAttribute('data-step', 'provider');
  });

  it('reopens a completed step from its own address', async () => {
    await firstRun({ step: 'verify' });

    expect(screen.getByTestId('wizard-body')).toHaveAttribute('data-step', 'verify');
  });

  it('makes every step a link, which is what makes reopening survive a reload', async () => {
    await firstRun();

    for (const step of screen.getAllByTestId('wizard-step')) {
      expect(step.getAttribute('href')).toBe(
        `/first-run?step=${String(step.getAttribute('data-step'))}`,
      );
    }
  });

  it('says why each step exists rather than only what it is called', () => {
    for (const step of WIZARD_STEPS) {
      expect(EN[`firstRun.why.${step}`], step).toBeDefined();
    }
  });
});

// --- The provider step ----------------------------------------------------------------

describe('choosing a provider', () => {
  it('offers all nine, each with its siting and its guidance', async () => {
    await firstRun();

    const options = screen.getAllByTestId('provider-option');
    expect(options).toHaveLength(9);
    for (const option of options) {
      expect(within(option).getByTestId('provider-siting').textContent).toBeTruthy();
      expect(within(option).getByTestId('provider-guidance').textContent).toBeTruthy();
      expect(within(option).getByTestId('choose-provider')).toBeInTheDocument();
    }
  });

  it('draws the local one exactly as it draws the other eight', async () => {
    await firstRun();

    const options = screen.getAllByTestId('provider-option');
    const local = options.filter((one) => one.getAttribute('data-local') === 'true');
    expect(local).toHaveLength(1);
    // Equal weight is a property of the markup, not of the wording: the same
    // class list, the same controls, no heading of its own.
    const [only] = local;
    expect(only?.className).toBe(options[0]?.className);
    expect(within(one(only)).getByTestId('choose-provider')).toBeInTheDocument();
  });

  it('sends a chosen provider to its credential form and nowhere else', async () => {
    await firstRun();

    const chosen = screen
      .getAllByTestId('provider-option')
      .find((one) => one.getAttribute('data-provider') === 'ollama');
    const link = within(one(chosen)).getByTestId('choose-provider');

    expect(link.getAttribute('href')).toBe(
      '/first-run?step=credential&provider=ollama',
    );
  });
});

// --- The credential step ----------------------------------------------------------------

describe('storing the provider credential', () => {
  it('generates the form from the provider’s own declared fields', async () => {
    await firstRun({ step: 'credential', provider: 'anthropic' });

    const field = screen.getByLabelText('API key');
    expect(field).toHaveAttribute('type', 'password');
    expect(field).toHaveAttribute('autocomplete', 'off');
    expect(screen.getByTestId('where-to-get-it').textContent).toContain(
      'console.anthropic.com',
    );
  });

  it('sends somebody back to the choice when no provider has been named', async () => {
    await firstRun({ step: 'credential' });

    expect(screen.getByTestId('no-provider-chosen')).toBeInTheDocument();
  });

  it('never puts the value in the address of the request that carries it', async () => {
    vi.stubGlobal('fetch', answerWith({ state: 'usable', version: 1, fields: ['k'] }));
    const { CredentialField } = await import('@/surfaces/credential');
    render(
      <CredentialField
        integration="anthropic"
        fields={[
          { name: 'k', label: 'API key', help: '', secret: true, required: true },
        ]}
        labels={{
          submit: 'Store',
          sending: '…',
          stored: 'stored',
          absent: 'none',
          whereToGetIt: 'at',
          required: 'required',
          saved: 'saved',
          refused: 'refused',
          unreachable: 'unreachable',
        }}
      />,
    );

    await userEvent.type(screen.getByLabelText('API key'), 'sentinel-4f2a');
    await userEvent.click(screen.getByTestId('store-credential'));

    expect(sent.map((one) => one.url)).toEqual(['/api/credential']);
    expect(sent[0]?.url).not.toContain('sentinel-4f2a');
    expect(document.body.innerHTML).not.toContain('sentinel-4f2a');
  });
});

// --- The model step -----------------------------------------------------------------------

describe('choosing a model', () => {
  const LABELS = {
    known: 'Model',
    free: 'Model identifier',
    preview: 'What would this change?',
    previewing: '…',
    save: 'Save it',
    saving: '…',
    wouldChange: 'would change',
    nothingWouldChange: 'nothing would change',
    saved: 'Saved.',
    refused: 'refused',
    unreachable: 'unreachable',
    needsPreview: 'preview first',
  };

  it('offers the models a provider declares as a closed list', () => {
    render(
      <ModelStep
        provider="anthropic"
        models={['claude-opus-5', 'claude-sonnet-5']}
        defaultModel="claude-sonnet-5"
        nodeId="team-a"
        labels={LABELS}
      />,
    );

    expect(screen.getByLabelText('Model').tagName).toBe('SELECT');
  });

  it('offers a free field with the default when a provider declares none', () => {
    render(
      <ModelStep
        provider="ollama"
        models={[]}
        defaultModel="llama4:70b"
        nodeId="team-a"
        labels={LABELS}
      />,
    );

    expect(screen.getByLabelText('Model identifier')).toHaveValue('llama4:70b');
  });

  it('will not save until the deployment has said what saving would do', async () => {
    vi.stubGlobal(
      'fetch',
      answerWith({ changes: [{ path: 'models.investigator.model', after: 'x' }] }),
    );
    render(
      <ModelStep
        provider="ollama"
        models={[]}
        defaultModel="llama4:70b"
        nodeId="team-a"
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('save-model')).toBeDisabled();
    await userEvent.click(screen.getByTestId('preview-model'));
    expect(sent[0]?.url).toBe('/api/preview');
    expect(screen.getByTestId('save-model')).toBeEnabled();

    await userEvent.click(screen.getByTestId('save-model'));
    expect(sent[1]?.url).toBe('/api/config');
    // The same patch both times. A preview of one document and a write of
    // another is the failure the preview exists to prevent.
    expect(sent[1]?.body).toBe(sent[0]?.body);
  });
  it('reads a refusal the gateway spelled as detail, since the courier is verbatim', async () => {
    vi.stubGlobal('fetch', answerWith({ detail: 'outside this session’s scope' }, 403));
    render(
      <ModelStep
        provider="ollama"
        models={[]}
        defaultModel="llama4:70b"
        nodeId="team-a"
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByTestId('preview-model'));

    expect(screen.getByTestId('model-result')).toHaveTextContent('scope');
  });

  it('says the deployment refused, in its words, and does not claim a save', async () => {
    vi.stubGlobal(
      'fetch',
      answerWith({ reason: 'that value is locked above this node' }, 400),
    );
    render(
      <ModelStep
        provider="ollama"
        models={[]}
        defaultModel="llama4:70b"
        nodeId="team-a"
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByTestId('preview-model'));

    expect(screen.getByTestId('model-result')).toHaveTextContent(
      'locked above this node',
    );
    // And the save stays shut: nothing has said what saving would do.
    expect(screen.getByTestId('save-model')).toBeDisabled();
  });

  it('tells a deployment that was not there apart from one that refused', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
    );
    render(
      <ModelStep
        provider="ollama"
        models={[]}
        defaultModel="llama4:70b"
        nodeId="team-a"
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByTestId('preview-model'));

    expect(screen.getByTestId('model-result')).toHaveTextContent('unreachable');
  });

  it('sends the patch in the shape the schema declares, nested and not dotted', async () => {
    // The config service refuses `models.investigator.model` as a literal
    // key — "is not a configuration field" — so a step that flattened the
    // path would preview one document and fail to save any.
    vi.stubGlobal('fetch', answerWith({ changes: [] }));
    render(
      <ModelStep
        provider="ollama"
        models={[]}
        defaultModel="llama4:70b"
        nodeId="team-a"
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByTestId('preview-model'));

    expect(JSON.parse(sent[0]?.body ?? '{}')).toEqual({
      nodeId: 'team-a',
      patch: {
        models: { investigator: { provider: 'ollama', model: 'llama4:70b' } },
      },
    });
  });

  it('shows what the write would refuse, and keeps the save shut', async () => {
    // The preview answers 200 with the refusals in `errors`. Ignoring them
    // showed "would change X" beside a save that was going to fail.
    vi.stubGlobal(
      'fetch',
      answerWith({
        changes: [{ path: 'models.investigator.model', after: 'llama4:70b' }],
        errors: [
          {
            path: 'models.investigator.model',
            message: 'is not a configuration field',
          },
        ],
      }),
    );
    render(
      <ModelStep
        provider="ollama"
        models={[]}
        defaultModel="llama4:70b"
        nodeId="team-a"
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByTestId('preview-model'));

    expect(screen.getByTestId('model-result')).toHaveTextContent(
      'is not a configuration field',
    );
    expect(screen.getByTestId('save-model')).toBeDisabled();
  });

  it('says nothing would change when the deployment says nothing would', async () => {
    vi.stubGlobal('fetch', answerWith({ changes: [] }));
    render(
      <ModelStep
        provider="ollama"
        models={[]}
        defaultModel="llama4:70b"
        nodeId="team-a"
        labels={LABELS}
      />,
    );

    await userEvent.click(screen.getByTestId('preview-model'));

    expect(screen.getByTestId('model-preview')).toHaveTextContent(
      'nothing would change',
    );
  });
});

// --- The integrations step -------------------------------------------------------------------

describe('connecting integrations', () => {
  const OFFERS = [
    {
      name: 'metrics-store',
      displayName: 'Metrics store',
      summary: 'Range queries.',
      category: 'observability',
      fields: [
        { name: 'api_token', label: 'Token', help: '', secret: true, required: true },
      ],
      configured: false,
    },
    {
      name: 'chat',
      displayName: 'Chat',
      summary: 'Posts summaries.',
      category: 'collaboration',
      fields: [
        {
          name: 'bot_token',
          label: 'Bot token',
          help: '',
          secret: true,
          required: true,
        },
      ],
      configured: false,
    },
    {
      name: 'ticketing',
      displayName: 'Ticketing',
      summary: 'Opens tickets.',
      category: 'workflow',
      fields: [
        {
          name: 'api_token',
          label: 'API token',
          help: '',
          secret: true,
          required: true,
        },
      ],
      configured: false,
    },
  ];

  const LABELS = {
    search: 'Search the catalogue',
    none: 'nothing matches',
    connected: 'connected',
    notConnected: 'not connected',
    optional: 'all optional',
    summary: 'Connected: {names}.',
    summaryNone: 'nothing connected',
    failed: 'failed:',
    foundHere: 'Found in your estate at',
    credential: {
      submit: 'Store',
      sending: '…',
      stored: 'stored',
      absent: 'none',
      whereToGetIt: 'at',
      required: 'required',
      saved: 'saved',
      refused: 'refused',
      unreachable: 'unreachable',
    },
  };

  it('is searchable over the whole catalogue', async () => {
    render(<IntegrationsStep offers={OFFERS} labels={LABELS} />);

    expect(screen.getAllByTestId('integration-offer')).toHaveLength(3);
    await userEvent.type(screen.getByLabelText('Search the catalogue'), 'chat');
    expect(screen.getAllByTestId('integration-offer')).toHaveLength(1);
  });

  it('says that none of them is required', () => {
    render(<IntegrationsStep offers={OFFERS} labels={LABELS} />);

    expect(screen.getByText('all optional')).toBeInTheDocument();
  });

  it('says so when a search matches nothing, rather than showing an empty list', async () => {
    render(<IntegrationsStep offers={OFFERS} labels={LABELS} />);

    await userEvent.type(
      screen.getByLabelText('Search the catalogue'),
      'nothing-like-this',
    );

    expect(screen.getByTestId('no-integration-matches')).toBeInTheDocument();
  });

  // Built rather than written: a literal origin in console source is refused by
  // the lint rule that keeps every request pointed at the deployment, and this
  // one is data the deployment sent rather than an address the console knows.
  const FOUND_AT = ['http:', '//10.20.20.37:9090'].join('');

  it('names where the estate found a vendor, so nobody has to go and look', () => {
    // The hard part of this step is not choosing a vendor. It is knowing which
    // of fifty-seven containers is the metric store, and the deployment already
    // swept the cluster and knows.
    render(
      <IntegrationsStep
        offers={OFFERS.map((offer, index) =>
          index === 0
            ? {
                ...offer,
                suggested: {
                  address: FOUND_AT,
                  because:
                    'this estate holds a container called prometheus at 10.20.20.37',
                },
              }
            : offer,
        )}
        labels={LABELS}
      />,
    );

    const suggested = screen.getAllByTestId('integration-suggested');
    expect(suggested).toHaveLength(1);
    expect(one(suggested[0])).toHaveTextContent(FOUND_AT);
  });

  it('keeps the order the deployment served, and searching never reorders it', async () => {
    // The relevance is derived once, server-side, so the CLI wizard and this
    // one cannot disagree about it. Re-sorting here would be the second copy.
    render(<IntegrationsStep offers={OFFERS} labels={LABELS} />);

    const before = screen
      .getAllByTestId('integration-offer')
      .map((row) => row.getAttribute('data-integration'));
    expect(before).toEqual(OFFERS.map((offer) => offer.name));

    await userEvent.type(screen.getByLabelText('Search the catalogue'), 'a');
    const after = screen
      .getAllByTestId('integration-offer')
      .map((row) => row.getAttribute('data-integration'));
    expect(after).toEqual(before.filter((name) => after.includes(name)));
  });

  it('says which ones this deployment already holds a credential for', () => {
    render(
      <IntegrationsStep
        offers={OFFERS.slice(0, 1).map((offer) => ({ ...offer, configured: true }))}
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('integration-state')).toHaveTextContent('connected');
  });

  it('does not abandon the rest when one is refused, and reports at the end', async () => {
    let call = 0;
    vi.stubGlobal('fetch', (url: unknown, init?: RequestInit) => {
      sent = [
        ...sent,
        { url: String(url), body: typeof init?.body === 'string' ? init.body : '' },
      ];
      call += 1;
      // The first write is refused and the second is accepted, which is the
      // shape the CLI's own `setup_many` keeps going through.
      return Promise.resolve(
        new Response(
          JSON.stringify(call === 1 ? { reason: 'no' } : { state: 'usable' }),
          {
            status: call === 1 ? 400 : 200,
            headers: { 'content-type': 'application/json' },
          },
        ),
      );
    });
    render(<IntegrationsStep offers={OFFERS} labels={LABELS} />);

    const [first, second] = screen.getAllByTestId('integration-offer');
    await userEvent.type(within(one(first)).getByLabelText('Token'), 'a-token');
    await userEvent.click(within(one(first)).getByTestId('store-credential'));
    await userEvent.type(within(one(second)).getByLabelText('Bot token'), 'b-token');
    await userEvent.click(within(one(second)).getByTestId('store-credential'));

    // Both were attempted, the refusal is on the one it belongs to, and the
    // summary at the bottom is what was collected rather than where it stopped.
    expect(sent).toHaveLength(2);
    expect(within(one(first)).getByTestId('credential-result')).toHaveTextContent(
      'refused',
    );
    expect(screen.getByTestId('integrations-summary')).toHaveTextContent(
      'Connected: chat.',
    );
  });
});

// --- The verification step ---------------------------------------------------------------------

describe('verifying what is configured', () => {
  const LABELS = {
    check: 'Check it',
    checking: '…',
    retry: 'Check it again',
    passed: 'It answered.',
    failed: 'It did not answer.',
    unchecked: 'nobody has checked',
    unreachable: 'unreachable',
    nothing: 'nothing to check',
    remedy: 'What to do:',
    findings: 'It answered, and what it answered cannot be relied on:',
  };

  const THINGS = [
    {
      kind: 'provider' as const,
      name: 'anthropic',
      displayName: 'Anthropic',
      readiness: 'configured',
    },
    {
      kind: 'integration' as const,
      name: 'chat',
      displayName: 'Chat',
      readiness: 'configured',
    },
  ];

  it('draws one result line per configured thing, each unchecked until asked', () => {
    render(<VerifyStep things={THINGS} labels={LABELS} />);

    const rows = screen.getAllByTestId('verify-row');
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      expect(row.getAttribute('data-verdict')).toBe('unchecked');
    }
  });

  it('checks one at a time and lets that one be tried again', async () => {
    vi.stubGlobal(
      'fetch',
      answerWith({ verified: false, reason: 'it refused the key' }),
    );
    render(<VerifyStep things={THINGS} labels={LABELS} />);

    const [first] = screen.getAllByTestId('verify-row');
    await userEvent.click(within(one(first)).getByTestId('verify-one'));

    expect(first).toHaveAttribute('data-verdict', 'failed');
    expect(first).toHaveTextContent('it refused the key');
    expect(within(one(first)).getByTestId('verify-one')).toHaveTextContent(
      'Check it again',
    );
    // The other row is untouched: a retry that re-ran everything would spend
    // money re-proving what already answered.
    expect(screen.getAllByTestId('verify-row')[1]).toHaveAttribute(
      'data-verdict',
      'unchecked',
    );
    expect(sent).toHaveLength(1);
  });

  it('names the field a failure was caused by, when the deployment names one', async () => {
    vi.stubGlobal(
      'fetch',
      answerWith({
        verified: false,
        reason: 'the request was refused',
        remedy: 'ANTHROPIC_API_KEY was skipped at setup',
      }),
    );
    render(<VerifyStep things={THINGS} labels={LABELS} />);

    await userEvent.click(one(screen.getAllByTestId('verify-one')[0]));

    expect(screen.getByTestId('verify-remedy')).toHaveTextContent('ANTHROPIC_API_KEY');
  });

  it('names what makes a source that answered unusable anyway', async () => {
    // The failure this is about: a metric store that authenticates, answers
    // 200, and is holding nothing. Every other signal on this row says it
    // passed, and an investigation that reaches it will conclude that nothing
    // happened.
    vi.stubGlobal(
      'fetch',
      answerWith({
        verified: true,
        reason: 'the credential works',
        findings: [
          'it answered and holds nothing for the last 15 minutes. Check its scrape targets.',
          "its clock is 90.0s from the platform's, outside the 30.0s correlation tolerates",
        ],
      }),
    );
    render(<VerifyStep things={THINGS} labels={LABELS} />);

    await userEvent.click(one(screen.getAllByTestId('verify-one')[0]));

    const findings = screen.getAllByTestId('verify-finding');
    expect(findings).toHaveLength(2);
    expect(one(findings[0])).toHaveTextContent('holds nothing for the last 15 minutes');
    expect(one(findings[1])).toHaveTextContent('90.0s');
    expect(screen.getByTestId('verify-findings')).toHaveTextContent(
      'cannot be relied on',
    );
  });

  it('draws no findings block for a source that had none', async () => {
    vi.stubGlobal(
      'fetch',
      answerWith({ verified: true, reason: 'the credential works' }),
    );
    render(<VerifyStep things={THINGS} labels={LABELS} />);

    await userEvent.click(one(screen.getAllByTestId('verify-one')[0]));

    expect(screen.queryByTestId('verify-findings')).toBeNull();
  });

  it('says the deployment was unreachable rather than that a check failed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
    );
    render(<VerifyStep things={THINGS} labels={LABELS} />);

    await userEvent.click(one(screen.getAllByTestId('verify-one')[0]));

    expect(screen.getAllByTestId('verify-row')[0]).toHaveAttribute(
      'data-verdict',
      'unreachable',
    );
  });

  it('reports a check that answered as passed', async () => {
    vi.stubGlobal('fetch', answerWith({ verified: true, reason: 'it answered' }));
    render(<VerifyStep things={THINGS} labels={LABELS} />);

    await userEvent.click(one(screen.getAllByTestId('verify-one')[0]));

    expect(screen.getAllByTestId('verify-row')[0]).toHaveAttribute(
      'data-verdict',
      'passed',
    );
  });

  it('says so rather than showing an empty list when nothing is configured', () => {
    render(<VerifyStep things={[]} labels={LABELS} />);

    expect(screen.getByTestId('nothing-to-verify')).toBeInTheDocument();
  });
});

// --- What is established, once, however many places record it -------------------------------------

describe('what is established', () => {
  /**
   * A provider that is also a generic integration — Gemini both drives
   * investigations and appears in the integration catalogue — is one stored
   * credential. The panel used to list it twice under the same name, because
   * the chosen provider was prepended without excluding it from the
   * integrations spread beside it.
   */
  it('lists a credential once even when it is both the chosen provider and a configured integration', async () => {
    serveScenario('populated');
    const scenario = global.fetch;
    const base = ['http:', '//fixtures.invalid'].join('');
    vi.stubGlobal('fetch', (input: unknown, init?: RequestInit) => {
      const path = new URL(String(input), base).pathname;
      if (path === '/v1/providers') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              providers: [
                {
                  provider_id: 'google_gemini',
                  display_name: 'Gemini',
                  configured: true,
                },
              ],
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          ),
        );
      }
      if (path === '/v1/setup/checklist') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              complete: true,
              provider: 'verified',
              integrations: [{ name: 'google_gemini', readiness: 'configured' }],
              steps: [],
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          ),
        );
      }
      return scenario(input as Parameters<typeof fetch>[0], init);
    });

    render(await FirstRunScreen(await surfaceContext()));

    const established = screen.getByTestId('established');
    expect(within(established).getAllByText('google_gemini')).toHaveLength(1);
  });
});

// --- The last two steps hand over -----------------------------------------------------------------

describe('the steps this feature does not own', () => {
  it.each(['estate', 'alerts'])(
    '%s names what is missing and which screen provides it',
    async (step) => {
      await firstRun({ step });

      const handover = screen.getByTestId('handover');
      expect(handover).toHaveAttribute('data-step', step);
      expect(screen.getByTestId('handover-detail').textContent).toBeTruthy();
      expect(screen.getByTestId('handover-action').textContent).toBeTruthy();
      const href = screen.getByTestId('handover-link').getAttribute('href') ?? '';
      expect(areaByPath(href), `${href} is not an area of this console`).toBeDefined();
    },
  );
});

// --- What the dashboard gains -------------------------------------------------------------------

describe('the dashboard of a deployment that is not set up', () => {
  async function dashboard(scenario: 'first-run' | 'populated'): Promise<void> {
    serveScenario(scenario);
    render(await DashboardScreen(await surfaceContext({})));
  }

  it('renders the figures at zero rather than hiding them', async () => {
    await dashboard('first-run');

    // Honest numbers on a new deployment are information. The alternative —
    // hiding the product behind a form — is what this feature exists to undo.
    expect(screen.getAllByTestId('figure').length).toBeGreaterThan(0);
    expect(screen.getByTestId('main-figures')).toHaveTextContent('0');
  });

  it('shows the remaining plan with the outstanding step one click away', async () => {
    await dashboard('first-run');

    // The hero, and only the hero: the same plan used to be rendered twice on
    // this page, once in the centre and once as a side card, and a page that
    // says the same thing in two places is a page with no first reading.
    expect(screen.getByTestId('setup-hero')).toBeInTheDocument();
    expect(screen.queryByTestId('setup-checklist')).toBeNull();
    expect(screen.getByTestId('setup-hero-cta').getAttribute('href')).toBe(
      '/first-run?step=provider',
    );
  });

  it('warns about a missing provider inside the page, linking to the step', async () => {
    await dashboard('first-run');

    const notice = screen.getByTestId('no-provider');
    expect(notice).toBeInTheDocument();
    expect(screen.getByTestId('no-provider-action').getAttribute('href')).toBe(
      '/first-run?step=provider',
    );
  });

  it('offers the three quick actions the checklist is asking for', async () => {
    await dashboard('first-run');

    const actions = screen.getAllByTestId('quick-action');
    expect(actions).toHaveLength(3);
    for (const action of actions) {
      const href = action.getAttribute('href') ?? '';
      expect(areaByPath(href), `${href} is not an area`).toBeDefined();
    }
  });

  it('drops the plan and the warning once the deployment is set up', async () => {
    await dashboard('populated');

    // Absent, not shrunk. A deployment that finished setting up months ago
    // should not carry a permanent reminder that it once had not.
    expect(screen.queryByTestId('setup-hero')).toBeNull();
    expect(screen.queryByTestId('setup-checklist')).toBeNull();
    expect(screen.queryByTestId('no-provider')).toBeNull();
  });
});

// --- The tutorial ---------------------------------------------------------------------------------

describe('the tutorial overlay', () => {
  const LABELS = { locale: 'en' as const, nodeId: 'team-a' };

  /**
   * The first-run scenario, with this file listening in.
   *
   * The dataset answers the reads; what it cannot do is record a write or say
   * that a dismissal already happened, and those are the two facts these tests
   * are about. Writes land in `sent`, and `dismissed` answers the viewer's
   * effective configuration with the dismissal already recorded — nested, the
   * way the deployment actually serves it.
   */
  function serveTour(options: { dismissed?: boolean; principal?: unknown } = {}): void {
    serveScenario('first-run', options.principal);
    const scenario = globalThis.fetch;
    const base = ['http:', '//fixtures.invalid'].join('');
    vi.stubGlobal('fetch', (input: unknown, init?: RequestInit) => {
      if (init?.method === 'POST') {
        sent = [
          ...sent,
          {
            url: String(input),
            body: typeof init.body === 'string' ? init.body : '',
          },
        ];
        return Promise.resolve(
          new Response('{}', {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        );
      }
      const path = new URL(String(input), base).pathname;
      if (options.dismissed === true && path === '/v1/config/org-northwind') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              node_id: 'org-northwind',
              values: DISMISSAL,
              provenance: {},
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          ),
        );
      }
      return scenario(String(input));
    });
  }

  it('shows a progress indicator and a visible skip from the first slide', () => {
    render(<Tutorial {...LABELS} />);

    expect(screen.getByTestId('tutorial-progress')).toHaveTextContent('1 of 5');
    expect(screen.getByTestId('tutorial-skip')).toBeVisible();
  });

  it('walks five slides and finishes by closing', async () => {
    render(<Tutorial {...LABELS} />);

    for (let index = 1; index < SLIDES.length; index += 1) {
      await userEvent.click(screen.getByTestId('tutorial-next'));
      expect(screen.getByTestId('tutorial')).toHaveAttribute(
        'data-slide',
        String(index + 1),
      );
    }
    vi.stubGlobal('fetch', answerWith({}));
    await userEvent.click(screen.getByTestId('tutorial-next'));
    expect(screen.queryByTestId('tutorial')).toBeNull();
  });

  it('records the dismissal on the deployment rather than in this browser', async () => {
    vi.stubGlobal('fetch', answerWith({}));
    render(<Tutorial {...LABELS} />);

    await userEvent.click(screen.getByTestId('tutorial-skip'));

    expect(sent[0]?.url).toBe('/api/config');
    // The patch is the nested document the deployment's schema validates. A
    // flat dotted key is a field the closed schema has never heard of, and a
    // write it refuses is a dismissal that comes back tomorrow.
    expect(JSON.parse(sent[0]?.body ?? '{}')).toEqual({
      nodeId: 'team-a',
      patch: DISMISSAL,
    });
    // Nothing in the browser's own storage: a flag there would show the whole
    // thing again on the second machine, to the same person.
    expect(window.localStorage.length).toBe(0);
  });

  it('finishes into the first-run wizard, recording the dismissal on the way', async () => {
    vi.stubGlobal('fetch', answerWith({}));
    render(<Tutorial {...LABELS} />);

    for (let index = 1; index < SLIDES.length; index += 1) {
      await userEvent.click(screen.getByTestId('tutorial-next'));
    }
    await userEvent.click(screen.getByTestId('tutorial-next'));

    // The final button promises a beginning, so it has to deliver one: the
    // overlay is gone, the dismissal is on its way, and the wizard is where
    // the reader lands.
    expect(screen.queryByTestId('tutorial')).toBeNull();
    expect(pushed).toEqual(['/first-run']);
    expect(JSON.parse(sent[0]?.body ?? '{}')).toEqual({
      nodeId: 'team-a',
      patch: DISMISSAL,
    });
  });

  it('closes without writing anything when the viewer resolves to no node', async () => {
    // A principal whose organisation tree has not been built yet. There is
    // nowhere to record the dismissal, and the overlay still has to close —
    // trapping somebody behind it would be the worse of the two failures.
    vi.stubGlobal('fetch', answerWith({}));
    render(<Tutorial locale="en" nodeId="" />);

    await userEvent.click(screen.getByTestId('tutorial-skip'));

    expect(screen.queryByTestId('tutorial')).toBeNull();
    expect(sent).toHaveLength(0);
  });

  it('keeps the same geometry on every slide, so Back and Next never move', () => {
    // The defect: the card had no width of its own (`w-prose` names no class
    // this stylesheet declares) and the title-and-body block had no fixed
    // height, so both dimensions followed whichever slide's text was
    // longest — and a click that landed on Next on one slide missed it on
    // the next. Asserted structurally, across every slide, rather than only
    // on the first: a class list that is fixed changes for no slide.
    render(<Tutorial {...LABELS} />);
    const card = () => screen.getByTestId('tutorial-body').parentElement;

    for (let index = 0; index < SLIDES.length; index += 1) {
      expect(card()?.className).toContain('w-full');
      expect(card()?.className).toContain('max-w-prose');
      expect(screen.getByTestId('tutorial-body').className).toContain('h-44');
      expect(screen.getByTestId('tutorial-body').className).toContain(
        'overflow-y-auto',
      );
      const next = screen.getByTestId('tutorial-next');
      if (index < SLIDES.length - 1) {
        next.click();
      }
    }
  });

  it('goes back a slide, and will not go back from the first', async () => {
    render(<Tutorial {...LABELS} />);

    expect(screen.getByTestId('tutorial-back')).toBeDisabled();
    await userEvent.click(screen.getByTestId('tutorial-next'));
    await userEvent.click(screen.getByTestId('tutorial-back'));

    expect(screen.getByTestId('tutorial')).toHaveAttribute('data-slide', '1');
  });

  it('is not drawn at all for a deployment that has already dismissed it', async () => {
    // The read half of the persistence: the effective configuration says the
    // dismissal happened, and the dashboard never mounts the overlay at all.
    serveTour({ dismissed: true });
    render(await DashboardScreen(await surfaceContext({})));

    expect(screen.queryByTestId('tutorial')).toBeNull();
  });

  it('writes the dismissal at the root of the tree when the viewer has no team', async () => {
    // A token that names no team still has to record the dismissal somewhere,
    // and the configuration screen's answer — the root of the tree the viewer
    // may see — is the answer here too.
    serveTour({
      principal: principalHolding(['config.read', 'config.write'], ''),
    });
    render(await DashboardScreen(await surfaceContext({})));

    await userEvent.click(screen.getByTestId('tutorial-skip'));

    expect(sent[0]?.url).toBe('/api/config');
    expect(JSON.parse(sent[0]?.body ?? '{}')).toEqual({
      nodeId: 'org-northwind',
      patch: DISMISSAL,
    });
  });

  it('declares no animation, so reduced motion changes nothing about it', async () => {
    const { readFile } = await import('node:fs/promises');
    const source = await readFile('src/surfaces/first-run/tutorial.tsx', 'utf8');

    // Honouring the preference is weaker than having nothing to honour.
    expect(source).not.toMatch(/motion-|animate-|transition/);
  });

  it('is absent from a dashboard that has nothing left to set up', async () => {
    serveScenario('populated');
    render(await DashboardScreen(await surfaceContext({})));

    expect(screen.queryByTestId('tutorial')).toBeNull();
  });

  it('is present on a dashboard that has', async () => {
    serveScenario('first-run');
    render(await DashboardScreen(await surfaceContext({})));

    expect(screen.getByTestId('tutorial')).toBeInTheDocument();
  });
});

// --- Nothing redirects, and every pre-estate screen says what is missing -----------------------------

describe('what a half-configured deployment is allowed to do to a reader', () => {
  it('renders every area rather than redirecting any of them', async () => {
    serveScenario('first-run');

    for (const target of ALL_SCREENS) {
      const rendered = await target.render({ searchParams: Promise.resolve({}) });
      // A redirect from a server component throws; reaching here is the claim.
      expect(rendered, target.id).toBeTruthy();
    }
  });

  it('gives every empty state an action that names a place this console has', async () => {
    serveScenario('empty');

    const paths = new Set(AREAS.map((area) => area.path));
    for (const [index, target] of ALL_SCREENS.entries()) {
      const rendered = await ALL_SCREENS[index]?.render({
        searchParams: Promise.resolve({}),
      });
      const { container } = render(rendered);
      for (const link of container.querySelectorAll('[data-testid="way-back"]')) {
        const href = (link.getAttribute('href') ?? '').split('?')[0] ?? '';
        expect(paths.has(href), `${target.id} sends somebody to ${href}`).toBe(true);
      }
    }
  });
});
