import { describe, expect, it } from 'vitest';

import {
  WIZARD_STEPS,
  currentStep,
  outstanding,
  planFor,
  readSetup,
  stepAt,
  type DeploymentSetup,
} from '@/surfaces/first-run/plan';

/**
 * Where the guided first run thinks you are, and why nothing here is state.
 *
 * The whole of the resumability requirement is this module. There is no wizard
 * state in the browser: the current step is *derived* from what the deployment
 * says about itself, so closing the tab after the credential step and coming
 * back is the same computation as never having left. A cursor kept in a cookie
 * would be a cursor that disagrees with the deployment the first time somebody
 * runs the CLI wizard instead.
 */

function setup(over: Partial<DeploymentSetup> = {}): DeploymentSetup {
  return {
    complete: false,
    provider: 'absent',
    integrations: [],
    steps: [],
    modelChosen: false,
    providerName: '',
    ...over,
  };
}

describe('the seven steps', () => {
  it('are the order the platform is set up in, and nothing else', () => {
    expect([...WIZARD_STEPS]).toEqual([
      'provider',
      'credential',
      'model',
      'integrations',
      'verify',
      'estate',
      'alerts',
    ]);
  });

  it('answers to a name it has, and to nothing else', () => {
    expect(stepAt('model')).toBe('model');
    expect(stepAt('nowhere')).toBeUndefined();
    expect(stepAt(null)).toBeUndefined();
  });
});

describe('where a deployment is', () => {
  it('is finished when the deployment says it is, whatever the finer view thinks', () => {
    // Seven steps are a finer view of the platform's four. A finer view that
    // contradicted the coarser one would have a console and a terminal
    // disagreeing about a deployment that is done.
    const done = setup({ complete: true });

    expect(currentStep(done)).toBe('alerts');
    expect(outstanding(done)).toBe(0);
  });

  it('starts at the provider when nothing holds a credential', () => {
    expect(currentStep(setup())).toBe('provider');
  });

  it('is at the model once a provider credential is stored and unchecked', () => {
    // The step the browser being killed after the credential form resumes at.
    // Choosing a provider and storing its credential are one act — there is
    // nothing a deployment records about the first without the second.
    expect(currentStep(setup({ provider: 'configured' }))).toBe('model');
  });

  it('is at the integrations once a model is named', () => {
    expect(currentStep(setup({ provider: 'configured', modelChosen: true }))).toBe(
      'integrations',
    );
  });

  it('is at the verification once something is configured and unverified', () => {
    expect(
      currentStep(
        setup({
          provider: 'configured',
          modelChosen: true,
          integrations: [{ name: 'metrics-store', readiness: 'configured' }],
        }),
      ),
    ).toBe('verify');
  });

  it('does not ask for the provider to be checked twice under its two names', () => {
    // A provider that is also a catalogue integration — the Gemini case — is
    // one stored credential and one thing to check. Counting it a second time
    // as an integration made the verification step uncompletable: the row that
    // would have satisfied it is the row the screen deliberately does not show.
    expect(
      currentStep(
        setup({
          provider: 'verified',
          providerName: 'google_gemini',
          modelChosen: true,
          integrations: [
            { name: 'google_gemini', readiness: 'configured' },
            { name: 'metrics-store', readiness: 'verified' },
          ],
          steps: [{ name: 'infrastructure-source', state: 'ready' }],
        }),
      ),
    ).toBe('estate');
  });

  it('still needs an integration that is not the provider to answer', () => {
    expect(
      currentStep(
        setup({
          provider: 'verified',
          providerName: 'google_gemini',
          modelChosen: true,
          integrations: [
            { name: 'google_gemini', readiness: 'verified' },
            { name: 'metrics-store', readiness: 'configured' },
          ],
        }),
      ),
    ).toBe('verify');
  });

  it('is at the estate once the provider and every integration have answered', () => {
    expect(
      currentStep(
        setup({
          provider: 'verified',
          modelChosen: true,
          integrations: [{ name: 'metrics-store', readiness: 'verified' }],
          steps: [{ name: 'infrastructure-source', state: 'ready' }],
        }),
      ),
    ).toBe('estate');
  });

  it('is at the alerts once the estate exists', () => {
    expect(
      currentStep(
        setup({
          provider: 'verified',
          modelChosen: true,
          integrations: [{ name: 'metrics-store', readiness: 'verified' }],
          steps: [
            { name: 'infrastructure-source', state: 'done' },
            { name: 'first-investigation', state: 'ready' },
          ],
        }),
      ),
    ).toBe('alerts');
  });

  it('stays on the last step when everything is done, rather than falling off the end', () => {
    expect(
      currentStep(
        setup({
          complete: true,
          provider: 'verified',
          modelChosen: true,
          integrations: [{ name: 'metrics-store', readiness: 'verified' }],
          steps: [
            { name: 'infrastructure-source', state: 'done' },
            { name: 'first-investigation', state: 'done' },
          ],
        }),
      ),
    ).toBe('alerts');
  });
});

