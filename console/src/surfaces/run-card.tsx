import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { Badge } from '@/components/status';
import { ListIcon } from '@/design/icons';
import { formatDuration, formatNumber, timestamp } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { CopyReport } from './copy-report';
import { EvidenceChip, type RunEvidence } from './run-evidence';
import { Report } from './report';
import { RunCardToggle } from './run-card-toggle';
import { field, list, number, text } from './read';
import { triggerLabel } from './run-trigger';

/**
 * One investigation, open where it sits.
 *
 * Every row used to navigate to its own page, which is the arrangement that
 * loses the list. Somebody comparing the eight firings of one subject went
 * back and forth eight times and lost their place on each return — and the
 * comparison, which is the actual work, was never on one screen.
 *
 * So the card grows instead. The address carries which row is open
 * (`?selected=`), so the expansion is still a thing somebody can send, still
 * survives a reload, and is still rendered on the server rather than fetched
 * into a browser after the fact. The run's own page is kept and linked, for a
 * reader who wants only this run and a link that says so.
 *
 * What the expansion shows is what the run recorded, in the order a person
 * reads it: what happened, what it reaches, in order, why, what to do, and
 * then — last, because it is the working-out rather than the answer — what it
 * actually did. Nothing here is synthesised for the layout's benefit; a
 * section with no data behind it says so in a sentence rather than being
 * filled.
 */

/** Everything the header row of a card needs, whether open or closed. */
export interface RunCardHead {
  readonly runId: string;
  readonly subject: string;
  readonly subjectFull: string;
  readonly status: string;
  readonly trigger: string;
  readonly startedAt: string;
  readonly seconds: number;
  readonly evidence: RunEvidence;
}

/** What the expansion draws, read from the run's own detail and replay. */
export interface RunCardBody {
  /** The document the model wrote, in Markdown. Empty when it wrote none. */
  readonly report: string;
  readonly headline: string;
  readonly touchedResources: readonly string[];
  readonly incidentId: string;
  readonly tokens: number;
  readonly priced: boolean;
  readonly turns: readonly RunCardTurn[];
  readonly calls: number;
  readonly events: number;
  readonly waiting: readonly string[];
  readonly supporting: readonly string[];
  readonly missing: readonly string[];
}

/** One turn of the run, and the calls it made. */
export interface RunCardTurn {
  readonly index: number;
  readonly rationale: string;
  readonly model: string;
  readonly calls: readonly RunCardCall[];
}

/** One capability call, as the trace recorded it. */
export interface RunCardCall {
  readonly callId: string;
  readonly name: string;
  readonly status: string;
  readonly error: string;
  readonly durationMs: number;
}

/** The turns `replay` carries, in the shape the card draws them. */
export function turnsFrom(replay: unknown): readonly RunCardTurn[] {
  return list(replay, 'turns').map((turn) => ({
    index: number(turn, 'index'),
    // The model's own account of the turn, and only that. The other
    // rationale a turn carries — why those capabilities were the ones
    // offered — reads "ranked 75, offered 40, cut by the ceiling 19" and is
    // identical on every turn of a run: capability scoring, not reasoning.
    // Falling back to it filled six group headings with the same machine
    // sentence, which is worse than the honest line saying the model wrote
    // none. It stays where the run's own page already keeps it, behind its
    // own disclosure.
    rationale: text(turn, 'model_rationale'),
    model: text(turn, 'model'),
    calls: list(turn, 'calls').map((call) => ({
      callId: text(call, 'call_id'),
      name: text(call, 'name'),
      status: text(call, 'status'),
      error: text(call, 'error'),
      durationMs: number(call, 'duration_ms'),
    })),
  }));
}

/** The strings under `key`, or nothing at all when the value is not a list. */
function stringsOf(holder: unknown, key: string): readonly string[] {
  const found = field(holder, key);
  if (!Array.isArray(found)) return [];
  return found.filter((entry): entry is string => typeof entry === 'string');
}

