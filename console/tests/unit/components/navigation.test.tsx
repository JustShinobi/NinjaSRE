import type { ReactNode } from 'react';

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  Avatar,
  Breadcrumb,
  Pagination,
  SegmentedLinks,
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

/**
 * `next/link` stood in by an anchor that records it was the router's link,
 * and with which prefetch setting. A real `<a href>` and a router link render
 * the same element, so nothing in the DOM says which one a component used —
 * and the difference is the whole point of `TabLinks` using the router: a
 * plain anchor is a document navigation, which throws the shell away and
 * shows nothing at all while the next screen renders.
 */
vi.mock('next/link', () => ({
  default: ({
    href,
    prefetch,
    children,
    ...rest
  }: {
    readonly href: string;
    readonly prefetch?: boolean;
    readonly children: ReactNode;
  }) => (
    <a {...rest} href={href} data-router-link={String(prefetch)}>
      {children}
    </a>
  ),
}));

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

describe('TabLinks', () => {
  const LINKS = TABS.map((tab) => ({ ...tab, href: `?section=${tab.id}` }));

  it('follows a tab through the router, with prefetching off', () => {
    render(<TabLinks tabs={LINKS} selected="evidence" label="Investigation" />);

    // A router transition keeps the shell and shows the route's loading
    // state while the section renders; a plain anchor does neither. Prefetch
    // stays off, as it is on every link here: each tab is a full server
    // render against the deployment, and the tabs nobody opens must not
    // cost one.
    for (const tab of TABS) {
      const link = screen.getByRole('link', { name: tab.label });
      expect(link).toHaveAttribute('href', `?section=${tab.id}`);
      expect(link).toHaveAttribute('data-router-link', 'false');
    }
  });

  it('marks the selected tab as the current page', () => {
    render(<TabLinks tabs={LINKS} selected="evidence" label="Investigation" />);

    expect(screen.getByRole('link', { name: 'Evidence' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('link', { name: 'Transcript' })).not.toHaveAttribute(
      'aria-current',
    );
  });
});

describe('SegmentedLinks', () => {
  const OPTIONS = [
    { id: 'open', label: 'Open', href: '?state=open' },
    { id: 'resolved', label: 'Resolved', href: '?state=resolved' },
    { id: 'all', label: 'All', href: '?state=all' },
  ];

  it('follows a choice through the router, with prefetching off', () => {
    render(<SegmentedLinks options={OPTIONS} selected="open" label="State" />);

    // Same reasoning as the tab row: the address is the same either way, but
    // a plain anchor is a document navigation that throws the shell away and
    // repeats its reads for a change of filter. Prefetch stays off, because
    // every choice is a full server render against the deployment.
    for (const option of OPTIONS) {
      const link = screen.getByRole('link', { name: option.label });
      expect(link).toHaveAttribute('href', option.href);
      expect(link).toHaveAttribute('data-router-link', 'false');
    }
  });

  it('marks the selected choice as current', () => {
    render(<SegmentedLinks options={OPTIONS} selected="open" label="State" />);

    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute(
      'aria-current',
      'true',
    );
    expect(screen.getByRole('link', { name: 'All' })).not.toHaveAttribute(
      'aria-current',
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
