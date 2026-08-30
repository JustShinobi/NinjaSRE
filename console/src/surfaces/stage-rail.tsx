import type { ReactNode } from 'react';
import { Fragment } from 'react';

import { CheckIcon, CloseIcon, SearchIcon } from '@/design/icons';
import { cx } from '@/design/cx';
import { formatDuration, formatNumber } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { STAGE_NAMES, stageLabel } from './run-card';

/**
 * The pipeline, drawn as six boxes instead of read nowhere.
 *
 * A run always has six stages, and until this component existed the screen
 * that executes them never said so — the operator watching a live
 * investigation had no way to tell "still gathering evidence" from "stuck",
 * because nothing on the page named a stage at all.
 *
 * One component draws both readings, the same way `Transcript` does. A
 * settled run passes what its replay recorded (`stagesFrom`, `run-card.tsx`)
 * and nothing is `active`; a live run passes what has arrived over the
 * stream so far (`LiveState.stages`, `console/src/live/reducer.ts`) with
 * `running` true, and the first stage the record has not named yet is drawn
 * as the active one.
 */

/** What one finished (or failed) stage looks like, from whichever reader built it. */
export interface StageRailEntry {
  readonly stage: string;
  readonly finding: string;
  readonly durationMs: number;
  readonly failed: boolean;
}

type RailState = 'done' | 'active' | 'failed' | 'future';

export interface RailItem {
  readonly stage: string;
  readonly state: RailState;
  readonly durationMs: number;
  /** One-based position in the drawn order — what a future stage shows. */
  readonly position: number;
}

/** The canonical six, as a set, so an unlisted stage the trace names is not lost. */
const CANONICAL = new Set<string>(STAGE_NAMES);

/**
 * The stages `entries` describes, positioned against the canonical order.
 *
 * The set and order of boxes drawn is never a hardcoded six: it is the
 * canonical vocabulary this console has labels for, plus — appended, in the
 * order the record names them — any stage `entries` carries that the
 * vocabulary does not. A pipeline shortened or extended by configuration is
 * drawn from what actually ran, never from what this build expected to see.
 *
 * No stage is drawn `active` once any recorded stage has failed: the run
 * ends inside the stage that failed, and nothing after it will run.
 *
 * Exported for the run list's own mini stage bar
 * (`console/src/surfaces/screens/runs.tsx`), which draws the same states as
 * thin segments instead of circles — one derivation, two presentations.
 */
export function railOf(
  entries: readonly StageRailEntry[],
  running: boolean,
): readonly RailItem[] {
  const byName = new Map(entries.map((entry) => [entry.stage, entry] as const));
  const extra = entries
    .map((entry) => entry.stage)
    .filter((name) => !CANONICAL.has(name));
  const order = [...STAGE_NAMES, ...extra];
  const anyFailed = entries.some((entry) => entry.failed);

  let activeAssigned = false;
  return order.map((stage, index) => {
    const position = index + 1;
    const found = byName.get(stage);
    if (found !== undefined) {
      return {
        stage,
        state: found.failed ? 'failed' : 'done',
        durationMs: found.durationMs,
        position,
      };
    }
    if (running && !anyFailed && !activeAssigned) {
      activeAssigned = true;
      return { stage, state: 'active', durationMs: 0, position };
    }
    return { stage, state: 'future', durationMs: 0, position };
  });
}

/**
 * The well each state draws, and what sits inside it.
 *
 * A future stage's own number is drawn *inside* its circle — the artboard's
 * own composition (`RunView.dc.html`'s numbered wells carry the digit as the
 * circle's own text content, not a caption underneath it); only a settled or
 * active stage gets a line below the circle, for its duration or its elapsed
 * time. `font-display` because the artboard sets the digit in Space Grotesk
 * (`class="sg"`), the same family every other number-as-a-glyph on this
 * board is set in.
 */
