import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { Badge, ResolvedChip } from '@/components/status';
import { ListIcon } from '@/design/icons';
import { formatDuration, formatNumber, timestamp } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { CopyReport } from './copy-report';
import { DecisionControls } from './decision';
import { EvidenceChip, type RunEvidence } from './run-evidence';
import { Report } from './report';
import { RunCardToggle } from './run-card-toggle';
import { field, list, number, text, type Read } from './read';
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
 * reads it: the run's own headline and the resources it names, then what
 * happened, what it reaches, why, what to do, what is worth remembering, and
 * then — last, because it is the working-out rather than the answer — what it
 * actually did. Nothing here is synthesised for the layout's benefit; a
 * section with no data behind it says so in a sentence rather than being
 * filled, and a fact the deployment does not record is absent rather than
 * derived from the report's prose.
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
  /**
   * The six stages the investigation ran, in order, as the trace recorded
   * them. Empty for a run whose trace holds no stages — every run recorded
   * before the deployment wrote them down, and any loop driven outside the
   * pipeline — and the card falls back to the flat list of turns there,
   * which is the only honest thing to draw when stages is all it lacks.
   */
  readonly stages: readonly RunCardStage[];
  readonly calls: number;
  readonly events: number;
  readonly waiting: readonly string[];
  /** Actions this run proposed that a person has not yet decided. */
  readonly decisions: readonly RunCardDecision[];
  readonly supporting: readonly string[];
  readonly missing: readonly string[];
  /**
   * What this run left in the episodic corpus, or nothing, or the fact that
   * the corpus could not be read.
   *
   * Three answers rather than two, and the third is the one worth the type.
   * A run that wrote no episode is ordinary — extraction skips a conclusion
   * too short to learn from, and a run that failed reached none at all — so
   * the deployment answers `null` and the card prints a calm sentence. A read
   * that never came back is a different thing entirely, and a card that
   * collapsed the two would tell a reader "this taught nobody anything" on
   * the strength of a gateway it could not reach.
   */
  readonly episode: Read<RunCardEpisode | null>;
}

/** One episode the corpus holds, as the card draws it. */
export interface RunCardEpisode {
  readonly title: string;
  readonly summary: string;
  /** The corpus's own word for how it went, drawn as the badge finds it. */
  readonly outcome: string;
  readonly components: readonly string[];
}

/**
 * One action the run proposed and stopped at, waiting on a person.
 *
 * Separate from `waiting`, which is questions. Both are open interactions and
 * both hold the run up, but they ask for different things: a question wants an
 * answer typed, an approval wants a verdict — and only the second is something
 * a reader can settle by pressing a button.
 */
