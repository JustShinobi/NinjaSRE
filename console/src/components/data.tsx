import type { ReactNode } from 'react';
import { useId } from 'react';

import { cx } from '@/design/cx';
import { Badge } from '@/components/status';

/**
 * The components that carry the data, and the three cases that break them.
 *
 * A table at 320 pixels with eight columns. A cell holding one unbroken
 * identifier longer than its column. A payload larger than anybody will read.
 * Each has an answer here rather than a horizontal scrollbar and a shrug —
 * because each of those is what a console looks like on the phone somebody
 * picked up at three in the morning.
 */

/** How many lines of a payload are shown before it is bounded. */
export const PAYLOAD_LINE_BOUND = 200;

export interface Column {
  readonly key: string;
  readonly header: string;
  /** Right-aligned and tabular, because numbers are compared down a column. */
  readonly numeric?: boolean;
  /** Monospace, because an identifier is compared character by character. */
  readonly identifier?: boolean;
}

export interface Row {
  readonly id: string;
  readonly [key: string]: string;
}

export interface TableProps {
  readonly caption: string;
  readonly columns: readonly Column[];
  readonly rows: readonly Row[];
  readonly empty?: string;
}

/**
 * Rows and columns, with the responsive answer built in.
 *
 * Every cell carries its own header in `data-label`. Below the breakpoint the
 * stylesheet turns the rows into stacked blocks and prints that label in front
 * of the value; without it the stacked form is a column of numbers with nothing
 * saying which is which. Putting it on the cell rather than asking each screen
 * to do it is the difference between a rule and a habit.
 */
export function Table({ caption, columns, rows, empty }: TableProps): ReactNode {
  if (rows.length === 0) {
    return (
      <p className="text-muted text-small p-4">
        {empty ?? 'Nothing to show in this table.'}
      </p>
    );
  }
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full text-small">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cx(
                  'text-micro uppercase text-muted px-3 pb-2 edge border-border border-t-0 border-x-0',
                  column.numeric === true ? 'text-right' : 'text-left',
                )}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  data-label={column.header}
                  className={cx(
                    'px-3 py-2 edge border-border border-t-0 border-x-0 align-middle',
                    // An unbroken identifier is longer than the column it is in
                    // more often than not, and a table that widens for it takes
                    // the page sideways with it.
                    'break-all',
                    column.numeric === true ? 'text-right tabular-nums' : 'text-left',
                    column.identifier === true ? 'font-mono' : '',
                  )}
                >
                  {row[column.key] ?? ''}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export interface DataListItem {
  readonly term: string;
  readonly value: string;
  readonly identifier?: boolean;
}

export interface DataListProps {
  readonly items: readonly DataListItem[];
  readonly empty?: string;
}

