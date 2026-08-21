import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RowList, type ListRow, type RowColumn } from '@/surfaces/rows';
import { DEFAULT_VIEW_STATE, SORT_PARAM } from '@/surfaces/url-state';
import { ROW_HEIGHT } from '@/surfaces/window';

/**
 * Ten thousand rows, and the three properties that make the list usable.
 *
 * The benchmark this file carries is a *scaling* assertion rather than a
 * stopwatch: a wall-clock number measured on a loaded CI runner is a flake
 * waiting for a busy afternoon, and the claim worth making is stronger anyway —
 * that the number of rows in the document does not depend on how many there are.
 */

const COLUMNS: readonly RowColumn[] = [
  { key: 'run', header: 'Run', sortable: true },
  { key: 'status', header: 'Status' },
  { key: 'cost', header: 'Cost', numeric: true, sortable: true },
];

function rows(count: number): readonly ListRow[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `run-${String(index)}`,
    href: `/runs/run-${String(index)}`,
    cells: [
      { kind: 'identifier' as const, text: `run-${String(index)}` },
      { kind: 'status' as const, text: 'succeeded' },
      { kind: 'numeric' as const, text: '0.12' },
    ],
  }));
}

const LABELS = {
  caption: 'Every run this deployment has recorded',
  sortedAscending: 'sorted ascending',
  sortedDescending: 'sorted descending',
  open: 'Open this run',
} as const;

function renderList(count: number): ReturnType<typeof render> {
  return render(
    <RowList
      columns={COLUMNS}
      rows={rows(count)}
      labels={LABELS}
      path="/runs"
      state={DEFAULT_VIEW_STATE}
      filters={['status']}
    />,
  );
}

describe('a list of ten thousand rows', () => {
  it('puts the same number of rows in the document as a list of a hundred', () => {
    const hundred = renderList(100);
    const drawn = screen.getAllByTestId('row').length;
    hundred.unmount();

    renderList(10_000);
    expect(screen.getAllByTestId('row')).toHaveLength(drawn);
  });

  it('says how many there are even though it drew a fraction of them', () => {
    renderList(10_000);

    expect(screen.getByTestId('row-list')).toHaveAttribute('data-total', '10000');
  });

  it('reserves the height of the rows it did not draw', () => {
    renderList(10_000);

    const pad = screen.getByTestId('pad-bottom').firstElementChild;
    const reserved = Number.parseInt(
      (pad as HTMLElement).style.blockSize.replace('px', ''),
      10,
    );
    const drawn = screen.getAllByTestId('row').length;
    expect(reserved).toBe((10_000 - drawn) * ROW_HEIGHT);
  });
});

describe('what a row and a header are', () => {
  it('makes the whole first cell a link into the subject', () => {
    renderList(4);

    expect(screen.getByRole('link', { name: /run-0/ })).toHaveAttribute(
      'href',
      '/runs/run-0',
    );
  });

  it('sorts by navigating, so the sorted view has an address', () => {
    renderList(4);

    const sort = screen.getAllByTestId('sort')[0];
    expect(sort).toHaveAttribute('href', `/runs?${SORT_PARAM}=run`);
  });

  it('says which column is sorted, to anything that reads a table', () => {
    render(
      <RowList
        columns={COLUMNS}
        rows={rows(4)}
        labels={LABELS}
        path="/runs"
        state={{ ...DEFAULT_VIEW_STATE, sort: 'cost', descending: true }}
        filters={['status']}
      />,
    );

    const headers = screen.getAllByRole('columnheader');
    expect(headers.map((header) => header.getAttribute('aria-sort'))).toEqual([
      'none',
      'none',
      'descending',
    ]);
  });

  it('carries each cell’s header on the cell, for the stacked form', () => {
    renderList(1);

    const cells = screen.getAllByRole('cell');
    expect(cells.map((cell) => cell.getAttribute('data-label'))).toEqual([
      'Run',
      'Status',
      'Cost',
    ]);
  });

  it('exposes the complete value as a tooltip when a cell is truncated', () => {
    render(
      <RowList
        columns={COLUMNS}
        rows={[
          {
            id: 'run-long',
            href: '/runs/run-long',
            cells: [
              {
                kind: 'text',
                text: 'A long subject…',
                title: 'A long subject that does not fit in the row',
              },
              { kind: 'status', text: 'succeeded' },
              { kind: 'numeric', text: '0.12' },
            ],
          },
        ]}
        labels={LABELS}
        path="/runs"
        state={DEFAULT_VIEW_STATE}
        filters={['status']}
      />,
    );

    expect(
      screen.getByTitle('A long subject that does not fit in the row'),
    ).toBeInTheDocument();
  });
});
