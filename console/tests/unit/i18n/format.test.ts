import { describe, expect, it } from 'vitest';

import {
  formatCount,
  formatCurrency,
  formatDateTime,
  formatDuration,
  formatNumber,
  formatRelative,
  humaniseIdentifier,
  timestamp,
} from '@/i18n/format';

/**
 * Formatting, per locale, and the one rule that is not about locale at all.
 *
 * A relative time is easier to read and impossible to act on: "4m ago" cannot
 * be compared against a log line, a ticket, or somebody else's screen. So
 * everything that produces one also produces the absolute instant it was
 * computed from, and `timestamp()` is the only way to get either — there is no
 * path that yields a relative time on its own.
 */

const INSTANT = new Date('2026-08-07T12:00:00Z');

describe('formatting by locale', () => {
  it('writes a number the way the locale writes numbers', () => {
    expect(formatNumber('en', 1234567.5)).toBe('1,234,567.5');
    expect(formatNumber('pt-BR', 1234567.5)).toBe('1.234.567,5');
  });

  it('writes a count against the singular key at one and the plural key otherwise', () => {
    // "1 events" and "1 items need you" are what this exists to prevent: a
    // count of one reads through the singular key, anything else through the
    // plural one, in whichever locale is asking.
    expect(formatCount('en', 1, 'transcript.events.one', 'transcript.events')).toBe(
      '1 event',
    );
    expect(formatCount('en', 2, 'transcript.events.one', 'transcript.events')).toBe(
      '2 events',
    );
    expect(formatCount('pt-BR', 1, 'transcript.events.one', 'transcript.events')).toBe(
      '1 evento',
    );
    expect(formatCount('pt-BR', 2, 'transcript.events.one', 'transcript.events')).toBe(
      '2 eventos',
    );
  });

  it('writes the attention count in the number the sentence agrees with', () => {
    expect(
      formatCount(
        'en',
        1,
        'dashboard.attention.count.one',
        'dashboard.attention.count',
      ),
    ).toBe('1 item needs you');
    expect(
      formatCount(
        'en',
        2,
        'dashboard.attention.count.one',
        'dashboard.attention.count',
      ),
    ).toBe('2 items need you');
  });

  it('writes the count itself the way the locale writes numbers', () => {
    expect(formatCount('en', 1234, 'transcript.events.one', 'transcript.events')).toBe(
      '1,234 events',
    );
  });

  it('writes money with the currency the deployment is billed in', () => {
    expect(formatCurrency('en', 1234.5, 'USD')).toContain('1,234.50');
    expect(formatCurrency('pt-BR', 1234.5, 'BRL')).toContain('1.234,50');
  });

  it('writes a date the way the locale orders one', () => {
    const english = formatDateTime('en', INSTANT, 'UTC');
    const portuguese = formatDateTime('pt-BR', INSTANT, 'UTC');

    expect(english).not.toBe(portuguese);
    expect(english).toContain('2026');
    expect(portuguese).toContain('2026');
  });

  it('writes a duration in units, not in seconds nobody converts in their head', () => {
    expect(formatDuration('en', 228)).toBe('3m 48s');
    expect(formatDuration('en', 41)).toBe('41s');
    expect(formatDuration('en', 8100)).toBe('2h 15m');
    expect(formatDuration('en', 0)).toBe('0s');
  });

  it('rounds a duration towards the unit rather than showing four of them', () => {
    // Three units is a measurement; two is a sentence somebody reads at a
    // glance, which is what this is for.
    expect(formatDuration('en', 90061).split(' ').length).toBeLessThanOrEqual(2);
  });

  it('refuses a negative duration rather than printing a backwards one', () => {
    expect(() => formatDuration('en', -1)).toThrow('duration');
  });

  it('says how long ago, in the locale', () => {
    const fourMinutesBefore = new Date(INSTANT.getTime() - 4 * 60 * 1000);

    expect(formatRelative('en', fourMinutesBefore, INSTANT)).toContain('4');
    expect(formatRelative('pt-BR', fourMinutesBefore, INSTANT)).toContain('4');
    expect(formatRelative('en', fourMinutesBefore, INSTANT)).not.toBe(
      formatRelative('pt-BR', fourMinutesBefore, INSTANT),
    );
  });
});

describe('a relative time never travels alone', () => {
  it('carries the absolute instant beside it', () => {
    const stamped = timestamp('en', INSTANT, INSTANT, 'UTC');

    expect(stamped.relative).not.toBe('');
    expect(stamped.absolute).toContain('2026');
    expect(stamped.iso).toBe('2026-08-07T12:00:00.000Z');
  });

  it('takes a string as readily as a date, because that is what an API sends', () => {
    const stamped = timestamp('en', '2026-08-07T11:56:00Z', INSTANT, 'UTC');

    expect(stamped.iso).toBe('2026-08-07T11:56:00.000Z');
    expect(stamped.relative).toContain('4');
  });

  it('says so rather than throwing when the instant is not one', () => {
    const stamped = timestamp('en', 'not a date', INSTANT, 'UTC');

    // A malformed timestamp is a data problem, and a screen that throws on one
    // takes down a page over a field nobody was reading.
    expect(stamped.iso).toBe('');
    expect(stamped.absolute).toBe('');
    expect(stamped.relative).toBe('');
  });
});

/**
 * An internal identifier, made readable without being made unfindable.
 *
 * The agent's topology set `resolve_integrations`, `plan_evidence` and
 * `gather_evidence` at twenty-two pixels as though they were headings, on a
 * screen whose dashboard two clicks away writes every label in words. Same
 * product, two vocabularies, and the reader is left to work out that the one
 * shouting at them is a variable name.
 *
 * The identifier is not thrown away — it is what a log line and a config key
 * are spelled as, and a screen that hid it would make the two impossible to
 * connect. It moves to where an identifier belongs: beside the name, in the
 * monospaced face, at the size of a reference rather than of a title.
 */
describe('humanising an identifier', () => {
  it('turns a snake_case name into a sentence', () => {
    expect(humaniseIdentifier('resolve_integrations')).toBe('Resolve integrations');
    expect(humaniseIdentifier('gather_evidence')).toBe('Gather evidence');
    expect(humaniseIdentifier('intake')).toBe('Intake');
  });

  it('handles the dotted and hyphenated spellings the same way', () => {
    expect(humaniseIdentifier('agents.max_iterations')).toBe('Agents max iterations');
    expect(humaniseIdentifier('change-historian')).toBe('Change historian');
  });

  it('leaves something that is already a sentence alone', () => {
    expect(humaniseIdentifier('Resolve integrations')).toBe('Resolve integrations');
  });

  it('gives back nothing for nothing rather than inventing a word', () => {
    expect(humaniseIdentifier('')).toBe('');
    expect(humaniseIdentifier('   ')).toBe('');
  });
});
