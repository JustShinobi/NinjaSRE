import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  Avatar,
  Breadcrumb,
  Pagination,
  TabLinks,
  Tabs,
} from '@/components/navigation';

/**
 * The patterns with a keyboard contract, tested by pressing keys.
 *
 * Asserting that a tab list has `role="tablist"` proves the attribute was
 * typed. Pressing the right arrow and finding the next tab focused proves the
 * pattern works, which is what a keyboard user has.
 */

const TABS = [
  { id: 'transcript', label: 'Transcript' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'decisions', label: 'Decisions' },
];

describe('Tabs', () => {
  it('exposes the roles and the selected state the pattern requires', () => {
    render(
      <Tabs
        tabs={TABS}
        selected="transcript"
        onSelect={vi.fn()}
        label="Investigation"
      />,
    );

    expect(screen.getByRole('tablist', { name: 'Investigation' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Transcript' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby');
  });

  it('moves along the row with the arrow keys and wraps at the end', async () => {
    const selected = vi.fn();
    render(
      <Tabs
        tabs={TABS}
        selected="transcript"
        onSelect={selected}
        label="Investigation"
      />,
    );

    await userEvent.tab();
    await userEvent.keyboard('{ArrowRight}');
    expect(selected).toHaveBeenLastCalledWith('evidence');

    await userEvent.keyboard('{ArrowLeft}');
    expect(selected).toHaveBeenLastCalledWith('decisions');
  });

  it('puts only the selected tab in the tab order', () => {
    render(
      <Tabs tabs={TABS} selected="evidence" onSelect={vi.fn()} label="Investigation" />,
    );

    expect(screen.getByRole('tab', { name: 'Evidence' })).toHaveAttribute(
      'tabindex',
      '0',
    );
    expect(screen.getByRole('tab', { name: 'Transcript' })).toHaveAttribute(
      'tabindex',
      '-1',
    );
  });
});

describe('the two tab rows, which a reader cannot tell apart', () => {
  /**
   * `Tabs` and `TabLinks` are deliberately two components with two different
   * keyboard contracts, and the module says so. What they are not is two
   * appearances: a reader moving between a screen whose section is in its
   * address and one whose section is not should see the same row of tabs.
   *
   * They were not. `TabLinks` gives each tab `edge border-t-0 border-x-0`, so
   * the selected one paints its `border-accent` as an underline. `Tabs` had
   * the colour and no width to paint it on, so its selected tab was marked by
   * a change of text colour alone — no rule under it at all. Which meant the
   * accent underline, the console's mark for "you are here", appeared on some
   * tab rows and not others depending on a distinction the reader has no way
   * to see.
   */
  const LINKS = TABS.map((tab) => ({ ...tab, href: `?section=${tab.id}` }));

  it('draws the selected tab with an underline in both of them', () => {
    const { unmount } = render(
      <Tabs tabs={TABS} selected="evidence" onSelect={vi.fn()} label="Investigation" />,
    );
    const owned = [...screen.getByRole('tab', { name: 'Evidence' }).classList];
    unmount();

    render(<TabLinks tabs={LINKS} selected="evidence" label="Investigation" />);
    const addressed = [...screen.getByRole('link', { name: 'Evidence' }).classList];

    // The underline is a border width plus the two removals that leave only
    // the bottom edge. Whatever paints it, both rows have to have it.
    for (const utility of ['edge', 'border-t-0', 'border-x-0', 'border-accent']) {
      expect(addressed, `${utility} on TabLinks`).toContain(utility);
      expect(owned, `${utility} on Tabs`).toContain(utility);
    }
  });

  it('gives an unselected tab the same quiet treatment in both of them', () => {
    const { unmount } = render(
      <Tabs tabs={TABS} selected="evidence" onSelect={vi.fn()} label="Investigation" />,
    );
    const owned = [...screen.getByRole('tab', { name: 'Transcript' }).classList];
    unmount();

    render(<TabLinks tabs={LINKS} selected="evidence" label="Investigation" />);
    const addressed = [...screen.getByRole('link', { name: 'Transcript' }).classList];

    for (const utility of ['text-muted', 'border-transparent']) {
      expect(addressed, `${utility} on TabLinks`).toContain(utility);
      expect(owned, `${utility} on Tabs`).toContain(utility);
    }
  });
});

describe('Breadcrumb', () => {
  it('is a navigation landmark with the current page marked', () => {
    render(
      <Breadcrumb
        trail={[
          { href: '/', label: 'Operate' },
          { href: '/incidents', label: 'Incidents' },
          { label: 'Quorum margin is zero' },
        ]}
        label="Breadcrumb"
      />,
    );

    expect(screen.getByRole('navigation', { name: /breadcrumb/i })).toBeInTheDocument();
    expect(screen.getByText('Quorum margin is zero')).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('does not make the current page a link to itself', () => {
    render(
      <Breadcrumb
        label="Breadcrumb"
        trail={[{ href: '/', label: 'Operate' }, { label: 'Incidents' }]}
      />,
    );
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });
});

/**
 * The strings a real screen takes from the message catalogue. Written out here
 * because a component test states the values it is asserting against — that is
 * the opposite of hard-coding one, and it is what keeps the assertion honest.
 */
function labelsFor(page: number): {
  landmark: string;
  previous: string;
  next: string;
  position: string;
} {
  return {
    landmark: 'Pagination',
    previous: 'Previous',
    next: 'Next',
    position: `Page ${String(page)} of 7`,
  };
}

describe('Pagination', () => {
  it('says where the reader is, in words', () => {
    render(<Pagination page={2} pages={7} onPage={vi.fn()} labels={labelsFor(2)} />);
    expect(screen.getByText(/page 2 of 7/i)).toBeInTheDocument();
  });

  it('disables the edge it is already at rather than hiding it', () => {
    render(<Pagination page={1} pages={7} onPage={vi.fn()} labels={labelsFor(1)} />);
    // Hiding it would move the next control under the pointer as the reader
    // arrives at the first page, which is the shift the design forbids.
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /next/i })).toBeEnabled();
  });

  it('turns the page from the keyboard', async () => {
    const turned = vi.fn();
    render(<Pagination page={2} pages={7} onPage={turned} labels={labelsFor(2)} />);

    await userEvent.tab();
    await userEvent.keyboard('{Enter}');
    expect(turned).toHaveBeenCalledWith(1);
  });
});

describe('Avatar', () => {
  it('says who it is, rather than showing initials to a screen reader', () => {
    render(<Avatar name="Priya Raman" unknownLabel="Unknown person" />);
    expect(screen.getByRole('img', { name: 'Priya Raman' })).toHaveTextContent('PR');
  });

  it('survives a single-word name and an empty one', () => {
    const { rerender } = render(<Avatar name="runner" unknownLabel="Unknown person" />);
    expect(screen.getByRole('img', { name: 'runner' })).toHaveTextContent('R');

    rerender(<Avatar name="" unknownLabel="Unknown person" />);
    expect(screen.getByRole('img', { name: /unknown/i })).toBeInTheDocument();
  });
});