/** Name and value pairs, as a description list so the association survives. */
export function DataList({ items, empty }: DataListProps): ReactNode {
  if (items.length === 0) {
    return <p className="text-muted text-small">{empty ?? 'Nothing was recorded.'}</p>;
  }
  return (
    <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3">
      {items.map((item) => (
        <div key={item.term} className="contents">
          <dt className="text-meta text-muted">{item.term}</dt>
          <dd
            className={cx(
              'text-small sm:col-span-2',
              item.identifier === true ? 'font-mono' : '',
            )}
          >
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export interface TimelineEvent {
  readonly id: string;
  readonly kind: string;
  readonly actor: string;
  readonly at: string;
  readonly summary: string;
  readonly sideEffect?: boolean;
}

export interface TimelineProps {
  readonly events: readonly TimelineEvent[];
  readonly empty?: string;
}

/**
 * What happened, in order.
 *
 * A side effect is stated in the header line rather than left in the payload,
 * because "this changed something" is the single most important fact about an
 * event and nobody finds it by reading JSON.
 */
export function Timeline({ events, empty }: TimelineProps): ReactNode {
  if (events.length === 0) {
    return (
      <p className="text-muted text-small">{empty ?? 'Nothing has happened yet.'}</p>
    );
  }
  return (
    <ol className="flex flex-col gap-3">
      {events.map((event) => (
        <li key={event.id} className="flex gap-3">
          <span className="text-meta text-muted tabular-nums w-5 shrink-0">
            {event.at}
          </span>
          <div className="min-w-0 flex flex-col gap-1">
            <span className="flex items-center gap-2 text-meta text-muted">
              <Badge status={event.kind} />
              {event.actor}
              {event.sideEffect === true ? (
                <span className="text-warning">side effect</span>
              ) : null}
            </span>
            <span className="text-small">{event.summary}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Bound `content` to the payload line bound, and say what was bounded. */
function bounded(content: string): { text: string; total: number; shown: number } {
  const lines = content.split('\n');
  if (lines.length <= PAYLOAD_LINE_BOUND) {
    return { text: content, total: lines.length, shown: lines.length };
  }
  return {
    text: lines.slice(0, PAYLOAD_LINE_BOUND).join('\n'),
    total: lines.length,
    shown: PAYLOAD_LINE_BOUND,
  };
}

export interface CodeBlockProps {
  readonly label: string;
  readonly content: string;
}

/**
 * A payload, bounded rather than truncated.
 *
 * The difference matters: a truncation is silent and a bound says what it
 * bounded and by how much, so a reader knows there is more and knows how much
 * more. A region rather than a `pre` on its own, because a scrollable area that
 * a keyboard cannot reach is a payload some readers cannot read.
 */
export function CodeBlock({ label, content }: CodeBlockProps): ReactNode {
  const id = useId();
  const { text, total, shown } = bounded(content);
  return (
    <div>
      <span id={id} className="sr-only">
        {label}
      </span>
      <pre
        role="region"
        aria-labelledby={id}
        tabIndex={0}
        className="p-3 rounded-2 edge border-border bg-sunken font-mono text-meta overflow-auto whitespace-pre-wrap"
      >
        {text}
      </pre>
      {shown < total ? (
        <p data-testid="bounded" className="text-meta text-muted mt-1">
          {total} lines in the payload; showing the first {shown}.
        </p>
      ) : null}
    </div>
  );
}

export interface DiffViewProps {
  readonly label: string;
  readonly before: string;
  readonly after: string;
}

type Change = 'added' | 'removed' | 'unchanged';

/** The lines of a diff, each marked with what happened to it. */
function diffLines(before: string, after: string): { change: Change; text: string }[] {
  const left = before.split('\n');
  const right = after.split('\n');
  const lines: { change: Change; text: string }[] = [];
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const was = left[index];
    const now = right[index];
    if (was === now) {
      if (was !== undefined) lines.push({ change: 'unchanged', text: was });
      continue;
    }
    if (was !== undefined) lines.push({ change: 'removed', text: was });
    if (now !== undefined) lines.push({ change: 'added', text: now });
  }
  return lines;
}

const CHANGE_SKIN: Readonly<Record<Change, string>> = {
  added: 'bg-success-bg text-success',
  removed: 'bg-danger-bg text-danger',
  unchanged: 'text-muted',
};

/**
 * Two documents, side by side in one column.
 *
 * The change is on the row as an attribute and in a sign in front of the line,
 * so it is carried by position and by character as well as by colour. Two
 * documents that are the same say so, rather than rendering an empty table that
 * looks like a failure to load.
 */
export function DiffView({ label, before, after }: DiffViewProps): ReactNode {
  const lines = diffLines(before, after);
  const changed = lines.filter((line) => line.change !== 'unchanged');
  if (changed.length === 0) {
    return (
      <p className="text-muted text-small">No difference between the two documents.</p>
    );
  }
  const shown = lines.slice(0, PAYLOAD_LINE_BOUND);
  return (
    <div>
      <table className="w-full font-mono text-meta">
        <caption className="sr-only">{label}</caption>
        <tbody>
          {shown.map((line, index) => (
            <tr
              key={`${String(index)}-${line.text}`}
              data-change={line.change}
              className={CHANGE_SKIN[line.change]}
            >
              <td className="px-2 select-none" aria-hidden="true">
                {line.change === 'added' ? '+' : line.change === 'removed' ? '-' : ' '}
              </td>
              <td className="px-2 break-all">{line.text}</td>
              <td className="sr-only">{line.change}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {shown.length < lines.length ? (
        <p data-testid="bounded" className="text-meta text-muted mt-1">
          {lines.length} lines in the difference; showing the first {shown.length}.
        </p>
      ) : null}
    </div>
  );
}
