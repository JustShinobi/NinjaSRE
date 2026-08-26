'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Badge } from '@/components/status';
import { cx } from '@/design/cx';
import {
  ActivityIcon,
  ArrowRightIcon,
  BellIcon,
  BrainIcon,
  CheckIcon,
  ChevronLeftIcon,
  ClipboardIcon,
  CompassIcon,
  DatabaseIcon,
  ListIcon,
  ShieldIcon,
  type IconProps,
} from '@/design/icons';
import { BoundedPayload, type PayloadLabels } from './payload';
import { renderReport } from './report';
import { KIND_ROLE, type TranscriptEvent, type TranscriptKind } from './transcript';

/**
 * The one component in this console that renders transcript events.
 *
 * "One" is asserted structurally rather than intended, because a live view and a
 * history view are the two files this feature is most likely to grow by
 * accident, and by the time they have diverged the recorded account of a run is
 * no longer the account somebody watched. This component takes a sequence; where
 * the sequence came from is the caller's problem.
 *
 * **The cost of drawing it does not grow with the length of it.** A run with ten
 * thousand events draws the same number of entries as a run with a hundred, and
 * the rest are one control away. The alternative — ten thousand entries in the
 * document, most of them holding a payload — is a page that takes four seconds
 * to become interactive on the machine somebody actually has.
 */

/** How many entries are in the document at once, however long the transcript is. */
export const TRANSCRIPT_WINDOW = 100;

const KIND_ICON: Readonly<Record<TranscriptKind, (props: IconProps) => ReactNode>> = {
  objective: CompassIcon,
  reasoning: BrainIcon,
  call: ActivityIcon,
  result: ListIcon,
  evidence: ClipboardIcon,
  recall: DatabaseIcon,
  dispatch: ArrowRightIcon,
  return: ChevronLeftIcon,
  guardrail: ShieldIcon,
  interaction: BellIcon,
  report: CheckIcon,
};

/** The well each kind's shape sits in. Colour is the second carrier, never the first. */
const ROLE_WELL: Readonly<Record<string, string>> = {
  info: 'bg-info-bg text-info border-info',
  neutral: 'bg-neutral-bg text-neutral border-border-strong',
  danger: 'bg-danger-bg text-danger border-danger',
  warning: 'bg-warning-bg text-warning border-warning',
  success: 'bg-success-bg text-success border-success',
};

/**
 * The kinds whose `detail` can be a whole document rather than a short aside.
 *
 * `reasoning` is what the model said on the turn — and on the turn where it
 * stops calling capabilities, that is its final answer, written in the same
 * markdown the report document is. `report` is the transcript's own
 * (ordinarily unreached — see `eventsFromReplay`) copy of that same document.
 * Every other kind's detail is a short, deployment-written aside — an error
 * message, a guardrail's reason, a question's text — never a model's prose,
 * so it keeps rendering as the plain text it is.
 *
 * An event's `note` is never in this set and never can be: it is the
 * deployment's own generated prose, and running a capability name like
 * `proxmox_backup_failures` through a markdown renderer emphasises `_backup_`
 * and prints the name without its underscores.
 */
const DOCUMENT_KINDS: ReadonlySet<TranscriptKind> = new Set(['reasoning', 'report']);

/**
 * One event's instant and its duration, formatted on the server.
 *
 * On the server because the absolute form is rendered in the *deployment's*
 * zone: an operator comparing the console against a log reads both in that zone,
 * and a browser quietly using its own would be an hour out twice a year.
 */
export interface EventTime {
  readonly relative: string;
  readonly absolute: string;
  readonly iso: string;
  /** How long the call took, already phrased. Empty when the event is not one. */
  readonly duration: string;
}

export interface TranscriptLabels {
  /** The name of each kind, in the viewer's language, keyed by kind. */
  readonly kinds: Readonly<Record<TranscriptKind, string>>;
  /** "Showing 1–100 of 10,000 events." Interpolated by the caller. */
  readonly position: string;
  readonly earlier: string;
  readonly later: string;
  readonly empty: string;
  readonly arguments: string;
  readonly result: string;
  /** What the fold over a deployment-written note is called. */
  readonly note: string;
  readonly payload: PayloadLabels;
}

export interface TranscriptProps {
  readonly events: readonly TranscriptEvent[];
  readonly labels: TranscriptLabels;
  /** Each event's instant, already formatted, keyed by event id. */
  readonly times: Readonly<Record<string, EventTime>>;
}

