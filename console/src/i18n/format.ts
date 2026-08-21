/**
 * Dates, durations, numbers and money, by locale — and the rule about relative
 * time that is not about locale at all.
 *
 * A relative time is the easiest thing on a screen to read and the hardest to
 * act on. "4m ago" cannot be compared against a log line, pasted into a ticket,
 * or matched with what somebody else is looking at, and the moment it matters is
 * the moment two people are on a call trying to line up two clocks. So the only
 * way to get a relative time here is `timestamp()`, which returns the absolute
 * instant beside it and the machine-readable form beside that.
 *
 * The arithmetic is `Intl`, which every browser this console supports ships. A
 * formatting library would be a dependency an operator has to audit for a job
 * the platform already does correctly, in every locale, including the ones
 * nobody here can review.
 */

import type { Locale } from './messages';

const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE;
const SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR;

/** `value`, grouped and pointed the way `locale` writes a number. */
export function formatNumber(locale: Locale, value: number): string {
  return new Intl.NumberFormat(locale).format(value);
}

/** `value` as money in `currency`, the way `locale` writes money. */
export function formatCurrency(
  locale: Locale,
  value: number,
  currency: string,
): string {
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(value);
}

/**
 * An absolute instant, to the second, in `zone`.
 *
 * The zone is a parameter rather than the browser's, because an operator
 * comparing a console against a log reads both in the deployment's zone and a
 * console that silently used theirs would be off by an hour twice a year.
 */
export function formatDateTime(locale: Locale, instant: Date, zone: string): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'medium',
    timeZone: zone,
  }).format(instant);
}

/**
 * A duration in seconds, as at most two units.
 *
 * Two, because three is a measurement and two is a sentence. `3m 48s` is read
 * at a glance; `1h 2m 3s 400ms` is read by counting.
 */
export function formatDuration(locale: Locale, seconds: number): string {
  if (seconds < 0 || !Number.isFinite(seconds)) {
    throw new Error(`a duration cannot be ${String(seconds)} seconds`);
  }
  const whole = Math.floor(seconds);
  const parts: string[] = [];
  const days = Math.floor(whole / SECONDS_PER_DAY);
  const hours = Math.floor((whole % SECONDS_PER_DAY) / SECONDS_PER_HOUR);
  const minutes = Math.floor((whole % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
  const remainder = whole % SECONDS_PER_MINUTE;

  if (days > 0) parts.push(`${formatNumber(locale, days)}d`);
  if (hours > 0) parts.push(`${formatNumber(locale, hours)}h`);
  if (minutes > 0 && days === 0) parts.push(`${formatNumber(locale, minutes)}m`);
  if (remainder > 0 && days === 0 && hours === 0) {
    parts.push(`${formatNumber(locale, remainder)}s`);
  }
  return parts.length === 0 ? `${formatNumber(locale, 0)}s` : parts.join(' ');
}

/** The largest unit that describes the gap, and how many of it. */
function largestUnit(seconds: number): [number, Intl.RelativeTimeFormatUnit] {
  const magnitude = Math.abs(seconds);
  if (magnitude < SECONDS_PER_MINUTE) return [Math.round(seconds), 'second'];
  if (magnitude < SECONDS_PER_HOUR) {
    return [Math.round(seconds / SECONDS_PER_MINUTE), 'minute'];
  }
  if (magnitude < SECONDS_PER_DAY)
    return [Math.round(seconds / SECONDS_PER_HOUR), 'hour'];
  return [Math.round(seconds / SECONDS_PER_DAY), 'day'];
}

/** How long before `now` the `instant` was, phrased the way `locale` phrases it. */
export function formatRelative(locale: Locale, instant: Date, now: Date): string {
  const seconds = (instant.getTime() - now.getTime()) / 1000;
  const [amount, unit] = largestUnit(seconds);
  return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(amount, unit);
}

/** One instant, in the three forms a screen needs at once. */
export interface Timestamp {
  /** How long ago, for reading. */
  readonly relative: string;
  /** The instant itself, for comparing against something outside the console. */
  readonly absolute: string;
  /** The machine-readable form, for a `datetime` attribute and for copying. */
  readonly iso: string;
}

/**
 * An instant, relative and absolute together.
 *
 * There is no function here that returns only the relative form, and that is
 * the design: a component cannot show a relative time without having the
 * absolute one in its hand.
 *
 * An unparseable instant comes back empty rather than throwing. A malformed
 * timestamp is a data problem, and a screen that throws on one takes the whole
 * page down over a field nobody was reading.
 */
export function timestamp(
  locale: Locale,
  instant: Date | string,
  now: Date,
  zone: string,
): Timestamp {
  const parsed = instant instanceof Date ? instant : new Date(instant);
  if (Number.isNaN(parsed.getTime())) {
    return { relative: '', absolute: '', iso: '' };
  }
  return {
    relative: formatRelative(locale, parsed, now),
    absolute: formatDateTime(locale, parsed, zone),
    iso: parsed.toISOString(),
  };
}