export interface RunCardDecision {
  readonly interactionId: string;
  readonly text: string;
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

/**
 * One of the six stages, and whatever ran inside it.
 *
 * `turns` is empty for five of the six and stays empty. Only the gathering
 * stage drives the loop; intake and diagnosis each make a model call of their
 * own and hand back a value, and resolving and planning make none. That is why
 * `llmCalls` is here: without it a stage that spent a model call and a stage
 * that did nothing draw identically, and the second is the one worth spotting.
 */
export interface RunCardStage {
  /** The trace's own name for the stage — `gather_evidence`, not a label. */
  readonly stage: string;
  /** The one line the stage wrote about what it established. May be empty. */
  readonly finding: string;
  readonly durationMs: number;
  readonly llmCalls: number;
  readonly failed: boolean;
  readonly turns: readonly RunCardTurn[];
}

/**
 * Calls shown before a long stage folds the rest away.
 *
 * Five, because the gathering stage of a real investigation runs eleven or
 * more and the point of the grouping is that six stages fit on one screen. The
 * rest are a press away and are still in the document, so a reader searching
 * the page finds a capability that is folded.
 */
const VISIBLE_CALLS = 5;

/**
 * The turns `replay` carries, in the shape the card draws them.
 *
 * `rationale` is the model's own account of the turn, and only that. The other
 * rationale a turn carries — why those capabilities were the ones offered —
 * reads "ranked 75, offered 40, cut by the ceiling 19" and is identical on
 * every turn of a run: capability scoring, not reasoning. Falling back to it
 * filled six group headings with the same machine sentence, which is worse
 * than the honest line saying the model wrote none. It stays where the run's
 * own page already keeps it, behind its own disclosure.
 */
export function turnsFrom(replay: unknown): readonly RunCardTurn[] {
  return list(replay, 'turns').map(turnFrom);
}

/** One turn as the replay serves it, in the shape the card draws it. */
function turnFrom(turn: unknown): RunCardTurn {
  return {
    index: number(turn, 'index'),
    rationale: text(turn, 'model_rationale'),
    model: text(turn, 'model'),
    calls: list(turn, 'calls').map((call) => ({
      callId: text(call, 'call_id'),
      name: text(call, 'name'),
      status: text(call, 'status'),
      error: text(call, 'error'),
      durationMs: number(call, 'duration_ms'),
    })),
  };
}

/**
 * The stages `replay` carries, in the shape the card draws them.
 *
 * Nothing is derived here and nothing is filled in. A run whose trace recorded
 * no stages returns nothing, and the card draws the flat turn list it always
 * drew; a stage the deployment wrote with no finding on it keeps the empty
 * string, and the card says the stage recorded none rather than composing one
 * out of what the turns happen to contain. The whole reason the deployment
 * writes a stage down is that four of the six leave nothing a console could
 * reconstruct them from.
 */
export function stagesFrom(replay: unknown): readonly RunCardStage[] {
  return list(replay, 'stages').map((stage) => ({
    stage: text(stage, 'stage'),
    finding: text(stage, 'finding'),
    durationMs: number(stage, 'duration_ms'),
    llmCalls: number(stage, 'llm_calls'),
    failed: field(stage, 'failed') === true,
    turns: list(stage, 'turns').map(turnFrom),
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

/**
 * What this run left behind for the next one to find.
 *
 * Three renderings for three answers, and they are kept apart on purpose.
 * `null` is a run that wrote no episode, which is ordinary and gets a
 * sentence. An unread corpus names the endpoint that would have answered,
 * because a reader who is told "nothing was written" has been told something
 * about the *run*, and only a read that came back can say that.
 */
function Remembered({
  locale,
  episode,
}: {
  readonly locale: Locale;
  readonly episode: Read<RunCardEpisode | null>;
}): ReactNode {
  if (episode.kind === 'unknown') {
    return (
      <p data-testid="run-episode-unknown" className="text-small text-muted">
        {message(locale, 'run.remembered.unknown', {
          dependency: episode.dependency,
        })}
      </p>
    );
  }
  if (episode.value === null) {
    return (
      <p className="text-small text-muted">{message(locale, 'run.remembered.none')}</p>
    );
  }
  const written = episode.value;
  return (
    <div data-testid="run-episode" className="flex flex-col gap-2">
      <div className="flex items-start gap-2">
        <Badge status={written.outcome} className="shrink-0" />
        <span className="text-small grow">{written.title}</span>
      </div>
      {written.summary === '' ? null : (
        <p className="text-small text-muted">{written.summary}</p>
      )}
      {written.components.length === 0 ? null : (
        <div className="flex flex-wrap items-center gap-2">
          {written.components.map((component) => (
            <span
              key={component}
              data-testid="run-episode-component"
              className="edge border-border rounded-1 bg-sunken px-2 text-meta font-mono text-muted"
            >
              {component}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** One capability call, drawn the same wherever it sits. */
function CallRow({
  locale,
  call,
}: {
  readonly locale: Locale;
  readonly call: RunCardCall;
}): ReactNode {
  return (
    <li
      data-testid="run-call"
      className="flex items-center gap-3 px-3 py-2 edge border-border border-x-0 border-t-0 last:border-b-0"
    >
      <Badge status={call.status} className="shrink-0" />
      <span className="font-mono text-meta grow min-w-0 break-all">{call.name}</span>
      {call.error === '' ? null : (
        <span className="text-meta text-danger min-w-0 break-words">{call.error}</span>
      )}
      {/* Nothing rather than "not recorded" on every row. A duration this
          deployment does not record is a column of the same three words down
          the whole trace, which reads as a fault and is an absence. */}
      {call.durationMs === 0 ? null : (
        <span className="text-meta text-muted tabular-nums shrink-0">
          {formatDuration(locale, call.durationMs / 1000)}
        </span>
      )}
    </li>
  );
}

/**
 * One stage, its line, and the calls it made.
 *
 * The calls are listed under the stage rather than under the turns inside it,
 * which is what the design asks for and is the right reading: an operator
 * scanning "what it did" is looking for which capabilities answered, and the
 * loop's iteration boundaries are an implementation detail of one stage of
 * six. The turn-by-turn transcript, reasoning and all, is still on the run's
 * own page — this is the summary, and it is grouped by the thing the product
 * says an investigation is made of.
 *
 * A stage with no calls draws none. For four of the six that is permanent, and
 * the line plus the model-call count is the whole of what they have to say —
 * which is more than the flat turn list said about them, which was nothing.
 */
function StageRow({
  locale,
  stage,
}: {
  readonly locale: Locale;
  readonly stage: RunCardStage;
}): ReactNode {
  const calls = stage.turns.flatMap((turn) => turn.calls);
  const shown = calls.slice(0, VISIBLE_CALLS);
  const folded = calls.slice(VISIBLE_CALLS);
  return (
    <div
      data-testid="run-stage"
      data-stage={stage.stage}
      className="edge border-border rounded-2 bg-sunken"
    >
      <div className="flex items-start gap-3 p-3">
        <span className="text-small shrink-0 w-column-word">
          {stageLabel(locale, stage.stage)}
        </span>
        <p className="text-small text-muted grow min-w-0">
          {stage.finding === ''
            ? message(locale, 'run.stage.noFinding')
            : stage.finding}
        </p>
        {stage.failed ? <Badge status="failed" className="shrink-0" /> : null}
        {calls.length === 0 && stage.llmCalls > 0 ? (
          <span className="text-meta text-muted shrink-0">
            {message(locale, 'run.stage.modelCalls', { calls: String(stage.llmCalls) })}
          </span>
        ) : null}
        {calls.length === 0 ? null : (
          <span className="text-meta text-muted shrink-0">
            {message(locale, 'run.did.calls', { calls: String(calls.length) })}
          </span>
        )}
        {stage.durationMs === 0 ? null : (
          <span className="text-meta text-muted tabular-nums shrink-0">
            {formatDuration(locale, stage.durationMs / 1000)}
          </span>
        )}
      </div>
      {calls.length === 0 ? null : (
        <ul className="edge border-border border-x-0 border-b-0">
          {shown.map((call) => (
            <CallRow key={call.callId} locale={locale} call={call} />
          ))}
        </ul>
      )}
      {folded.length === 0 ? null : (
        // A native disclosure rather than a client component. The list is
        // rendered on the server either way — a reader searching the page
        // finds a folded capability, and a browser with no JavaScript still
        // opens it.
        <details
          data-testid="run-stage-more"
          className="edge border-border border-x-0 border-b-0"
        >
          <summary className="px-3 py-2 text-meta text-muted motion-hover hover:bg-hover cursor-pointer">
            {message(locale, 'run.did.more', { count: String(folded.length) })}
          </summary>
          <ul>
            {folded.map((call) => (
              <CallRow key={call.callId} locale={locale} call={call} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/**
 * The turns no recorded stage claims.
 *
 * Every turn, for a run whose trace holds no stages — which is exactly the
 * flat list the card drew before, and the right drawing for a run that has
 * nothing else. For a run still going it is the turns of the stage that has
 * not ended yet: a stage record is written when the stage *ends*, so the
 * gathering a reader is watching happen has turns and no stage. Dropping them
 * would empty the section on the one run somebody has the card open for.
 */
export function unplacedTurns(body: RunCardBody): readonly RunCardTurn[] {
  const placed = new Set(
    body.stages.flatMap((stage) => stage.turns.map((turn) => turn.index)),
  );
  return body.turns.filter((turn) => !placed.has(turn.index));
}

/** The six the pipeline runs, and the only names this console has a label for. */
const STAGE_NAMES = [
  'resolve_integrations',
  'intake',
  'plan_evidence',
  'gather_evidence',
  'diagnose',
  'deliver',
] as const;

/**
 * What one stage is called on screen.
 *
 * The trace's own name when the console has no label for it. A deployment
 * running a newer pipeline records a stage this build has never heard of, and
 * showing `enrich_context` is an ugly label and a true one — dropping the row
 * would make the card disagree with the trace about how many stages ran, which
 * is the one thing a summary of a run must not do.
 */
export function stageLabel(locale: Locale, stage: string): string {
  const known = STAGE_NAMES.find((name) => name === stage);
  return known === undefined ? stage : message(locale, `run.stage.${known}`);
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
            {/* The run's own sentence, whole, before the document.

                The header row above shows the *subject*, which is that
                sentence clipped to one line and to a hundred and twenty
                characters, and "What happened" below shows the report — a
                markdown document that opens on a heading. So the one line
                the run wrote to say what it found had nowhere on this card
                to be read in full, which is the line somebody opened the
                card for.

                The resources sit with it rather than in a section of their
                own: `lxc/122` and `pve01` are what the sentence is *about*,
                and a reader who has just read it is holding exactly the
                question they answer. Nothing else joins them — a severity
                and a resolution belong here too, and the run record carries
                neither, so neither is drawn rather than derived from the
                report's prose. */}
            {body.headline === '' ? null : (
              <div
                data-testid="run-headline-block"
                className="flex flex-col gap-2 p-4 edge border-border border-x-0 border-t-0"
              >
                <h4 data-testid="run-headline" className="text-section">
                  {body.headline}
                </h4>
                {body.touchedResources.length === 0 ? null : (
                  <div className="flex flex-wrap items-center gap-2">
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
              </div>
            )}

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
                <p className="text-small text-muted">
                  {message(locale, 'run.happened.none')}
                </p>
              ) : (
                <Report text={body.report} />
              )}
            </Section>

            {/* What holds this run beyond itself. The resources it touched
                moved up to the headline they belong to, so what is left here
                is the incident it was filed under — which is the only place
                this card can send a reader who wants the other runs that
                answered the same firing. */}
            <Section label={message(locale, 'run.section.reaches')}>
              {body.incidentId === '' ? (
                <p className="text-small text-muted">
                  {message(locale, 'run.reaches.none')}
                </p>
              ) : (
                <Link href={`/incidents/${body.incidentId}`}>
                  {message(locale, 'run.links.incident')}
                </Link>
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
              {body.decisions.length === 0 && body.waiting.length === 0 ? (
                <p className="text-small text-muted">
                  {message(locale, 'run.todo.none')}
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {/* Decisions first. A question can wait for the reader to
                      think; an action the run stopped at is holding the whole
                      investigation, and in the design it had been holding it
                      for twenty-two minutes. */}
                  {body.decisions.map((decision) => (
                    <li
                      key={decision.interactionId}
                      data-testid="run-decision"
                      className="edge border-warning rounded-2 bg-warning-bg p-3 text-small flex flex-col gap-3"
                    >
                      <span className="flex items-start gap-2">
                        <Badge status="waiting" className="shrink-0" />
                        <span className="grow">{decision.text}</span>
                      </span>
                      <DecisionControls
                        interactionId={decision.interactionId}
                        labels={{
                          approve: message(locale, 'proposal.approve'),
                          reject: message(locale, 'proposal.reject'),
                          reason: message(locale, 'proposal.reason'),
                          reasonRequired: message(locale, 'proposal.reason.required'),
                        }}
                      />
                    </li>
                  ))}
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
              label={message(locale, 'run.section.remembered')}
              action={
                body.episode.kind === 'known' && body.episode.value !== null ? (
                  <ResolvedChip
                    role="info"
                    shape="filled-circle"
                    label={message(locale, 'run.remembered.written')}
                    testId="run-episode-written"
                  />
                ) : undefined
              }
            >
              <Remembered locale={locale} episode={body.episode} />
            </Section>

            {/* Grouped by stage, because that is what an investigation is.
                The section counted "16 events across 6 turns" and listed the
                loop's iterations, which is a complete account of the fourth
                stage of six and silence about the rest — including the two
                that each spend a model call and produce no turn at all, so no
                amount of grouping the turn list could have recovered them.

                The turns that fall outside a recorded stage are still drawn,
                below. A stage is written down when it *ends*, so a run still
                gathering has turns whose stage the trace does not hold yet,
                and grouping strictly would make them vanish off the card
                belonging to the one run somebody is actually watching. */}
            <Section
              label={message(locale, 'run.section.did')}
              action={
                <span className="text-meta text-muted">
                  {body.stages.length === 0
                    ? message(locale, 'run.did.summary', {
                        events: String(body.events),
                        turns: String(body.turns.length),
                      })
                    : message(locale, 'run.did.stages', {
                        events: String(body.events),
                        stages: String(body.stages.length),
                      })}
                </span>
              }
            >
              <div className="flex flex-col gap-3">
                {body.stages.map((stage) => (
                  <StageRow key={stage.stage} locale={locale} stage={stage} />
                ))}
                {unplacedTurns(body).map((turn) => (
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
                          <CallRow key={call.callId} locale={locale} call={call} />
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
