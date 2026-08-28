'use client';

import type { ReactNode } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { Button } from '@/components/action';
import { formatCount } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { publishResolved } from '@/shell/attention';
import { eventTimes, narrations, transcriptLabels } from '@/surfaces/labels';
import { Transcript } from '@/surfaces/transcript-view';
import { ConnectionBadge, StaleNotice } from './connection-state';
import type { LiveEvent, RunPhase, Seed } from './reducer';
import { useReopen, useRun } from './use-run';
import type { RunStore } from './store';

/**
 * A run watched as it happens, through the component a replayed run uses.
 *
 * The transcript below is `Transcript` — the same one, not a live variant of
 * it. That is the property the previous wave established and this one had to
 * preserve: a run being watched and the same run read back tomorrow are the
 * same account of the same events, or the recorded one is not evidence. What
 * this component adds is around the outside of it — whether the events are
 * arriving, and what to do when they stop.
 *
 * **New events do not move the viewport.** An operator who has scrolled up is
 * reading something; a transcript that yanked them to the bottom every time the
 * agent thought would be one they scroll up in and immediately lose their place
 * in. So the view follows only while it is already at the bottom, and otherwise
 * says how many arrived and waits to be asked.
 */

/** How close to the bottom still counts as being at it, in pixels. */
const ANCHOR_SLACK = 32;

const ENDED_MESSAGE = {
  completed: 'live.ended.completed',
  failed: 'live.ended.failed',
  cancelled: 'live.ended.cancelled',
} as const;

/**
 * How much of a live run there is, counted off the run itself.
 *
 * This exists because the transcript's header and the transcript's body are
 * siblings — the header is the card's `action` slot and the body is its
 * children — so there is no prop either can hand the other. Left to their own
 * devices they each found a source, and they found different ones: the header
 * counted the replay the server had already read, the body drew the stream,
 * and a live run's card said "6 events" over "This investigation recorded no
 * events."
 *
 * Both read the store instead, which is the thing that exists so that two
 * consumers of one run cannot disagree about what has arrived. Subscribing
 * twice costs nothing: the store is reference-counted per run, so the count and
 * the transcript below it share one connection and one sequence of events.
 */
export interface LiveEventCountProps {
  readonly runId: string;
  readonly locale: Locale;
  /**
   * What the server already rendered — the same seed the transcript is given.
   *
   * Handed to both halves from one place, because the store keys its first
   * state on whichever subscriber arrives first: two seeds would be two
   * answers to "what was already on the screen", and the card would be back to
   * stating two numbers by a subtler route.
   */
  readonly seed: Seed;
  /** Injected so the suite can drive a stream without a network. */
  readonly store?: RunStore;
}

/** The live run's event count, from the sequence the transcript is drawing. */
export function LiveEventCount({
  runId,
  locale,
  seed,
  store,
}: LiveEventCountProps): ReactNode {
  const snapshot = useRun(runId, seed, store);
  return (
    <span data-testid="transcript-count" className="text-meta text-muted">
      {formatCount(
        locale,
        snapshot.live.events.length,
        'transcript.events.one',
        'transcript.events',
      )}
      {snapshot.live.events.length === 0
        ? ''
        : ` · ${message(locale, 'transcript.newestFirst')}`}
    </span>
  );
}

export interface LiveRunProps {
  readonly runId: string;
  readonly locale: Locale;
  /** What the server already rendered: the replay, and where it got to. */
  readonly seed: Seed;
  /** The instant relative times are read against, as the server resolved it. */
  readonly now: string;
  readonly zone: string;
  /** Injected so the suite can drive a stream without a network. */
  readonly store?: RunStore;
}

export function LiveRun({
  runId,
  locale,
  seed,
  now,
  zone,
  store,
}: LiveRunProps): ReactNode {
  const snapshot = useRun(runId, seed, store);
  const reopen = useReopen(runId, store);
  const viewport = useRef<HTMLDivElement>(null);
  const [following, setFollowing] = useState(true);
  /**
   * How many events were on screen when the operator stopped following.
   *
   * Held rather than derived, and set only in the handler that observes the
   * scroll, so the arrival of an event never itself changes any state but the
   * transcript's. That is what keeps the count honest: it is the difference
   * from the moment they looked away, not from the last render.
   */
  const [anchor, setAnchor] = useState(0);

  const total = snapshot.live.events.length;
  const behind = following ? 0 : Math.max(0, total - anchor);

  const toNewest = useCallback(() => {
    const element = viewport.current;
    if (element !== null) element.scrollTop = element.scrollHeight;
    setFollowing(true);
  }, []);

  // The viewport follows only while it is already at the bottom. Nothing here
  // sets state: an operator reading something halfway up is not moved, and an
  // operator at the bottom stays there.
  useEffect(() => {
    if (!following) return;
    const element = viewport.current;
    if (element !== null) element.scrollTop = element.scrollHeight;
  }, [following, total]);

  // An interaction decided anywhere leaves the notification centre, without a
  // refresh and without this component knowing that a centre exists.
  useEffect(() => {
    for (const decision of snapshot.live.decided) publishResolved(decision.id);
  }, [snapshot.live.decided]);

  const events: readonly LiveEvent[] = snapshot.live.events;
  const phase: RunPhase = snapshot.live.phase;

  return (
    <div data-testid="live-run" data-phase={phase} className="flex flex-col gap-3">
      <div className="flex items-center gap-3 flex-wrap">
        <ConnectionBadge
          locale={locale}
          state={snapshot.connection}
          exhausted={snapshot.exhausted}
          onReload={reopen}
        />
        {phase === 'running' ? null : (
          <span data-testid="run-ended" className="text-meta text-muted">
            {message(locale, ENDED_MESSAGE[phase])}
          </span>
        )}
        {behind === 0 ? null : (
          <Button variant="quiet" data-testid="new-events" onClick={toNewest}>
            {message(locale, 'live.new', { count: behind })}
          </Button>
        )}
      </div>

      <StaleNotice locale={locale} shown={snapshot.exhausted} />

      <div
        ref={viewport}
        data-testid="transcript-viewport"
        data-following={following ? 'true' : 'false'}
        className="max-h-prose overflow-y-auto"
        onScroll={(event) => {
          const element = event.currentTarget;
          const atBottom =
            element.scrollHeight - element.scrollTop - element.clientHeight <=
            ANCHOR_SLACK;
          setFollowing(atBottom);
          if (!atBottom) setAnchor(total);
        }}
      >
        <Transcript
          events={events}
          labels={transcriptLabels(locale, events)}
          times={eventTimes(locale, events, new Date(now), zone)}
          narrations={narrations(locale, events)}
        />
      </div>
    </div>
  );
}
