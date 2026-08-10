/**
 * Where a change sits on the ruler an investigation is read against.
 *
 * The console draws no query of its own for this. Everything here comes out of
 * the run's own transcript: the agent called the change capability, the result
 * entered the trace, and this reads it back. That is not a shortcut — it is the
 * property that matters. A footer that re-queried would eventually show a change
 * the investigation never saw, and the picture would then disagree with the
 * report printed above it.
 *
 * Two decisions are worth stating.
 *
 * **The ruler is the change window, and the investigation is a mark on it.** The
 * question the picture answers is "what happened shortly before this broke", so
 * the axis has to be the interval the changes were looked for in, with the
 * moment of the investigation placed against them. A ruler spanning the run's
 * own duration would put every change off the left edge.
 *
 * **The grading survives.** A mark on a timeline is the most persuasive thing on
 * a page, and a change that merely shares the window is drawn as one — otherwise
 * the overlay quietly asserts the correlation the correlation refused to make.
 */

/** The capability whose result this overlay is drawn from. */
export const CHANGES_TOOL = 'changes_in_window';

/** One thing on the ruler: a change, or the investigation itself. */
export interface PlacedMark {
  readonly id: string;
  /** ISO 8601, as the deployment reported it. */
  readonly at: string;
  /** Where along the ruler it falls, 0 to 100. */
  readonly percent: number;
  readonly strength: string;
  readonly temporalOnly: boolean;
  readonly applied: boolean;
  readonly title: string;
  readonly detail: string;
}

/** The whole footer: an interval, what was said about it, and what is on it. */
export interface ChangeRuler {
  readonly start: string;
  readonly end: string;
  readonly statement: string;
  readonly marks: readonly PlacedMark[];
  /** Where the investigation itself sits, when it sits on the ruler at all. */
  readonly investigation?: PlacedMark | undefined;
}

function field(record: unknown, name: string): unknown {
  return Reflect.get(Object(record), name);
}

function text(record: unknown, name: string): string {
  const found = field(record, name);
  return typeof found === 'string' ? found : '';
}

function flag(record: unknown, name: string): boolean {
  return field(record, name) === true;
}

function list(record: unknown, name: string): readonly unknown[] {
  const found = field(record, name);
  return Array.isArray(found) ? found : [];
}

/** An instant as milliseconds, or `undefined` when it is not one. */
function instant(value: string): number | undefined {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? undefined : parsed;
}

/**
 * Where `at` falls between `start` and `end`, as a percentage.
 *
 * Clamped rather than allowed to run past either end. Something outside the
 * window is drawn at the edge it left by, which is honest — the alternative is a
 * mark positioned off the element, which reads as no mark at all.
 */
function place(at: number, start: number, end: number): number {
  const ratio = ((at - start) / (end - start)) * 100;
  return Math.min(100, Math.max(0, ratio));
}

/** The last successful change result in a replay, or `undefined`. */
function resultOf(replay: unknown): unknown {
  let found: unknown;
  for (const turn of list(replay, 'turns')) {
    for (const call of list(turn, 'calls')) {
      if (text(call, 'name') === CHANGES_TOOL) {
        const result = field(call, 'result');
        // The last one wins: an investigation that asked twice asked the second
        // time about the resource it had by then established.
        if (result !== null && result !== undefined) found = result;
      }
    }
  }
  return found;
}

/**
 * The footer for one run, or `undefined` when there is nothing to draw.
 *
 * `undefined` rather than an empty ruler for a run that never asked what
 * changed. An empty axis on every investigation would read as "nothing changed",
 * which is a claim only a run that asked can make.
 */
export function rulerFromReplay(
  replay: unknown,
  options: { readonly startedAt: string },
): ChangeRuler | undefined {
  const result = resultOf(replay);
  if (result === undefined) return undefined;

  const window = field(result, 'window');
  const start = instant(text(window, 'start'));
  const end = instant(text(window, 'end'));
  if (start === undefined || end === undefined || end <= start) return undefined;

  const marks: PlacedMark[] = [];
  for (const entry of list(result, 'changes')) {
    const at = instant(text(entry, 'instant'));
    if (at === undefined) continue;
    marks.push({
      id: text(entry, 'change_id'),
      at: text(entry, 'instant'),
      percent: place(at, start, end),
      strength: text(entry, 'strength'),
      temporalOnly: flag(entry, 'temporal_only'),
      applied: flag(entry, 'applied'),
      title: text(entry, 'message'),
      detail: text(entry, 'why'),
    });
  }
  marks.sort(
    (left, right) => left.percent - right.percent || left.id.localeCompare(right.id),
  );

  const started = instant(options.startedAt);
  return {
    start: text(window, 'start'),
    end: text(window, 'end'),
    statement: text(result, 'statement'),
    marks,
    investigation:
      started === undefined
        ? undefined
        : {
            id: 'investigation',
            at: options.startedAt,
            percent: place(started, start, end),
            strength: 'investigation',
            temporalOnly: false,
            applied: false,
            title: '',
            detail: '',
          },
  };
}