function StageMark({
  state,
  position,
  locale,
}: {
  readonly state: RailState;
  readonly position: number;
  readonly locale: Locale;
}): ReactNode {
  if (state === 'done') {
    return (
      <span className="flex items-center justify-center size-7 rounded-full bg-success text-on-success">
        <CheckIcon size="inline" />
      </span>
    );
  }
  if (state === 'failed') {
    return (
      <span className="flex items-center justify-center size-7 rounded-1 bg-danger text-on-danger">
        <CloseIcon size="inline" />
      </span>
    );
  }
  if (state === 'active') {
    return (
      <span className="pulse-live flex items-center justify-center size-7 rounded-full edge border-accent bg-accent-bg text-accent">
        <span className="pulse-live-ring" />
        <SearchIcon size="inline" />
      </span>
    );
  }
  return (
    <span
      data-testid="stage-number"
      className="flex items-center justify-center size-7 rounded-full edge border-border bg-sunken text-muted font-display text-meta"
    >
      {formatNumber(locale, position)}
    </span>
  );
}

/**
 * The connector between two consecutive boxes — solid once both sides are
 * settled, shimmering into the active one, otherwise unfilled.
 *
 * `size-7` matches the circle it sits beside, and `items-center` centres the
 * hairline inside that box — the same vertical middle the circle occupies,
 * without a hand-measured offset that would drift the moment the circle's
 * own size changed.
 */
function Connector({
  before,
  after,
}: {
  readonly before: RailState;
  readonly after: RailState;
}): ReactNode {
  const settled = (state: RailState): boolean => state === 'done' || state === 'failed';
  return (
    <span aria-hidden="true" className="flex-1 flex items-center size-7">
      <span
        className={cx(
          'w-full h-px',
          settled(before) && settled(after)
            ? 'bg-success'
            : settled(before) && after === 'active'
              ? 'stage-shimmer'
              : 'bg-sunken',
        )}
      />
    </span>
  );
}

/**
 * The same six states, as a thin bar instead of six circles — what the run
 * list draws inside a live card, where six 28px wells would not fit beside
 * a subject line and an elapsed time.
 */
export function StageBar({ locale, stages, running }: StageRailProps): ReactNode {
  const items = railOf(stages, running);
  return (
    <div
      className="flex gap-1"
      role="list"
      aria-label={message(locale, 'run.stage.rail.title')}
    >
      {items.map((item) => (
        <span
          key={item.stage}
          role="listitem"
          data-testid="stage-bar-segment"
          data-stage={item.stage}
          data-state={item.state}
          title={stageLabel(locale, item.stage)}
          className={cx(
            'flex-1 h-1 rounded-full',
            item.state === 'done'
              ? 'bg-success'
              : item.state === 'failed'
                ? 'bg-danger'
                : item.state === 'active'
                  ? 'stage-shimmer'
                  : 'bg-sunken',
          )}
        />
      ))}
    </div>
  );
}

export interface StageRailProps {
  readonly locale: Locale;
  readonly stages: readonly StageRailEntry[];
  /** Whether the run is still going — the only state a stage may be `active` in. */
  readonly running: boolean;
}

/** The six stages a run's own page names, in execution order, at the top. */
export function StageRail({ locale, stages, running }: StageRailProps): ReactNode {
  const items = railOf(stages, running);

  return (
    <div
      data-testid="stage-rail"
      role="list"
      aria-label={message(locale, 'run.stage.rail.title')}
      className="flex items-start gap-0"
    >
      {items.map((item, index) => (
        <Fragment key={item.stage}>
          <div
            data-testid="stage-item"
            data-stage={item.stage}
            data-state={item.state}
            role="listitem"
            className="flex flex-col items-center gap-1 w-column-word shrink-0"
          >
            <StageMark state={item.state} position={item.position} locale={locale} />
            <span
              className={cx(
                'text-meta text-center',
                item.state === 'future' ? 'text-muted' : 'text-text',
              )}
            >
              {stageLabel(locale, item.stage)}
            </span>
            {item.state === 'done' || item.state === 'failed' ? (
              <span
                data-testid="stage-duration"
                className="font-mono text-micro text-muted tabular-nums"
              >
                {formatDuration(locale, item.durationMs / 1000)}
              </span>
            ) : null}
          </div>
          {index < items.length - 1 ? (
            <Connector
              before={item.state}
              after={items[index + 1]?.state ?? 'future'}
            />
          ) : null}
        </Fragment>
      ))}
    </div>
  );
}
