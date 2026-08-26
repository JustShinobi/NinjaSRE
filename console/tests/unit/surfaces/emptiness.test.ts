import { describe, expect, it } from 'vitest';

import { INVESTIGATION_STEP, type DeploymentSetup } from '@/surfaces/first-run/plan';
import { extractionCause, setupCause } from '@/surfaces/emptiness';

/**
 * `setupCause`'s own two properties: it is dependency-scoped rather than a
 * bare countdown, and it stops speaking the moment the step that actually
 * gates the caller is done — however many other steps a deployment still
 * owes elsewhere.
 */

function setup(
  steps: Readonly<Record<string, 'done' | 'ready' | 'blocked'>>,
): DeploymentSetup {
  return {
    complete: Object.values(steps).every((state) => state === 'done'),
    provider: 'absent',
    integrations: [],
    modelChosen: false,
    providerName: '',
    next: '',
    steps: Object.entries(steps).map(([name, state]) => ({
      name,
      state,
      title: `Title of ${name}`,
    })),
  };
}

describe('a cause scoped to the dependency the caller actually names', () => {
  it('says nothing once the named step is done, even with other steps still owing', () => {
    const deployment = setup({
      'durable-credential': 'done',
      'model-provider': 'blocked',
      'infrastructure-source': 'blocked',
      'investigation-runtime': 'blocked',
      [INVESTIGATION_STEP]: 'done',
    });

    expect(setupCause('en', deployment, INVESTIGATION_STEP)).toBeNull();
  });

  it('names the pending step that actually justifies the cause, not a count', () => {
    const deployment = setup({
      'durable-credential': 'done',
      'model-provider': 'done',
      'infrastructure-source': 'done',
      'investigation-runtime': 'done',
      [INVESTIGATION_STEP]: 'ready',
    });

    const cause = setupCause('en', deployment, INVESTIGATION_STEP);

    expect(cause).not.toBeNull();
    expect(cause?.body).toContain(`Title of ${INVESTIGATION_STEP}`);
    expect(cause?.body).not.toMatch(/\d+\s*step\(s\)/i);
  });

  it('never claims investigations cannot run — only names the pending step', () => {
    const deployment = setup({ 'durable-credential': 'ready' });

    const cause = setupCause('en', deployment, 'durable-credential');

    expect(cause?.body).not.toMatch(/cannot run until/i);
  });

  it('is null when this deployment declares nothing about the named step', () => {
    const deployment = setup({ 'durable-credential': 'ready' });

    expect(setupCause('en', deployment, 'a-step-nobody-declared')).toBeNull();
  });
});

/**
 * The cause a corpus has when the chain above it plainly ran.
 *
 * "An episode is written when an investigation ends, and none has been
 * written yet" is the mechanism, and on a deployment with fifty finished
 * investigations behind it the second half of that sentence is false. The
 * screen was reading as patience — nothing has happened yet — while every
 * attempt to write an episode was failing, and the reader had no way to tell
 * those two apart. So where investigations have finished and the corpus is
 * still empty, the screen says *that*, and points at the step between the
 * two that a person can actually go and look at.
 *
 * What it deliberately does not do is name a failure it cannot read. The
 * console has no endpoint that serves why extraction failed; it has the count
 * of finished investigations and the size of the corpus, and it says only what
 * those two facts support.
 */
describe('a corpus that is empty behind investigations that finished', () => {
  it('says nothing while no investigation has finished', () => {
    expect(extractionCause('en', 0)).toBeNull();
  });

  it('names how many finished, rather than repeating that none has', () => {
    const cause = extractionCause('en', 50);

    expect(cause).not.toBeNull();
    expect(cause?.body).toContain('50');
    expect(cause?.body).not.toMatch(/none has (been written|ended)/i);
  });

  it('sends the reader to the models each role uses', () => {
    expect(extractionCause('en', 1)?.href).toBe('/settings/models-providers');
  });

  it('claims no failure it cannot read', () => {
    const body = extractionCause('en', 3)?.body ?? '';

    expect(body, 'the console cannot read a provider error').not.toMatch(
      /connection error|credential|unauthorised|unauthorized/i,
    );
  });
});
