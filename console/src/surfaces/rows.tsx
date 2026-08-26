'use client';

import type { ReactNode } from 'react';
import { useEffect, useRef, useState } from 'react';

import { ProgressBar } from '@/components/feedback';
import { Badge } from '@/components/status';
import { cx } from '@/design/cx';
import type { ColumnWidth } from '@/design/tokens';
import { ROW_HEIGHT, windowFor } from './window';
import { hrefFor, withSort, type FilterName, type ViewState } from './url-state';

/**
 * The one long list in this console, and every screen that has one uses it.
 *
 * Three things are load-bearing and none of them is the scrolling.
 *
 * **A row is a link.** The whole row, not a cell in it — a list whose only way
 * into a subject is a word in the second column is a list people click three
 * times to open one thing.
 *
 * **A sort is a navigation.** The header is an anchor carrying the address the
 * sorted view has, so sorting survives a reload, a share and a browser with no
 * JavaScript, and the URL requirement is satisfied by construction rather than
 * by remembering to push after every click.
 *
 * **Every row is the same height.** That is what lets the window be arithmetic
 * rather than measurement; see `window.ts`. A cell with more to say than fits
 * gets a bound and a way to open it, not a taller row.
 */

export const CELL_KINDS = [
  'text',
  'identifier',
  'numeric',
  'status',
  'meter',
  'muted',
] as const;

export type CellKind = (typeof CELL_KINDS)[number];

export interface Cell {
  readonly kind: CellKind;
  /** What is written in the cell. A meter shows this beside the bar. */
  readonly text: string;
  /** The complete value, shown when the cell's visible text is truncated. */
  readonly title?: string;
  /** Per cent, for a meter. Ignored by every other kind. */
  readonly value?: number;
  /**
   * An explanation of a jargon word or a placeholder value, on hover and on
   * focus. Absent for an ordinary cell — a hint on every cell would teach a
   * reader to stop reading them, which is the same lesson a column that never
   * has a value teaches.
   */
  readonly hint?: string | undefined;
  /**
   * Where this cell's own value is declared, when that is a place. Distinct
   * from the row's own link on the first cell: a placeholder value like
   * "unplaced" is not an invitation to open the resource, it is an invitation
   * to go and declare the fact that is missing.
   */
  readonly href?: string | undefined;
}

export interface ListRow {
  readonly id: string;
  /** Where the row goes. Every row goes somewhere; a row that does not is a fact. */
  readonly href: string;
  /** One per column, in the columns' order. */
  readonly cells: readonly Cell[];
}

export interface RowColumn {
  readonly key: string;
  readonly header: string;
  /** Whether this column can be sorted by. A column that cannot says nothing. */
  readonly sortable?: boolean;
  readonly numeric?: boolean;
  /**
   * Which of the declared column widths this column takes, by what it holds.
   * Omitted for the column that carries the row's subject, which then takes
   * whatever is left.
   *
   * The table lays out fixed, so without this every column gets an equal
   * share of the width. On a Full HD screen that gave a status badge and a
   * duration four hundred pixels each and truncated the one column that says
   * what the row is about — the reader's only way of telling two rows apart,
   * clipped to make room for eight characters of "COMPLETED".
   */
  readonly width?: ColumnWidth;
}

/**
 * The sort control's accessible name, with the column it is about in it.
 *
 * A reader hears the heading and this together, and "Started sort, smallest
 * first" is neither a sentence nor a statement about any particular column —
 * the defect three screens reported independently. The label carries a
 * `{column}` placeholder and it is filled here rather than in the catalogue
 * lookup, because the lookup happens once per screen and there is one of these
 * per column.
 *
 * A label with no placeholder is returned unchanged, which is what keeps a test
 * double that passes "ascending" working.
 */
export function sortAction(label: string, column: string): string {
  return label.replace('{column}', column);
}