function Entry({
  event,
  labels,
  time,
}: {
  readonly event: TranscriptEvent;
  readonly labels: TranscriptLabels;
  readonly time: EventTime | undefined;
}): ReactNode {
  const role = KIND_ROLE[event.kind];
  const Icon = KIND_ICON[event.kind];
  const guardrail = event.kind === 'guardrail';

  return (
    <li
      data-testid="transcript-event"
      data-kind={event.kind}
      data-raw-kind={event.rawKind}
      data-role={role}
      className="flex gap-3 min-w-0"
    >
      <span
        aria-hidden="true"
        className={cx(
          'flex items-center justify-center size-5 shrink-0 rounded-2 edge',
          ROLE_WELL[role] ?? ROLE_WELL.neutral,
        )}
      >
        <Icon />
      </span>
      <div className="flex flex-col gap-1 min-w-0 pb-4">
        <span className="flex items-center gap-2 flex-wrap text-meta text-muted">
          {/* The kind is a word as well as a shape and a colour. A transcript
              read by somebody who cannot separate this palette's danger from
              its accent still says "guardrail". */}
          <span
            data-testid="event-kind"
            className={cx('text-strong', guardrail ? 'text-danger' : 'text-text')}
          >
            {labels.kinds[event.kind]}
          </span>
          {event.title === '' ? null : <span className="font-mono">{event.title}</span>}
          {event.status === '' ? null : <Badge status={event.status} />}
          {time === undefined || time.duration === '' ? null : (
            <span className="tabular-nums">{time.duration}</span>
          )}
          {time === undefined || time.relative === '' ? null : (
            <time dateTime={time.iso} title={time.absolute}>
              {time.relative}
            </time>
          )}
        </span>
        {event.detail === '' ? null : DOCUMENT_KINDS.has(event.kind) ? (
          renderReport(event.detail)
        ) : (
          <p className={cx('text-small', guardrail ? 'text-danger' : '')}>
            {event.detail}
          </p>
        )}
        {event.note === '' ? null : (
          <details data-testid="event-note" className="text-meta">
            <summary className="text-muted cursor-pointer select-none">
              {labels.note}
            </summary>
            {/* Plain text, in a scroller of its own. This is a ranking table
                sixty capabilities long, it repeats between turns because the
                scoring is deterministic, and it used to be drawn expanded on
                every turn — six thousand pixels of arithmetic around four
                lines of what the investigation actually did. */}
            <pre
              data-testid="event-note-body"
              className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap font-mono text-meta text-muted"
            >
              {event.note}
            </pre>
          </details>
        )}
        {event.payload === '' ? null : (
          <BoundedPayload
            label={event.kind === 'call' ? labels.arguments : labels.result}
            content={event.payload}
            labels={labels.payload}
          />
        )}
      </div>
    </li>
  );
}

/** A run's account of itself, live or replayed, through one component. */
export function Transcript({ events, labels, times }: TranscriptProps): ReactNode {
  const [first, setFirst] = useState(Math.max(0, events.length - TRANSCRIPT_WINDOW));
  const drawn = events.slice(first, first + TRANSCRIPT_WINDOW);

  if (events.length === 0) {
    return (
      <p data-testid="transcript" data-total="0" className="text-muted text-small">
        {labels.empty}
      </p>
    );
  }

  return (
    <div
      data-testid="transcript"
      data-total={events.length}
      className="flex flex-col gap-3"
    >
      {events.length > TRANSCRIPT_WINDOW ? (
        <div className="flex items-center gap-3 flex-wrap">
          <p data-testid="transcript-position" className="text-meta text-muted">
            {labels.position}
          </p>
          <Button
            variant="quiet"
            data-testid="earlier"
            state={first === 0 ? 'disabled' : 'default'}
            onClick={() => {
              setFirst(Math.max(0, first - TRANSCRIPT_WINDOW));
            }}
          >
            {labels.earlier}
          </Button>
          <Button
            variant="quiet"
            data-testid="later"
            state={first + TRANSCRIPT_WINDOW >= events.length ? 'disabled' : 'default'}
            onClick={() => {
              setFirst(
                Math.min(events.length - TRANSCRIPT_WINDOW, first + TRANSCRIPT_WINDOW),
              );
            }}
          >
            {labels.later}
          </Button>
        </div>
      ) : null}
      <ol className="flex flex-col">
        {drawn.map((event) => (
          <Entry key={event.id} event={event} labels={labels} time={times[event.id]} />
        ))}
      </ol>
    </div>
  );
}
