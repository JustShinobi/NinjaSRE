import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  AttentionBlock,
  ATTENTION_ROWS_SHOWN,
  type AttentionRow,
} from '@/surfaces/attention';

/**
 * The band is bounded, like every other list on this console.
 *
 * The pattern this design settles is that a list whose length nothing bounds
 * is grouped or paged, never dumped — and the band was the worst offender,
 * because the rows it dumps are the ones it most wants read. Sixteen of them
 * is a page nobody reads to the end of, which costs exactly the rows at the
 * bottom: the oldest, which is to say the ones that have been waiting longest.
 */
describe('how many rows the band shows', () => {
  function rows(count: number): AttentionRow[] {
    return Array.from({ length: count }, (_, index) => ({
      id: `item-${String(index)}`,
      kind: 'approval',
      title: `Waiting item ${String(index)}`,
      detail: 'awaiting decision',
      href: `/decisions?selected=item-${String(index)}`,
      since: '1h ago',
    }));
  }

  function band(count: number): void {
    render(
      <AttentionBlock
        heading={`${String(count)} items need you`}
        oldest="Waiting longest: 2h"
        rows={rows(count)}
        openLabel="Open"
        moreLabel={(over) => `and ${String(over)} more waiting`}
        moreHref="/decisions"
      />,
    );
  }

  it('shows every row while they still fit', () => {
    band(5);

    expect(screen.getAllByTestId('attention-row')).toHaveLength(5);
    expect(screen.queryByTestId('attention-more')).toBeNull();
  });

  it('stops at the cap and says how many it did not draw', () => {
    band(16);

    expect(screen.getAllByTestId('attention-row')).toHaveLength(ATTENTION_ROWS_SHOWN);
    expect(screen.getByTestId('attention-more')).toHaveTextContent(
      `and ${String(16 - ATTENTION_ROWS_SHOWN)} more waiting`,
    );
  });

  it('keeps the count in the heading honest about the whole queue', () => {
    // The cap is a drawing decision. A band that also quietly reduced its own
    // count would be hiding the backlog rather than bounding the page.
    band(16);

    expect(screen.getByText('16 items need you')).toBeInTheDocument();
  });

  it('reaches the rest in one click', () => {
    band(16);

    expect(screen.getByTestId('attention-more').getAttribute('href')).toBe(
      '/decisions',
    );
  });
});