export interface RowListLabels {
  readonly caption: string;
  /** Names the sort control, e.g. "Sort by {column}". Interpolated by the caller. */
  readonly sortedAscending: string;
  readonly sortedDescending: string;
  /** What one row's link is called, for a reader who hears only the link. */
  readonly open: string;
}

export interface RowListProps {
  readonly columns: readonly RowColumn[];
  readonly rows: readonly ListRow[];
  readonly labels: RowListLabels;
  /** The address the sort links are built against. */
  readonly path: string;
  readonly state: ViewState;
  readonly filters: readonly FilterName[];
  /** How tall the scrolling region is. Fixed, so the window is arithmetic. */
  readonly height?: number;
}

/**
 * The utility each declared column width is reached by.
 *
 * Written out rather than composed from the name, because the class names have
 * to survive a static scan of this file — a class built at runtime is a class
 * the stylesheet never generates, and the column silently falls back to an
 * equal share of the table.
 */
const COLUMN_CLASS: Readonly<Record<ColumnWidth, string>> = {
  word: 'w-column-word',
  badge: 'w-column-badge',
  identifier: 'w-column-identifier',
  instant: 'w-column-instant',
  measure: 'w-column-measure',
};

function cellClass(kind: CellKind): string {
  return cx(
    'px-3 truncate',
    kind === 'numeric' ? 'text-right tabular-nums' : 'text-left',
    kind === 'identifier' ? 'font-mono' : '',
    kind === 'muted' ? 'text-muted' : '',
  );
}

function CellValue({ cell }: { readonly cell: Cell }): ReactNode {
  if (cell.kind === 'status') {
    return <Badge status={cell.text} />;
  }
  if (cell.kind === 'meter') {
    return <ProgressBar label={cell.text} value={cell.value ?? 0} />;
  }
  return <>{cell.text}</>;
}

function CellBody({ cell }: { readonly cell: Cell }): ReactNode {
  if (cell.href !== undefined) {
    return (
      <a
        href={cell.href}
        title={cell.hint}
        className="underline-offset-2 hover:underline"
      >
        <CellValue cell={cell} />
      </a>
    );
  }
  if (cell.hint !== undefined) {
    return (
      <span title={cell.hint}>
        <CellValue cell={cell} />
      </span>
    );
  }
  return <CellValue cell={cell} />;
}

