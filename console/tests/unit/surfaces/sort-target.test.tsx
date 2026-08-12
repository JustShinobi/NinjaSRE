import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RowList } from '@/surfaces/rows';

/**
 * A sort control is a link wrapped around a column heading, and the heading is
 * set in the smallest type on the screen. Left as an inline element it is a
 * target about twelve pixels tall — comfortably under the twenty-four WCAG 2.2
 * asks for, and the padding that would have made it bigger sits on the cell
 * around it rather than on the link itself.
 *
 * The fix is to move the cell's padding onto the link, so the whole padded area
 * is the target rather than just the glyphs. That is why this test asserts on
 * where the padding lives: putting it back on the `th` is exactly the change
 * that would silently shrink the target again.
 */

const LABELS = {
  caption: 'Resources',
  open: 'Open',
  sortedAscending: 'sorted ascending',
  sortedDescending: 'sorted descending',
  empty: 'Nothing here',
};

const STATE = { filters: {}, sort: '', descending: false, selection: null, page: 0 };

function renderList() {
  return render(
    <RowList
      path="/resources"
      state={STATE}
      filters={[]}
      labels={LABELS}
      columns={[
        { key: 'display_name', header: 'Resource', sortable: true },
        { key: 'parent_name', header: 'Parent' },
      ]}
      rows={[
        {
          id: 'res-a',
          href: '/resources?selected=res-a',
          cells: [
            { kind: 'text', text: 'ct100' },
            { kind: 'muted', text: 'pve01' },
          ],
        },
      ]}
    />,
  );
}

describe('a sortable column heading is a target somebody can hit', () => {
  it('carries its own padding, so the target is the cell and not the glyphs', () => {
    renderList();

    const link = screen.getByTestId('sort');

    expect(link.className).toContain('px-3');
    expect(link.className).toContain('py-2');
  });

  it('declares a minimum height rather than inheriting the type’s', () => {
    // The heading is set in the smallest type on the screen; its line box alone
    // is about half the minimum.
    renderList();

    expect(screen.getByTestId('sort').className).toMatch(/min-h-\d/);
  });

  it('does not leave the padding on the cell, where the link cannot use it', () => {
    renderList();

    const cell = screen.getByTestId('sort').closest('th');

    expect(cell?.className).not.toContain('px-3');
  });

  it('leaves a column nobody can sort padded as it was', () => {
    // Only the sortable heading moves its padding inward; an ordinary one has
    // no link to grow and should keep the cell spacing every other cell has.
    renderList();

    const plain = screen.getByText('Parent').closest('th');

    expect(plain?.className).toContain('px-3');
  });
});
