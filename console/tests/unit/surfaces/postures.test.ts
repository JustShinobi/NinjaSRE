import { describe, expect, it } from 'vitest';

import { postureLabel, postureLabels } from '@/surfaces/postures';

/**
 * What an autonomy level permits, at the point somebody chooses it.
 *
 * The deployment sends these as slugs, and every control that offered them
 * offered the slug — a `<Select>` whose most consequential option was
 * indistinguishable from its least. This is the most consequential decision in
 * the product, and a posture an operator misreads is a posture they did not
 * choose.
 */

describe('what a posture is called', () => {
  it('says what the most dangerous one actually does', () => {
    const said = postureLabel('en', 'act_silently');

    expect(said).not.toBe('act_silently');
    expect(said.toLowerCase()).toContain('reports nothing');
  });

  it('distinguishes acting on low risk from acting on anything', () => {
    expect(postureLabel('en', 'act_on_low_risk')).not.toBe(
      postureLabel('en', 'act_and_report'),
    );
  });

  it('falls back to the slug for a level this console has no words for', () => {
    // The levels come from the deployment, not from here. A fifth one must
    // still render a usable control rather than an empty option.
    expect(postureLabel('en', 'act_on_tuesdays')).toBe('act_on_tuesdays');
  });

  it('translates rather than carrying English into another locale', () => {
    expect(postureLabel('pt-BR', 'propose_only')).not.toBe(
      postureLabel('en', 'propose_only'),
    );
  });

  it('keeps the deployment’s order when it builds a lookup', () => {
    const held = postureLabels('en', ['act_silently', 'propose_only']);

    expect(Object.keys(held)).toEqual(['act_silently', 'propose_only']);
  });
});
