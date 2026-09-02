import { isTerminalIncident } from '@/design/status';
import type { IncidentOccurrence } from './incident-groups';

/**
 * A subject's own firings, laid out on one axis instead of repeated as a
 * list.
 *
 * The window ends at `now` and defaults to 24 hours — the Incidents screen's
 * own strip, matching what its edge labels say ("start of the window",
 * "now"). The Painel's "what insists" strip asks for 48 hours instead, over
 * the same function: one positioning rule, two callers, rather than a second
 * copy that could disagree with the first about where a marker lands. An
 * occurrence older than the window is not dropped — it is counted, so "more
 * before yesterday" is always true rather than a silent omission the reader
 * has no way to notice.
 *
 * A group of exactly one occurrence needs no strip: there is nothing to plot
 * a recurrence against, and the expansion still shows the cause/link block
 * for it.
 */

/** The Incidents screen's own window, unless a caller asks for another. */
export const DEFAULT_TIMELINE_WINDOW_HOURS = 24;

export type TimelineShape = 'circle' | 'diamond';

export interface TimelinePoint {
  readonly id: string;
  /** Position along the axis, 0 at the window's start and 100 at `now`. */
  readonly percent: number;
  readonly shape: TimelineShape;
  readonly at: string;
  readonly state: string;
}

export interface Timeline {
  readonly points: readonly TimelinePoint[];
  /** Occurrences older than the window, counted rather than plotted. */
  readonly overflowCount: number;
  readonly windowStart: string;
}

/** `occurrences` positioned on the last `windowHours` ending at `now`. */
export function positionOnTimeline(
  occurrences: readonly IncidentOccurrence[],
  now: Date,
  windowHours: number = DEFAULT_TIMELINE_WINDOW_HOURS,
): Timeline {
  const windowStart = new Date(now.getTime() - windowHours * 60 * 60 * 1000);
  if (occurrences.length <= 1) {
    return { points: [], overflowCount: 0, windowStart: windowStart.toISOString() };
  }

  const span = now.getTime() - windowStart.getTime();
  const points: TimelinePoint[] = [];
  let overflowCount = 0;

  for (const occurrence of occurrences) {
    const instant = Date.parse(occurrence.at);
    if (Number.isNaN(instant) || instant < windowStart.getTime()) {
      overflowCount += 1;
      continue;
    }
    const clamped = Math.min(instant, now.getTime());
    const percent = span === 0 ? 100 : ((clamped - windowStart.getTime()) / span) * 100;
    points.push({
      id: occurrence.id,
      percent,
      shape: isTerminalIncident(occurrence.state) ? 'circle' : 'diamond',
      at: occurrence.at,
      state: occurrence.state,
    });
  }

  return { points, overflowCount, windowStart: windowStart.toISOString() };
}
