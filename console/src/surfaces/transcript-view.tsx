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
 * The raw kinds that are genuinely documents, as opposed to the ones that
 * merely *default* to a document-shaped semantic kind.
 *
 * `turn` is `eventsFromReplay`'s own rawKind for a turn's reasoning; the
 * other three are what the stream vocabulary itself spells
 * (`STREAM_KINDS`, `transcript.ts`). Nothing outside this set is a document,
 * however `kindOf` happened to classify it — the distinction the narration
 * table needs and `TranscriptKind` alone cannot make.
 */
const DOCUMENT_RAW_KINDS: ReadonlySet<string> = new Set([
  'turn',
  'model_reasoned',
  'run_completed',
  'run_failed',
]);

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
  /** The Narrado/Bruto toggle's own two words, and what the disclosure is called. */
  readonly view: TranscriptViewLabels;
}

export interface TranscriptViewLabels {
  readonly narrated: string;
  readonly raw: string;
  /** What the closed-by-default disclosure over a payload is called. */
  readonly payload: string;
}

export interface TranscriptProps {
  readonly events: readonly TranscriptEvent[];
  readonly labels: TranscriptLabels;
  /** Each event's instant, already formatted, keyed by event id. */
  readonly times: Readonly<Record<string, EventTime>>;
  /** Each event's narrated sentence, already composed, keyed by event id. */
  readonly narrations: Readonly<Record<string, string>>;
}

/** Which of the two views the transcript is drawn in — screen state, not data. */
type TranscriptView = 'narrated' | 'raw';

function Entry({
  event,
  labels,
  time,
  narration,
  view,
}: {
  readonly event: TranscriptEvent;
  readonly labels: TranscriptLabels;
  readonly time: EventTime | undefined;
  readonly narration: string;
  readonly view: TranscriptView;
}): ReactNode {
  const role = KIND_ROLE[event.kind];
  const Icon = KIND_ICON[event.kind];
  const guardrail = event.kind === 'guardrail';
  // The reasoning and report kinds already render as the document they are —
  // the model's own prose, or the run's own headline document — and folding a
  // lead sentence into that markdown would print it as part of the document
  // rather than beside it. Every other kind's `detail` is a short aside, and
  // that is what the narrated sentence below replaces.
  //
  // Keyed by `rawKind`, not by `event.kind`: `kindOf` defaults every kind it
  // does not recognise to `reasoning` (`transcript.ts`), which is the right
  // default for *icon and colour* — an event the vocabulary has never heard
  // of drawn as an aside rather than dropped — and the wrong one for *this*
  // check. A kind this build has never met is not a document; it is the
  // narration table's own floor, the generic sentence that names it, and
  // `DOCUMENT_KINDS.has(event.kind)` alone would have swallowed it into
  // `renderReport('')` and shown nothing at all.
  const document = DOCUMENT_KINDS.has(event.kind) && DOCUMENT_RAW_KINDS.has(event.rawKind);

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
        {/* The narrated sentence is the primary content of every event but a
            document one — never a JSON block, never the raw kind standing in
            for a sentence nobody wrote. `data-testid="event-narration"` is
            what the acceptance suite reads to prove it is there, on every
            event, in both views: the toggle switches which of this and the
            payload disclosure below opens by default, never which of them
            exists. */}
        {document ? (
          event.detail === '' ? null : renderReport(event.detail)
        ) : (
          <p
            data-testid="event-narration"
            className={cx('text-small', guardrail ? 'text-danger' : '')}
          >
            {narration}
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
              className="mt-1 max-h-scroll-entry overflow-auto whitespace-pre-wrap font-mono text-meta text-muted"
            >
              {event.note}
            </pre>
          </details>
        )}
        {event.payload === '' ? null : (
          // Closed by default in Narrado, open by default in Bruto — the
          // whole difference the toggle makes. `open` is driven by the
          // screen's view rather than left to a first interaction, so
          // switching to Bruto shows every payload at once rather than one
          // click at a time.
          <details
            data-testid="event-payload-disclosure"
            open={view === 'raw' ? true : undefined}
          >
            <summary className="text-meta text-muted cursor-pointer select-none">
              {event.title === '' ? labels.view.payload : `${labels.view.payload} — ${event.title}`}
            </summary>
            <div className="mt-1">
              <BoundedPayload
                label={event.kind === 'call' ? labels.arguments : labels.result}
                content={event.payload}
                labels={labels.payload}
              />
            </div>
          </details>
        )}
      </div>
    </li>
  );
}

/** A run's account of itself, live or replayed, through one component. */
export function Transcript({
  events,
  labels,
  times,
  narrations,
}: TranscriptProps): ReactNode {
  const [first, setFirst] = useState(Math.max(0, events.length - TRANSCRIPT_WINDOW));
  // Screen state, not data: switching views never re-fetches or re-derives
  // the event list, so it can neither lose nor duplicate an event. Narrado
  // is the default — the whole point of this feature is that a payload block
  // is not the first thing an operator reads.
  const [view, setView] = useState<TranscriptView>('narrated');
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
      <div className="flex items-center gap-3 flex-wrap">
        {events.length > TRANSCRIPT_WINDOW ? (
          <p data-testid="transcript-position" className="text-meta text-muted">
            {labels.position}
          </p>
        ) : null}
        {events.length > TRANSCRIPT_WINDOW ? (
          <>
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
          </>
        ) : null}
        {/* Narrado/Bruto — a screen-level choice, applied to every entry drawn
            below rather than asked of each one. `data-view` is what the
            acceptance suite reads to know which view is current. Two
            independent chips, not one shared segmented pill — the artboard
            draws each with its own outline (bordered when it is the current
            view, transparent when it is not) rather than housing both in a
            single enclosing well. */}
        <span
          data-testid="transcript-view-toggle"
          data-view={view}
          className="ml-auto flex items-center gap-2"
        >
          <Button
            variant={view === 'narrated' ? 'secondary' : 'quiet'}
            data-testid="transcript-view-narrated"
            aria-pressed={view === 'narrated'}
            onClick={() => {
              setView('narrated');
            }}
          >
            {labels.view.narrated}
          </Button>
          <Button
            variant={view === 'raw' ? 'secondary' : 'quiet'}
            data-testid="transcript-view-raw"
            aria-pressed={view === 'raw'}
            onClick={() => {
              setView('raw');
            }}
          >
            {labels.view.raw}
          </Button>
        </span>
      </div>
      <ol className="flex flex-col">
        {drawn.map((event) => (
          <Entry
            key={event.id}
            event={event}
            labels={labels}
            time={times[event.id]}
            narration={narrations[event.id] ?? ''}
            view={view}
          />
        ))}
      </ol>
    </div>
  );
}
