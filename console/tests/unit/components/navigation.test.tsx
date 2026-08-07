import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Avatar, Breadcrumb, Pagination, Tabs } from '@/components/navigation';

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

describe('Breadcrumb', () => {
  it('is a navigation landmark with the current page marked', () => {
    render(
      <Breadcrumb
        trail={[
          { href: '/', label: 'Operate' },
          { href: '/incidents', label: 'Incidents' },
          { label: 'Quorum margin is zero' },
        ]}
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
      <Breadcrumb trail={[{ href: '/', label: 'Operate' }, { label: 'Incidents' }]} />,
    );
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });
});

describe('Pagination', () => {
  it('says where the reader is, in words', () => {
    render(<Pagination page={2} pages={7} onPage={vi.fn()} />);
    expect(screen.getByText(/page 2 of 7/i)).toBeInTheDocument();
  });

  it('disables the edge it is already at rather than hiding it', () => {
    render(<Pagination page={1} pages={7} onPage={vi.fn()} />);
    // Hiding it would move the next control under the pointer as the reader
    // arrives at the first page, which is the shift the design forbids.
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /next/i })).toBeEnabled();
  });

  it('turns the page from the keyboard', async () => {
    const turned = vi.fn();
    render(<Pagination page={2} pages={7} onPage={turned} />);

    await userEvent.tab();
    await userEvent.keyboard('{Enter}');
    expect(turned).toHaveBeenCalledWith(1);
  });
});

describe('Avatar', () => {
  it('says who it is, rather than showing initials to a screen reader', () => {
    render(<Avatar name="Priya Raman" />);
    expect(screen.getByRole('img', { name: 'Priya Raman' })).toHaveTextContent('PR');
  });

  it('survives a single-word name and an empty one', () => {
    const { rerender } = render(<Avatar name="runner" />);
    expect(screen.getByRole('img', { name: 'runner' })).toHaveTextContent('R');

    rerender(<Avatar name="" />);
    expect(screen.getByRole('img', { name: /unknown/i })).toBeInTheDocument();
  });
});