/**
 * What the run named as backing its conclusion, and what it could not read.
 *
 * Read off the run's own record rather than off the replay. The replay's call
 * view carries a name, a status and a duration and has never carried a
 * payload, so the first version of this — which walked the replay looking for
 * the assessment's arguments — found nothing on every run ever recorded and
 * drew an empty section under a heading that promised one.
 */
export function namedEvidence(run: unknown): {
  readonly supporting: readonly string[];
  readonly missing: readonly string[];
} {
  return {
    supporting: stringsOf(run, 'evidence_supporting_names'),
    missing: stringsOf(run, 'evidence_missing_names'),
  };
}

/** A section of the opened card: a quiet label, then whatever it labels. */
function Section({
  label,
  action,
  children,
}: {
  readonly label: string;
  readonly action?: ReactNode;
  readonly children: ReactNode;
}): ReactNode {
  return (
    <section className="flex flex-col gap-2 p-4 edge border-border border-x-0 border-t-0 last:border-b-0">
      <div className="flex items-center gap-2">
        <h4 className="text-micro text-muted">{label}</h4>
        {action === undefined ? null : <div className="ml-auto">{action}</div>}
      </div>
      {children}
    </section>
  );
}

/** One measurement, in the row of them above the report. */
function Measure({
  label,
  value,
  note,
}: {
  readonly label: string;
  readonly value: string;
  readonly note?: string;
}): ReactNode {
  return (
    <div className="bg-sunken edge border-border rounded-2 p-3 flex flex-col gap-1">
      <span className="text-meta text-muted">{label}</span>
      <span className="text-section tabular-nums">{value}</span>
      {note === undefined ? null : <span className="text-meta text-muted">{note}</span>}
    </div>
  );
}

export interface RunCardProps {
  readonly locale: Locale;
  readonly now: Date;
  readonly zone: string;
  readonly head: RunCardHead;
  /** Where clicking the header goes: open when closed, closed when open. */
  readonly toggleHref: string;
  readonly open: boolean;
  /** Present only for the open card, because only it was read. */
  readonly body?: RunCardBody;
}

