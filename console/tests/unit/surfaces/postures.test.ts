import { describe, expect, it } from 'vitest';

import {
  postureLabel,
  postureLabels,
  postureName,
  postureNames,
} from '@/surfaces/postures';

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

describe('what a posture is called, in short', () => {
  it('is shorter than the sentence, and is not the raw slug', () => {
    const named = postureName('en', 'act_and_report');

    expect(named).not.toBe('act_and_report');
    expect(named).not.toBe(postureLabel('en', 'act_and_report'));
    // The short name is the descriptive sentence's own headline — the
    // words a reader who already saw the subtitle recognises on opening
    // the level selector, not a second vocabulary for the same thing.
    expect(postureLabel('en', 'act_and_report')).toContain(named);
  });

  it('falls back to the slug for a level this console has no words for', () => {
    // The levels come from the deployment, not from here — the same
    // guarantee `postureLabel` gives, and just as easy to lose while
    // adding a second lookup beside it.
    expect(postureName('en', 'act_on_tuesdays')).toBe('act_on_tuesdays');
  });

  it('translates rather than carrying English into another locale', () => {
    expect(postureName('pt-BR', 'propose_only')).not.toBe(
      postureName('en', 'propose_only'),
    );
  });
});

describe('what a set of postures is called, in short, as a lookup', () => {
  it('builds the same lookup postureLabels does, from the short name', () => {
    const named = postureNames('en', ['act_silently', 'propose_only']);

    expect(Object.keys(named)).toEqual(['act_silently', 'propose_only']);
    expect(named.act_silently).toBe(postureName('en', 'act_silently'));
    expect(named.propose_only).toBe(postureName('en', 'propose_only'));
  });

  it('falls back to the slug for a level this console has no words for', () => {
    const named = postureNames('en', ['act_on_tuesdays']);

    expect(named.act_on_tuesdays).toBe('act_on_tuesdays');
  });
});
