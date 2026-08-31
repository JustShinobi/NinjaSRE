import { isTerminalIncident } from '@/design/status';
import type { IncidentOccurrence } from './incident-groups';

/**
 * A subject's own firings, laid out on one 24-hour axis instead of repeated
 * as a list.
 *
 * The window is the 24 hours ending at `now`, matching what the strip's own
 * edge labels say ("start of the window", "now"). An occurrence older than
 * that is not dropped — it is counted, so "more before yesterday" is always
 * true rather than a silent omission the reader has no way to notice.
 *
 * A group of exactly one occurrence needs no strip: there is nothing to plot
 * a recurrence against, and the expansion still shows the cause/link block
 * for it.
 */

const WINDOW_HOURS = 24;

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

/** `occurrences` positioned on the last 24 hours ending at `now`. */
export function positionOnTimeline(
  occurrences: readonly IncidentOccurrence[],
  now: Date,
): Timeline {
  const windowStart = new Date(now.getTime() - WINDOW_HOURS * 60 * 60 * 1000);
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
