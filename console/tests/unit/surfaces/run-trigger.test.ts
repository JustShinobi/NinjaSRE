import { describe, expect, it } from 'vitest';

import { triggerLabel } from '@/surfaces/run-trigger';

describe('run trigger labels', () => {
  it.each([
    ['interactive', 'Manual'],
    ['manual', 'Manual'],
    ['alert', 'Alert'],
    ['schedule', 'Scheduled'],
    ['subagent', 'Specialist'],
  ])('translates the internal %s trigger', (raw, expected) => {
    expect(triggerLabel('en', raw)).toBe(expected);
  });

  it.each([
    ['interactive', 'Manual'],
    ['alert', 'Alerta'],
    ['schedule', 'Agendada'],
    ['subagent', 'Especialista'],
  ])('translates %s for Portuguese readers', (raw, expected) => {
    expect(triggerLabel('pt-BR', raw)).toBe(expected);
  });

  it('does not expose an unknown slug verbatim', () => {
    expect(triggerLabel('en', 'future_source')).toBe('Future source');
  });
});
