import { describe, expect, it } from 'vitest';

import {
  cronFromPreset,
  frequencyOfCron,
  SCHEDULE_FREQUENCIES,
  WEEKDAYS,
} from '@/surfaces/schedules';

/**
 * The frequency preset generator: a readable choice in, the five-field cron
 * expression it stands for out — the one part of the frequency form with no
 * server counterpart, because the deployment's own preview already answers what a
 * cron expression *fires on*. This only answers what a sentence like "every
 * Monday at 08:00" *is*, in the syntax the field already accepts.
 */

describe('the frequency preset generator', () => {
  it('turns "every Monday at 08:00" into the exact cron the spec names', () => {
    expect(cronFromPreset('weekly', 'monday', '08:00')).toBe('0 8 * * 1');
  });

  it('turns daily into every day at the chosen time', () => {
    expect(cronFromPreset('daily', 'monday', '06:30')).toBe('30 6 * * *');
  });

  it('turns weekdays into Monday through Friday only', () => {
    expect(cronFromPreset('weekdays', 'monday', '09:00')).toBe('0 9 * * 1-5');
  });

  it('turns monthly into the first of the month', () => {
    expect(cronFromPreset('monthly', 'monday', '00:00')).toBe('0 0 1 * *');
  });

  it('reads every weekday name against the ordinary crontab numbering, Sunday first', () => {
    expect(cronFromPreset('weekly', 'sunday', '08:00')).toBe('0 8 * * 0');
    expect(cronFromPreset('weekly', 'saturday', '08:00')).toBe('0 8 * * 6');
  });

  it('generates nothing for "custom" — the one preset that leaves the field alone', () => {
    expect(cronFromPreset('custom', 'monday', '08:00')).toBeNull();
  });

  it('generates nothing for a time it cannot parse', () => {
    expect(cronFromPreset('daily', 'monday', '')).toBeNull();
    expect(cronFromPreset('daily', 'monday', 'not-a-time')).toBeNull();
  });

  it('declares every frequency and every weekday exactly once', () => {
    expect(SCHEDULE_FREQUENCIES).toEqual([
      'custom',
      'daily',
      'weekdays',
      'weekly',
      'monthly',
    ]);
    expect(WEEKDAYS).toEqual([
      'monday',
      'tuesday',
      'wednesday',
      'thursday',
      'friday',
      'saturday',
      'sunday',
    ]);
  });
});

/**
 * Reading a stored cron expression back as the sentence it stands for.
 *
 * The list is where an operator checks what is scheduled, and `30 6 * * 1-5`
 * is not an answer to "when does this run" for most of the people entitled to
 * ask. This is the generator run backwards, and deliberately partial: it
 * recognises the shapes the presets can produce and refuses everything else,
 * because a wrong sentence about when an investigation runs is worse than the
 * raw expression the operator can at least look up.
 */
describe('reading a cron expression back as a frequency', () => {
  it('recognises every shape the presets generate, round-tripping each one', () => {
    expect(frequencyOfCron('0 8 * * 1')).toEqual({
      frequency: 'weekly',
      weekday: 'monday',
      time: '08:00',
    });
    expect(frequencyOfCron('30 6 * * *')).toEqual({
      frequency: 'daily',
      weekday: null,
      time: '06:30',
    });
    expect(frequencyOfCron('0 9 * * 1-5')).toEqual({
      frequency: 'weekdays',
      weekday: null,
      time: '09:00',
    });
    expect(frequencyOfCron('0 0 1 * *')).toEqual({
      frequency: 'monthly',
      weekday: null,
      time: '00:00',
    });
  });

  it('pads the clock, so a list of times reads as a column rather than as noise', () => {
    expect(frequencyOfCron('5 7 * * *')?.time).toBe('07:05');
  });

  it('reads every weekday back to the name it was generated from', () => {
    for (const weekday of WEEKDAYS) {
      const cron = cronFromPreset('weekly', weekday, '08:00');
      expect(cron).not.toBeNull();
      expect(frequencyOfCron(cron ?? '')).toEqual({
        frequency: 'weekly',
        weekday,
        time: '08:00',
      });
    }
  });

  it('refuses an expression no preset could have written, rather than guessing at it', () => {
    // Every-fifteen-minutes, a range of hours, a step, a named month: all
    // legal cron, none of them a sentence this function is entitled to invent.
    expect(frequencyOfCron('*/15 * * * *')).toBeNull();
    expect(frequencyOfCron('0 9-17 * * *')).toBeNull();
    expect(frequencyOfCron('0 8 * * 1,3')).toBeNull();
    expect(frequencyOfCron('0 8 15 * *')).toBeNull();
  });

  it('refuses what is not a five-field expression at all', () => {
    expect(frequencyOfCron('')).toBeNull();
    expect(frequencyOfCron('0 8 * *')).toBeNull();
    expect(frequencyOfCron('not a cron')).toBeNull();
  });
});
