import type { ReactNode } from 'react';

import NextLink from 'next/link';

import { isSettled } from '@/design/status';
import { formatDuration, formatNumber } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { cx } from '@/design/cx';
import { field, text } from './read';
import { triggerLabel } from './run-trigger';

/**
 * "Em execução agora": the runs the deployment is working right now, named
 * rather than counted, with a card per run and the stage each has reached.
 *
 * **What "não terminado" means here, and why it is narrower than the
 * literal reading of the spec's own evidence query.** A run's `status` is
 * one of six words (`console/src/design/status.ts`'s own `RUN_STATUSES`),
 * and `status NOT IN ('completed','failed','cancelled')` — the query the
 * spec's evidence section names — also matches `interrupted`: a run a reaper
 * marked that way because the process running it is gone, days ago, with no
 * title. Staging carries eleven of exactly that shape and zero of anything
 * else non-terminal. A band built on the literal query would be eleven
 * zombies wide, pushing the one run actually in flight off the six-card cap
 * this band has.
 *
 * `isSettled` (`@/design/status`, frozen foundation, already exported,
 * already the predicate `dashboard.tsx` uses today for a different figure on
 * this same screen) declares `interrupted` settled for exactly this reason —
 * its own docstring: "nothing is going to resume producing events for a run
 * the store only marked this way". `inFlightRuns` below is `!isSettled`,
 * which resolves to `{running, suspended}` — the same pair
 * `incident-detail.tsx`'s own local `LIVE_RUN_STATUSES` already uses to
 * decide whether a linked run is still live. Not a new invention: the
 * existing vocabulary, read for the question this band actually asks.
 */

/** How many segments a run's stage bar always draws. */
export const RUN_BAND_STAGE_COUNT = 6;

/** How many cards the band draws before the rest are a count behind a link. */
export const RUN_BAND_VISIBLE_MAX = 6;

export type StageState = 'completed' | 'current' | 'future';

/**
 * The six segments' states, from the last **completed** stage.
 *
 * `stageIndex` absent means no stage has completed — the console's own
 * existing degradation for "not yet known" — and draws all six future.
 * `stageIndex === RUN_BAND_STAGE_COUNT` (every stage completed, run not yet
 * terminated — the gap between the last stage finishing and the run being
 * marked settled) draws all six completed with **no current segment**: a
 * segment cannot carry both states, so the literal "current is index + 1"
 * rule is not applied past the last index.
 */
export function stageStates(stageIndex: number | undefined): readonly StageState[] {
  const states: StageState[] = [];
  for (let position = 1; position <= RUN_BAND_STAGE_COUNT; position += 1) {
    if (stageIndex === undefined) {
      states.push('future');
    } else if (position <= stageIndex) {
      states.push('completed');
    } else if (position === stageIndex + 1 && stageIndex < RUN_BAND_STAGE_COUNT) {
      states.push('current');
    } else {
      states.push('future');
    }
  }
  return states;
}

/** `records`, kept to the ones this band draws a card for. */
export function inFlightRuns(records: readonly unknown[]): readonly unknown[] {
  return records.filter((record) => !isSettled(text(record, 'status')));
}

/** `record.stage_index` when it names a real segment, `undefined` otherwise.
 *
 * A value the console has never seen — negative, non-integer, past the last
 * segment — is read as absent rather than trusted, because a malformed
 * index must not put two segments in the "current" state or crash the bar;
 * absent is the same honest degradation the field's own absence already
 * gets.
 */
function stageIndexOf(record: unknown): number | undefined {
  const found = field(record, 'stage_index');
  if (typeof found !== 'number' || !Number.isInteger(found)) return undefined;
  if (found < 0 || found > RUN_BAND_STAGE_COUNT) return undefined;
  return found;
}

/** One run, as this band's card reads it. */
export interface RunCardData {
  readonly id: string;
  /** The objective typed, or the completed run's headline — served, never derived. */
  readonly title: string;
  readonly trigger: string;
  readonly elapsedSeconds: number;
  readonly stageIndex: number | undefined;
}

/** `record`, as `RunCardData` — reading only, no title or stage derived here. */
export function runCardOf(record: unknown, now: Date): RunCardData {
  const startedAt = Date.parse(text(record, 'started_at'));
  const elapsedSeconds = Number.isNaN(startedAt)
    ? 0
    : Math.max(0, (now.getTime() - startedAt) / 1000);
  return {
    id: text(record, 'run_id'),
    title: text(record, 'headline'),
    trigger: text(record, 'trigger'),
    elapsedSeconds,
    stageIndex: stageIndexOf(record),
  };
}

