'use client';

import type { ReactNode } from 'react';
import { useEffect, useRef, useState } from 'react';

import { ProgressBar } from '@/components/feedback';
import { Badge } from '@/components/status';
import { cx } from '@/design/cx';
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
  /** Per cent, for a meter. Ignored by every other kind. */
  readonly value?: number;
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

function cellClass(kind: CellKind): string {
  return cx(
    'px-3 truncate',
    kind === 'numeric' ? 'text-right tabular-nums' : 'text-left',
    kind === 'identifier' ? 'font-mono' : '',
    kind === 'muted' ? 'text-muted' : '',
  );
}

function CellBody({ cell }: { readonly cell: Cell }): ReactNode {
  if (cell.kind === 'status') {
    return <Badge status={cell.text} />;
  }
  if (cell.kind === 'meter') {
    return <ProgressBar label={cell.text} value={cell.value ?? 0} />;
  }
  return <>{cell.text}</>;
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
      style={{ blockSize: `${String(height)}px` }}
      onScroll={(event) => {
        setScrollTop(event.currentTarget.scrollTop);
      }}
    >
      <table className="w-full text-small table-fixed">
        <caption className="sr-only">{labels.caption}</caption>
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
                    'text-micro uppercase text-muted px-3 pb-2 edge border-border border-t-0 border-x-0',
                    column.numeric === true ? 'text-right' : 'text-left',
                  )}
                >
                  {column.sortable === true ? (
                    <a
                      href={hrefFor(path, next, filters)}
                      data-testid="sort"
                      data-column={column.key}
                      className="inline-flex items-center gap-1 underline-offset-2 hover:underline"
                    >
                      {column.header}
                      <span className="sr-only">
                        {next.descending
                          ? labels.sortedDescending
                          : labels.sortedAscending}
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
              className="motion-hover hover:bg-sunken"
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
                        <span className="truncate">
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
