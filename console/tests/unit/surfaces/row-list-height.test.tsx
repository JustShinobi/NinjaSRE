import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RowList } from '@/surfaces/rows';
import { ROW_HEIGHT } from '@/surfaces/window';

/**
 * The list is windowed, so it reserves a viewport and draws only the rows
 * inside it. The viewport was a constant — fifteen rows' worth — whatever the
 * list held, so a knowledge screen with three documents reserved twelve rows of
 * nothing beneath them, and a memory screen with five reserved ten.
 *
 * Dead space that large reads as a screen that failed to finish loading, which
 * is the opposite of what these screens are saying: they are complete and the
 * estate is small.
 *
 * The window's arithmetic is unaffected. It needs a viewport to divide by, and
 * that is still the same number; what changes is the height the element claims
 * on the page, which never needs to exceed what is in it.
 */

const LABELS = {
  caption: 'Documents',
  open: 'Open',
  sortedAscending: 'sorted ascending',
  sortedDescending: 'sorted descending',
  empty: 'Nothing here',
};

const STATE = { filters: {}, sort: '', descending: false, selection: null, page: 0 };

function renderRows(count: number) {
  return render(
    <RowList
      path="/knowledge"
      state={STATE}
      filters={[]}
      labels={LABELS}
      columns={[{ key: 'title', header: 'Document' }]}
      rows={Array.from({ length: count }, (_unused, index) => ({
        id: `doc-${String(index)}`,
        href: `/knowledge?selected=doc-${String(index)}`,
        cells: [{ kind: 'text' as const, text: `Document ${String(index)}` }],
      }))}
    />,
  );
}

function sizing(): { block: string; max: string } {
  const style = screen.getByTestId('row-list').style;
  return { block: style.blockSize, max: style.maxBlockSize };
}

describe('a short list claims only the height it needs', () => {
  it('is capped rather than fixed, so a short list sizes to what it holds', () => {
    // A cap rather than an arithmetic height: the element then needs no opinion
    // about how tall a header is, and gets the right answer when that changes.
    renderRows(3);

    expect(sizing().block).toBe('');
    expect(sizing().max).toBe(`${String(15 * ROW_HEIGHT)}px`);
  });

  it('still stops at the window once the list is longer than it', () => {
    // The window is what keeps a thousand-row estate cheap to draw; a list past
    // the viewport must keep scrolling rather than growing without bound.
    renderRows(200);

    expect(sizing().max).toBe(`${String(15 * ROW_HEIGHT)}px`);
  });

  it('reserves nothing at all when there is nothing to list', () => {
    renderRows(0);

    expect(sizing().block).toBe('');
  });

  it('draws every row of a short list rather than windowing it away', () => {
    renderRows(3);

    expect(screen.getByTestId('row-list').dataset.total).toBe('3');
    expect(screen.getByText('Document 2')).toBeTruthy();
  });
});
