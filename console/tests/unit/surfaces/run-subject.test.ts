import { describe, expect, it } from 'vitest';

import { MAX_RUN_NAME_LENGTH, subjectOf } from '@/surfaces/run-subject';

/**
 * One function, called by every surface that names a run — the header, the
 * tab title, and the runs list column — so the three cannot drift into three
 * different opinions about what the same run is called, the way they did
 * when each one computed its own.
 */

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: 'e19e882a1c9b4d5e8f6a2b3c7d0e1f24',
    trigger: 'alert',
    headline: '',
    summary: '',
    ...overrides,
  };
}

describe('subjectOf', () => {
  it('uses the headline when the record carries one', () => {
    const subject = subjectOf(
      run({ headline: 'Primary database ran out of connections' }),
      'en',
    );
    expect(subject.text).toBe('Primary database ran out of connections');
    expect(subject.truncated).toBe(false);
  });

  it('treats a blank headline as though none were recorded', () => {
    const subject = subjectOf(
      run({ headline: '   ', trigger: 'schedule', run_id: 'abcdef1234567890' }),
      'en',
    );
    expect(subject.text).toBe('Scheduled · abcdef12');
  });

  it('uses only the first non-empty line of the headline', () => {
    const subject = subjectOf(
      run({ headline: '\nThe replica fell behind\nA second sentence for the report' }),
      'en',
    );
    expect(subject.text).toBe('The replica fell behind');
  });

  it('strips markdown syntax out of the headline before showing it', () => {
    const subject = subjectOf(
      run({ headline: 'The **platform** node `pve02` degraded — see #findings' }),
      'en',
    );
    expect(subject.text).not.toMatch(/[#*`]/);
    expect(subject.text).toBe('The platform node pve02 degraded — see findings');
  });

  it('collapses runs of whitespace left behind by stripped syntax', () => {
    const subject = subjectOf(
      run({ headline: 'A   **very**    spaced   sentence' }),
      'en',
    );
    expect(subject.text).toBe('A very spaced sentence');
  });

  it('clips a headline past the display limit, at a word boundary, with an indicator', () => {
    const long = 'A'.repeat(10) + ' ' + 'word '.repeat(30);
    const subject = subjectOf(run({ headline: long }), 'en');
    expect(subject.text.length).toBeLessThanOrEqual(MAX_RUN_NAME_LENGTH);
    expect(subject.truncated).toBe(true);
    expect(subject.text.endsWith('…')).toBe(true);
    expect(subject.text).not.toContain('  ');
  });

  it('carries the untruncated sentence separately, for a tooltip', () => {
    const long = 'word '.repeat(40).trim();
    const subject = subjectOf(run({ headline: long }), 'en');
    expect(subject.full).toBe(long);
    expect(subject.full.length).toBeGreaterThan(subject.text.length);
  });

  it('never truncates a name that already fits', () => {
    const subject = subjectOf(run({ headline: 'Short and clear' }), 'en');
    expect(subject.full).toBe(subject.text);
  });

  it('falls back to trigger and short id when there is no headline and the summary is not a recorded failure', () => {
    const subject = subjectOf(
      run({
        headline: '',
        trigger: 'manual',
        run_id: 'e19e882a1c9b4d5e8f6a2b3c7d0e1f24',
        summary: 'A guest reached the ceiling of its own volume.',
      }),
      'en',
    );
    expect(subject.text).toBe('Manual · e19e882a');
  });

  it('never returns the report document as the run’s name, even a long markdown one', () => {
    const document =
      '### Incident Findings & Root Cause Analysis\n\nThe **primary** node lost quorum.';
    const subject = subjectOf(run({ headline: '', summary: document }), 'en');
    expect(subject.text).not.toContain('Incident Findings');
    expect(subject.text).not.toMatch(/[#*]/);
    expect(subject.text).toBe('Alert · e19e882a');
  });

  it('translates a recognised failure instead of falling back to trigger and id', () => {
    const raw =
      "InvestigatorNotConfigured: No investigation runtime is configured. Set NINJASRE_INVESTIGATOR to 'module:factory'.";
    const subject = subjectOf(run({ headline: '', summary: raw }), 'en');
    expect(subject.text).toBe('Investigations are not switched on yet');
    expect(subject.text).not.toContain('InvestigatorNotConfigured');
  });

  it('names a run with neither a headline nor a summary by trigger and id, never leaving the name blank', () => {
    const subject = subjectOf(
      run({ headline: '', summary: '', trigger: 'subagent', run_id: '12345678abcd' }),
      'en',
    );
    expect(subject.text).toBe('Specialist · 12345678');
    expect(subject.text.trim()).not.toBe('');
  });
});