/** One segment of the stage bar. */
function StageSegment({ state }: { readonly state: StageState }): ReactNode {
  return (
    <span
      data-testid="run-card-stage"
      data-state={state}
      className={cx(
        'h-1 flex-1 rounded-1',
        state === 'completed'
          ? 'bg-accent'
          : state === 'current'
            ? 'stage-shimmer'
            : 'bg-sunken',
      )}
    />
  );
}

interface RunCardProps {
  readonly locale: Locale;
  readonly card: RunCardData;
}

/** One run's card: title, trigger, stage bar, elapsed — the entrance treatment always present. */
function RunCard({ locale, card }: RunCardProps): ReactNode {
  return (
    <li
      key={card.id}
      data-testid="run-card"
      data-run-id={card.id}
      // `slide-in` plays only on genuine mount (a new key entering the DOM);
      // an existing card re-rendered with updated fields keeps its node and
      // never replays it. `prefers-reduced-motion` is handled globally by
      // the utility itself (`console/src/app/globals.css`), not here.
      className="slide-in edge border-border rounded-2 bg-raised px-4 py-3 flex flex-col gap-2"
    >
      <div className="flex items-center gap-3">
        <span
          data-testid="run-card-title"
          className="text-strong truncate flex-1 min-w-0"
        >
          {card.title}
        </span>
        <span className="text-meta text-muted shrink-0">
          {triggerLabel(locale, card.trigger)}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex gap-1 flex-1">
          {stageStates(card.stageIndex).map((state, index) => (
            <StageSegment key={`${card.id}-stage-${String(index)}`} state={state} />
          ))}
        </div>
        <span
          data-testid="run-card-elapsed"
          className="font-mono text-meta text-muted tabular-nums shrink-0"
        >
          {formatDuration(locale, card.elapsedSeconds)}
        </span>
      </div>
    </li>
  );
}

export interface RunBandProps {
  readonly locale: Locale;
  /** Every run in flight, unsliced — the header count reads its length. */
  readonly runs: readonly RunCardData[];
  readonly followedCount: number;
  readonly blockedCount: number;
  readonly moreHref: string;
}

/** "Em execução agora": up to six cards, a header naming every count, an overflow link. */
export function RunBand({
  locale,
  runs,
  followedCount,
  blockedCount,
  moreHref,
}: RunBandProps): ReactNode {
  const visible = runs.slice(0, RUN_BAND_VISIBLE_MAX);

  return (
    <section
      data-testid="run-band"
      aria-label={message(locale, 'dashboard.runBand.title')}
      className="edge border-border rounded-3 bg-raised px-4 py-4 flex flex-col gap-3"
    >
      <header className="flex items-center gap-4 flex-wrap">
        <span className="flex items-center gap-2 text-strong">
          {message(locale, 'dashboard.runBand.title')}
        </span>
        <span className="text-meta text-muted flex items-center gap-1">
          <span data-testid="run-band-flight-count">
            {formatNumber(locale, runs.length)}
          </span>
          {message(locale, 'dashboard.runBand.flight')}
          {' · '}
          <span data-testid="run-band-followed-count">
            {formatNumber(locale, followedCount)}
          </span>
          {message(locale, 'dashboard.runBand.followed')}
          {' · '}
          <span
            className={blockedCount > 0 ? 'text-warning' : undefined}
            data-testid="run-band-blocked-count"
          >
            {formatNumber(locale, blockedCount)}
          </span>{' '}
          {message(locale, 'dashboard.runBand.blocked')}
        </span>
        {/* The band's permanent way out, drawn whether or not a seventh run
            has pushed a card off the end. The count it would otherwise carry
            is already beside it — "N em voo" reads the unsliced list — so
            hiding the link until something overflows only ever removed the
            one route off this band to the full listing. */}
        <a
          href={moreHref}
          data-testid="run-band-more"
          className="ml-auto text-meta text-accent hover:underline"
        >
          {message(locale, 'dashboard.runBand.more')}
        </a>
      </header>

      {visible.length === 0 ? (
        <p data-testid="run-band-empty" className="text-small text-muted">
          {message(locale, 'dashboard.runBand.empty')}{' '}
          <NextLink href="/runs" className="text-accent hover:underline">
            {message(locale, 'dashboard.runBand.empty.action')}
          </NextLink>
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {visible.map((card) => (
            <RunCard key={card.id} locale={locale} card={card} />
          ))}
        </ul>
      )}
    </section>
  );
}
