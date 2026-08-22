import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  MODELS_ENDPOINT,
  ProviderCredentialStep,
  type ProviderCredentialStepLabels,
} from '@/surfaces/first-run/provider-credential';

/**
 * Storing a provider key and finding out, there and then, whether it works.
 *
 * A key that is stored and a key that is accepted are two different facts, and
 * the whole reason this step asks the second question is that the deployment
 * used to answer only the first: an operator saved a key, walked to the model
 * screen, and was told the credential was missing. The listing call is the
 * cheapest question that can only be answered by a working key — it spends no
 * tokens, and what it comes back with is the list to choose a model from.
 */

const CREDENTIAL_LABELS = {
  submit: 'Save the key',
  sending: 'Saving…',
  stored: 'Stored in the vault; never shown again.',
  absent: 'No fields are declared.',
  whereToGetIt: 'Get it from',
  required: 'Every required field needs a value.',
  saved: 'Stored.',
  refused: 'The deployment refused:',
  unreachable: 'The deployment could not be reached.',
  minScope: 'Minimum permission:',
  guide: 'Step-by-step guide',
};

const MODEL_LABELS = {
  known: 'Model',
  free: 'Model identifier',
  preview: 'What would this change?',
  previewing: 'Asking…',
  save: 'Save it',
  saving: 'Saving…',
  wouldChange: 'Saving this would resolve to:',
  nothingWouldChange: 'Nothing would change.',
  saved: 'Saved.',
  refused: 'Refused:',
  unreachable: 'The deployment could not be reached.',
  needsPreview: 'See what it would change first.',
  fieldLabels: {},
};

const LABELS: ProviderCredentialStepLabels = {
  credential: CREDENTIAL_LABELS,
  model: MODEL_LABELS,
  checking: 'Asking the provider whether this key works…',
  accepted: 'The provider accepted this key and listed the models below.',
  notListed: 'The key is stored, but the provider would not list its models:',
  chooseModel: 'Choose the model this deployment thinks with',
};

const FIELDS = [
  { name: 'api_key', label: 'API key', help: '', secret: true, required: true },
];

let asked: string[] = [];
/** What the listing call answers with, set per test. */
let listing: unknown = null;