describe('reopening a step that is already done', () => {
  it('honours an address that names one', () => {
    const done = setup({ provider: 'configured', modelChosen: true });

    expect(currentStep(done, 'provider')).toBe('provider');
    expect(currentStep(done, 'credential')).toBe('credential');
  });

  it('ignores an address that names something that is not a step', () => {
    expect(currentStep(setup(), 'the-moon')).toBe('provider');
  });
});

describe('the list of steps the screen draws', () => {
  it('marks exactly one current, and every earlier one done', () => {
    const plan = planFor(setup({ provider: 'configured' }));

    expect(plan.filter((entry) => entry.current)).toHaveLength(1);
    expect(plan.find((entry) => entry.step === 'provider')?.done).toBe(true);
    expect(plan.find((entry) => entry.step === 'credential')?.done).toBe(true);
    expect(plan.find((entry) => entry.step === 'model')?.current).toBe(true);
    expect(plan.find((entry) => entry.step === 'model')?.done).toBe(false);
  });

  it('keeps a completed step reachable, which is what reopening means', () => {
    const plan = planFor(setup({ provider: 'configured' }));
    const provider = plan.find((entry) => entry.step === 'provider');

    expect(provider?.href).toBe('/first-run?step=provider');
  });

  it('counts what the deployment itself reports as not done, never a client tally', () => {
    // Deliberately not built from WIZARD_STEPS or from stepDone: a client-only
    // count of the seven UI screens is exactly the recomputation this function
    // must not do. `provider` and `modelChosen` below are irrelevant to it —
    // only `steps[].state` is.
    expect(outstanding(setup())).toBe(0);
    expect(
      outstanding(
        setup({
          provider: 'configured',
          modelChosen: true,
          steps: [
            { name: 'durable-credential', state: 'done' },
            { name: 'model-provider', state: 'ready' },
            { name: 'infrastructure-source', state: 'blocked' },
          ],
        }),
      ),
    ).toBe(2);
  });
});

describe('reading the deployment out of what the API answered', () => {
  it('takes the readiness vocabulary as the deployment spells it', () => {
    const read = readSetup(
      {
        complete: false,
        provider: 'configured',
        next: 'model-provider',
        steps: [
          {
            name: 'model-provider',
            state: 'ready',
            title: 'x',
            detail: '',
            action: '',
          },
        ],
        integrations: [{ name: 'metrics-store', readiness: 'absent' }],
      },
      // Values as the deployment actually answers them: a nested document,
      // because the schema refuses a dotted path as a literal key.
      { models: { investigator: { model: 'claude-sonnet-5' } } },
    );

    expect(read.provider).toBe('configured');
    expect(read.modelChosen).toBe(true);
    expect(read.integrations).toEqual([{ name: 'metrics-store', readiness: 'absent' }]);
  });

  it('reads a deployment that answered nothing as one that has done nothing', () => {
    // A checklist read that failed must not present itself as a finished setup:
    // the one direction this may never be wrong in.
    const read = readSetup(undefined, undefined);

    expect(read.complete).toBe(false);
    expect(read.provider).toBe('absent');
    expect(read.modelChosen).toBe(false);
    expect(currentStep(read)).toBe('provider');
  });
});