/** One card in the investigations list, closed or open. */
export function RunCard({
  locale,
  now,
  zone,
  head,
  toggleHref,
  open,
  body,
}: RunCardProps): ReactNode {
  const started = timestamp(locale, head.startedAt, now, zone);
  const none = message(locale, 'surface.none');

  return (
    <article
      data-testid="run-card"
      data-run={head.runId}
      data-open={open}
      className={`bg-raised edge rounded-3 shadow-1 ${open ? 'border-accent' : 'border-border'}`}
    >
      {/* The address still carries which card is open, so the expansion can be
          sent and survives a reload — but changing it is a router transition
          rather than a new document. A plain anchor here rebuilt the frame, the
          sidebar and every other panel on the page to open one card, which is
          the gesture somebody repeats most on this screen.

          The control itself is a client component: a transition has no progress
          bar of its own and does not swallow a second press, and both of those
          have to be answered where the pending state can be read. See
          `run-card-toggle.tsx`. */}
      <RunCardToggle
        href={toggleHref}
        open={open}
        label={message(locale, 'runs.row.opening')}
        className="flex items-center gap-4 p-4 motion-hover hover:bg-hover rounded-3"
      >
        <span className="sr-only">
          {open ? message(locale, 'runs.row.close') : message(locale, 'runs.row.open')}
        </span>
        <span className="shrink-0 rounded-2 edge border-border bg-sunken p-2 flex items-center justify-center">
          <ListIcon size="nav" className="text-muted" />
        </span>
        <span className="min-w-0 grow flex flex-col gap-1">
          {/* One line, in one type, in both states. This row is the handle
              somebody presses, and a handle that gets heavier and taller under
              the pointer is not a disclosure — it is the row being swapped for
              a different row at the moment everything below it moves. Opening
              a card used to do both at once, and that is the whole of why the
              expansion did not feel like one.

              Nothing is lost by holding it to a line: the tooltip carries the
              whole sentence while the card is shut, and the report carries it
              in full the moment it opens. */}
          <span
            data-testid="run-card-subject"
            className="text-body truncate"
            title={head.subjectFull}
          >
            {head.subject}
          </span>
          <span className="text-meta text-muted">
            {triggerLabel(locale, head.trigger)} ·{' '}
            <span className="font-mono">{`#${head.runId.slice(0, 8)}`}</span>
          </span>
        </span>
        <Badge status={head.status} className="shrink-0" />
        <EvidenceChip locale={locale} evidence={head.evidence} className="shrink-0" />
        <span className="text-meta text-muted tabular-nums shrink-0 w-column-measure text-right">
          {head.seconds === 0 ? none : formatDuration(locale, head.seconds)}
        </span>
        <time
          dateTime={started.iso}
          title={started.absolute}
          className="text-meta text-muted shrink-0 w-column-word text-right"
        >
          {started.relative}
        </time>
      </RunCardToggle>

      {open && body !== undefined ? (
        <div
          data-testid="run-card-body"
          className="edge border-border border-x-0 border-b-0"
        >
          <div className="p-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Measure
              label={message(locale, 'run.measure.duration')}
              value={head.seconds === 0 ? none : formatDuration(locale, head.seconds)}
            />
            <Measure
              label={message(locale, 'run.measure.calls')}
              value={formatNumber(locale, body.calls)}
            />
            <Measure
              label={message(locale, 'run.measure.trigger')}
              value={triggerLabel(locale, head.trigger)}
            />
            <Measure
              label={message(locale, 'run.measure.tokens')}
              value={formatNumber(locale, body.tokens)}
              {...(body.priced
                ? {}
                : { note: message(locale, 'run.measure.unpriced') })}
            />
          </div>

          <div className="mx-4 mb-4 edge border-border rounded-2 bg-surface overflow-hidden">
            <Section
              label={message(locale, 'run.section.happened')}
              action={
                body.report === '' ? undefined : (
                  <CopyReport
                    text={body.report}
                    labels={{
                      copy: message(locale, 'run.report.copy'),
                      copied: message(locale, 'run.report.copied'),
                      refused: message(locale, 'run.report.copyRefused'),
                    }}
                  />
                )
              }
            >
              {body.report === '' ? (
                <p className="text-small">{body.headline}</p>
              ) : (
                <Report text={body.report} />
              )}
            </Section>

            <Section label={message(locale, 'run.section.reaches')}>
              {body.touchedResources.length === 0 && body.incidentId === '' ? (
                <p className="text-small text-muted">
                  {message(locale, 'run.reaches.none')}
                </p>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {body.incidentId === '' ? null : (
                    <Link href={`/incidents/${body.incidentId}`}>
                      {message(locale, 'run.links.incident')}
                    </Link>
                  )}
                  {body.touchedResources.map((resource) => (
                    <span
                      key={resource}
                      data-testid="run-touched"
                      className="edge border-border rounded-1 bg-sunken px-2 text-meta font-mono text-muted"
                    >
                      {resource}
                    </span>
                  ))}
                </div>
              )}
            </Section>

            <Section label={message(locale, 'run.section.why')}>
              {body.supporting.length === 0 && body.missing.length === 0 ? (
                <p className="text-small text-muted">
                  {message(locale, 'run.why.none')}
                </p>
              ) : (
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div className="flex flex-col gap-1">
                    <span className="text-micro text-muted">
                      {message(locale, 'run.why.supporting')}
                    </span>
                    <ul className="flex flex-col gap-1">
                      {body.supporting.map((entry) => (
                        <li key={entry} className="text-small flex gap-2">
                          <span className="text-success" aria-hidden="true">
                            ·
                          </span>
                          {entry}
                        </li>
                      ))}
                    </ul>
                  </div>
                  {body.missing.length === 0 ? null : (
                    <div className="flex flex-col gap-1">
                      <span className="text-micro text-warning">
                        {message(locale, 'run.why.missing')}
                      </span>
                      <ul className="flex flex-col gap-1">
                        {body.missing.map((entry) => (
                          <li key={entry} className="text-small text-muted flex gap-2">
                            <span className="text-warning" aria-hidden="true">
                              ·
                            </span>
                            {entry}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </Section>

            <Section label={message(locale, 'run.section.todo')}>
              {body.waiting.length === 0 ? (
                <p className="text-small text-muted">
                  {message(locale, 'run.todo.none')}
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {body.waiting.map((question) => (
                    <li
                      key={question}
                      data-testid="run-waiting"
                      className="edge border-warning rounded-2 bg-warning-bg p-3 text-small"
                    >
                      {question}
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section
              label={message(locale, 'run.section.did')}
              action={
                <span className="text-meta text-muted">
                  {message(locale, 'run.did.summary', {
                    events: String(body.events),
                    turns: String(body.turns.length),
                  })}
                </span>
              }
            >
              <div className="flex flex-col gap-3">
                {body.turns.map((turn) => (
                  <div
                    key={turn.index}
                    data-testid="run-turn"
                    className="edge border-border rounded-2 bg-sunken"
                  >
                    <div className="flex items-start gap-3 p-3">
                      <span className="text-meta text-muted tabular-nums shrink-0">
                        {formatNumber(locale, turn.index)}
                      </span>
                      <p className="text-small grow">
                        {reasoningOf(locale, turn, body.report)}
                      </p>
                      <span className="text-meta text-muted shrink-0">
                        {message(locale, 'run.did.calls', {
                          calls: String(turn.calls.length),
                        })}
                      </span>
                    </div>
                    {turn.calls.length === 0 ? null : (
                      <ul className="edge border-border border-x-0 border-b-0">
                        {turn.calls.map((call) => (
                          <li
                            key={call.callId}
                            data-testid="run-call"
                            className="flex items-center gap-3 px-3 py-2 edge border-border border-x-0 border-t-0 last:border-b-0"
                          >
                            <Badge status={call.status} className="shrink-0" />
                            <span className="font-mono text-meta grow min-w-0 break-all">
                              {call.name}
                            </span>
                            {call.error === '' ? null : (
                              <span className="text-meta text-danger min-w-0 break-words">
                                {call.error}
                              </span>
                            )}
                            {/* Nothing rather than "not recorded" on every
                                row. A duration this deployment does not
                                record is a column of the same three words
                                down the whole trace, which reads as a fault
                                and is an absence. */}
                            {call.durationMs === 0 ? null : (
                              <span className="text-meta text-muted tabular-nums shrink-0">
                                {formatDuration(locale, call.durationMs / 1000)}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          </div>

          <div className="px-4 pb-4">
            <Link href={`/runs/${head.runId}`}>
              {message(locale, 'runs.row.openPage')}
            </Link>
          </div>
        </div>
      ) : null}
    </article>
  );
}

/**
 * What one turn's line says, which is never the report a second time.
 *
 * The last turn of a run is the turn that produced the answer, so the model's
 * own account of it *is* the report — and this slot is one line meant for why
 * a turn reached for the capabilities it did. Printing the conclusion here
 * put the whole document on the screen twice: once at the top, rendered, and
 * once at the bottom, raw, with its Markdown syntax showing.
 *
 * Compared against the report rather than guessed at by length or by looking
 * for a `#`. A turn whose reasoning genuinely *is* the document the card
 * already shows is the only turn this suppresses, and it says what that turn
 * did rather than going blank — "recorded no reasoning" would be false about
 * the one turn that did the most.
 */
export function reasoningOf(locale: Locale, turn: RunCardTurn, report: string): string {
  const written = turn.rationale.trim();
  if (written === '') return message(locale, 'run.did.noRationale');
  if (report.trim() !== '' && written === report.trim()) {
    return message(locale, 'run.did.wroteReport');
  }
  return written;
}