beforeEach(() => {
  asked = [];
  vi.stubGlobal('fetch', (url: unknown) => {
    const address = String(url);
    asked.push(address);
    if (address.startsWith(MODELS_ENDPOINT)) {
      return Promise.resolve(
        new Response(JSON.stringify(listing), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    }
    return Promise.resolve(
      new Response(JSON.stringify({ ok: true, state: 'configured', version: 1 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Type a key and press save. */
async function store(): Promise<void> {
  await userEvent.type(screen.getByLabelText('API key'), 'a-key-somebody-pasted');
  await userEvent.click(screen.getByTestId('store-credential'));
}

function mount(): void {
  render(
    <ProviderCredentialStep
      provider="google_gemini"
      fields={FIELDS}
      whereToGetIt="aistudio.google.com, under API keys."
      staticModels={['gemini-pro-latest']}
      defaultModel="gemini-pro-latest"
      nodeId="org:acme"
      labels={LABELS}
    />,
  );
}

describe('the first-run credential step', () => {
  it('asks the provider what it serves as soon as the key is stored', async () => {
    listing = {
      source: 'endpoint',
      reason: '',
      models: [
        { model_id: 'gemini-3.6-flash', display_name: 'Gemini 3.6 Flash' },
        { model_id: 'gemini-2.5-pro', display_name: 'Gemini 2.5 Pro' },
      ],
    };
    mount();
    await store();

    await waitFor(() => {
      expect(screen.getByTestId('credential-check')).toHaveTextContent(LABELS.accepted);
    });
    // The cache is bypassed: the key that was just written is a different key
    // from the one whatever is cached was fetched with.
    const listingCall = asked.find((address) => address.startsWith(MODELS_ENDPOINT));
    expect(listingCall).toContain('provider=google_gemini');
    expect(listingCall).toContain('refresh=true');
  });

  it('offers the endpoint list to choose from, in the same step', async () => {
    listing = {
      source: 'endpoint',
      reason: '',
      models: [
        { model_id: 'gemini-3.6-flash', display_name: 'Gemini 3.6 Flash' },
        { model_id: 'gemini-2.5-pro', display_name: 'Gemini 2.5 Pro' },
      ],
    };
    mount();
    await store();

    const chooser = await screen.findByLabelText('Model');
    const offered = Array.from(chooser.querySelectorAll('option')).map(
      (option) => option.value,
    );
    expect(offered).toEqual(['gemini-3.6-flash', 'gemini-2.5-pro']);
  });

  it('says why the list is the static one when the endpoint would not answer', async () => {
    listing = {
      source: 'static',
      reason: "google_gemini's listing endpoint answered 400",
      models: [{ model_id: 'gemini-pro-latest', display_name: 'gemini-pro-latest' }],
    };
    mount();
    await store();

    const check = await screen.findByTestId('credential-check');
    expect(check).toHaveTextContent(LABELS.notListed);
    // The provider's own words, not a translation of them.
    expect(check).toHaveTextContent('answered 400');
    // And a model can still be chosen — a listing that would not answer is not
    // a reason to strand somebody on the step.
    expect(await screen.findByLabelText('Model')).toBeInTheDocument();
  });

  it('names the deployment, not the provider, when the ask itself never left', async () => {
    vi.stubGlobal('fetch', (url: unknown) => {
      const address = String(url);
      asked.push(address);
      if (address.startsWith(MODELS_ENDPOINT)) return Promise.reject(new Error('down'));
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });
    mount();
    await store();

    const check = await screen.findByTestId('credential-check');
    // The console's own process could not reach the deployment. Saying the
    // provider refused the key would send somebody to the wrong console.
    expect(check).toHaveTextContent(CREDENTIAL_LABELS.unreachable);
    // The shipped list still stands in, so the step is not a dead end.
    expect(await screen.findByLabelText('Model')).toBeInTheDocument();
  });

  it('says it is asking while the provider is being asked', async () => {
    let answer: (body: Response) => void = () => {
      throw new Error('the listing was answered before it was asked for');
    };
    vi.stubGlobal('fetch', (url: unknown) => {
      const address = String(url);
      if (address.startsWith(MODELS_ENDPOINT)) {
        return new Promise<Response>((resolve) => {
          answer = resolve;
        });
      }
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });
    mount();
    await store();

    expect(await screen.findByTestId('credential-checking')).toHaveTextContent(
      LABELS.checking,
    );
    answer(
      new Response(JSON.stringify({ source: 'endpoint', reason: '', models: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    await waitFor(() => {
      expect(screen.queryByTestId('credential-checking')).not.toBeInTheDocument();
    });
  });

  it('falls back to the shipped list when the answer names no models at all', async () => {
    // A refusal that carries no `reason` and no models: the step still has to
    // offer something to choose from rather than an empty chooser.
    listing = { source: 'static' };
    mount();
    await store();

    const chooser = await screen.findByLabelText('Model');
    expect(
      Array.from(chooser.querySelectorAll('option')).map((option) => option.value),
    ).toEqual(['gemini-pro-latest']);
    expect(screen.getByTestId('credential-check')).toHaveTextContent(LABELS.notListed);
  });

  it('starts the chooser on something the endpoint actually serves', async () => {
    // The provider has retired this build's default. Seeding the chooser with
    // it would offer to save a model the endpoint no longer has.
    listing = {
      source: 'endpoint',
      reason: '',
      models: [
        { model_id: 'gemini-4.0-pro', display_name: 'Gemini 4.0 Pro' },
        { display_name: 'a row with no identifier at all' },
      ],
    };
    mount();
    await store();

    const chooser = await screen.findByLabelText('Model');
    expect(chooser).toHaveValue('gemini-4.0-pro');
    // The unusable row is dropped rather than offered as an empty option.
    expect(Array.from(chooser.querySelectorAll('option'))).toHaveLength(1);
  });

  it('leaves a free field for a provider nobody publishes a list for', async () => {
    // Ollama's shape: no static list, and a listing answer this cannot read.
    // The step has to let a model identifier be typed rather than show an
    // empty chooser, and it must say nothing about where it got a list from.
    listing = {
      source: 'static',
      reason: 'ollama declares no listing endpoint',
      models: 'not a list',
    };
    render(
      <ProviderCredentialStep
        provider="ollama"
        fields={FIELDS}
        staticModels={[]}
        defaultModel=""
        nodeId="org:acme"
        labels={LABELS}
      />,
    );
    // No `whereToGetIt`: a local provider has nowhere to send anybody.
    expect(screen.queryByTestId('where-to-get-it')).not.toBeInTheDocument();
    await store();

    expect(await screen.findByLabelText(MODEL_LABELS.free)).toBeInTheDocument();
    expect(screen.queryByLabelText(MODEL_LABELS.known)).not.toBeInTheDocument();
    expect(screen.getByTestId('credential-check')).toHaveTextContent(
      'ollama declares no listing endpoint',
    );
  });

  it('does not ask anything until something has been stored', () => {
    listing = { source: 'endpoint', reason: '', models: [] };
    mount();

    expect(asked).toEqual([]);
    expect(screen.queryByTestId('credential-check')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Model')).not.toBeInTheDocument();
  });
});
