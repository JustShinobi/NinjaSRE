import { describe, expect, it } from 'vitest';

import { INVESTIGATION_STEP, type DeploymentSetup } from '@/surfaces/first-run/plan';
import { setupCause } from '@/surfaces/emptiness';

/**
 * `setupCause`'s own two properties: it is dependency-scoped rather than a
 * bare countdown, and it stops speaking the moment the step that actually
 * gates the caller is done — however many other steps a deployment still
 * owes elsewhere.
 */

function setup(steps: Readonly<Record<string, 'done' | 'ready' | 'blocked'>>): DeploymentSetup {
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
