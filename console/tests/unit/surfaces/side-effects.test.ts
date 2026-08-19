import { describe, expect, it } from 'vitest';

import { sideEffectLabel } from '@/surfaces/side-effects';

/**
 * What a tool's worst-case side effect means, at the point a reviewer decides
 * whether to approve it.
 *
 * The deployment sends these as slugs, and the proposal card used to
 * interpolate the slug straight into a sentence a person reads. The five
 * levels are ordered least to most dangerous, and the words chosen here
 * preserve that order.
 */

describe('what a side-effect level means', () => {
  it('says what the most dangerous one actually does', () => {
    const said = sideEffectLabel('en', 'destructive');

    expect(said).not.toBe('destructive');
    expect(said.toLowerCase()).toContain('nothing left to roll back');
  });

  it('distinguishes a reversible write from an irreversible one', () => {
    expect(sideEffectLabel('en', 'write_reversible')).not.toBe(
      sideEffectLabel('en', 'write_irreversible'),
    );
  });

  it('distinguishes a plain read from a sensitive one', () => {
    expect(sideEffectLabel('en', 'read')).not.toBe(
      sideEffectLabel('en', 'read_sensitive'),
    );
  });

  it('falls back to the slug for a level this console has no words for', () => {
    // The levels come from the deployment, not from here. A sixth one must
    // still render, as itself, rather than an empty value.
    expect(sideEffectLabel('en', 'time_travel')).toBe('time_travel');
  });

  it('translates rather than carrying English into another locale', () => {
    expect(sideEffectLabel('pt-BR', 'read')).not.toBe(sideEffectLabel('en', 'read'));
  });
});