/** A long list, windowed, sortable by address, with every row a link. */
export function RowList({
  columns,
  rows,
  labels,
  path,
  state,
  filters,
  height = 15 * ROW_HEIGHT,
}: RowListProps): ReactNode {
  const [scrollTop, setScrollTop] = useState(0);
  const [drawnState, setDrawnState] = useState(state);
  const region = useRef<HTMLDivElement | null>(null);

  // A view that arrived from an address rather than from a scroll starts at the
  // top of itself. Adjusted during the render that notices the change rather
  // than in an effect afterwards: an effect would draw the new rows at the old
  // offset for one frame, which is a list that appears to jump when a filter is
  // applied.
  if (drawnState !== state) {
    setDrawnState(state);
    setScrollTop(0);
  }

  useEffect(() => {
    // The element's own scroll position is the browser's state rather than
    // React's, which is exactly what an effect is for.
    if (region.current !== null) {
      region.current.scrollTop = 0;
    }
  }, [state]);

  const window = windowFor({
    total: rows.length,
    rowHeight: ROW_HEIGHT,
    viewport: height,
    scrollTop,
  });
  const drawn = rows.slice(window.first, window.first + window.count);

  return (
    <div
      ref={region}
      data-testid="row-list"
      data-total={rows.length}
      className="w-full overflow-auto"
      // Capped rather than fixed. A fixed viewport reserved fifteen rows' worth
      // of page whatever the list held, so three documents sat above twelve rows
      // of nothing — dead space that reads as a screen which failed to finish
      // loading, when what it is saying is that the estate is small.
      //
      // A cap also spares this element an opinion about how tall its own header
      // is, which is the number an arithmetic height would have to guess and
      // would get wrong the next time the header changed.
      style={{ maxBlockSize: `${String(height)}px` }}
      onScroll={(event) => {
        setScrollTop(event.currentTarget.scrollTop);
      }}
    >
      <table className="w-full text-small table-fixed">
        <caption className="sr-only">{labels.caption}</caption>
        {/* A column that declares a width gets it; the rest divide the
            remainder. Declaring every column but the subject's is how the
            subject ends up with the slack instead of an equal sixth of it. */}
        <colgroup>
          {columns.map((column) => (
            <col
              key={column.key}
              data-column={column.key}
              className={
                column.width === undefined ? undefined : COLUMN_CLASS[column.width]
              }
            />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map((column) => {
              const sorted = state.sort === column.key;
              const next = withSort(state, column.key);
              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={
                    sorted ? (state.descending ? 'descending' : 'ascending') : 'none'
                  }
                  className={cx(
                    'text-micro uppercase text-muted edge border-border border-t-0 border-x-0',
                    // A sortable heading moves the cell's padding onto its own
                    // link, so the padded area is the target rather than the
                    // glyphs. An ordinary heading keeps the spacing every other
                    // cell has.
                    column.sortable === true ? 'p-0' : 'px-3 pb-2',
                    column.numeric === true ? 'text-right' : 'text-left',
                  )}
                >
                  {column.sortable === true ? (
                    <a
                      href={hrefFor(path, next, filters)}
                      data-testid="sort"
                      data-column={column.key}
                      className={cx(
                        'flex items-center gap-1 underline-offset-2 hover:underline',
                        // The heading is set in the smallest type on the screen,
                        // whose line box alone is about half of what WCAG 2.2
                        // asks a target to be.
                        'px-3 py-2 min-h-6',
                        column.numeric === true ? 'justify-end' : 'justify-start',
                      )}
                    >
                      {column.header}
                      {/* Which way this column is sorted, for a reader who has
                          the colour and not the announcement. `aria-sort` on
                          the header above carries the same fact for a reader
                          who has the announcement and not the glyph. */}
                      {sorted ? (
                        <span aria-hidden="true" className="text-accent">
                          {state.descending ? '↓' : '↑'}
                        </span>
                      ) : null}
                      <span className="sr-only">
                        {sortAction(
                          next.descending
                            ? labels.sortedDescending
                            : labels.sortedAscending,
                          column.header,
                        )}
                      </span>
                    </a>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {window.padTop > 0 ? (
            <tr aria-hidden="true" data-testid="pad-top">
              <td
                colSpan={columns.length}
                style={{ blockSize: `${String(window.padTop)}px` }}
              />
            </tr>
          ) : null}
          {drawn.map((row) => (
            <tr
              key={row.id}
              data-testid="row"
              data-row={row.id}
              className="motion-hover hover:bg-hover"
              style={{ blockSize: `${String(ROW_HEIGHT)}px` }}
            >
              {row.cells.map((cell, index) => {
                const column = columns[index];
                return (
                  <td
                    key={column?.key ?? String(index)}
                    data-label={column?.header ?? ''}
                    className={cx(
                      cellClass(cell.kind),
                      'edge border-border border-t-0 border-x-0 align-middle',
                    )}
                  >
                    {index === 0 ? (
                      <a href={row.href} className="flex items-center gap-2 min-w-0">
                        <span className="truncate" title={cell.title}>
                          <CellBody cell={cell} />
                        </span>
                        <span className="sr-only">{labels.open}</span>
                      </a>
                    ) : (
                      <CellBody cell={cell} />
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
          {window.padBottom > 0 ? (
            <tr aria-hidden="true" data-testid="pad-bottom">
              <td
                colSpan={columns.length}
                style={{ blockSize: `${String(window.padBottom)}px` }}
              />
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
