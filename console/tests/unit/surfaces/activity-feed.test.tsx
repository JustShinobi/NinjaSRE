import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  ActivityFeed,
  collapseFeed,
  type ActivityFeedEntry,
} from '@/surfaces/activity-feed';

/**
 * "Atividade ao vivo": each entry carries the shape of its own kind, and
 * consecutive firings of the same subject collapse into one row with a
 * count -- the exact defect the audit named (five rows for one recurring
 * cause, indistinguishable from five different problems).
 */

function entry(over: Partial<ActivityFeedEntry> = {}): ActivityFeedEntry {
  return {
    id: 'e-1',
    kind: 'incident',
    outcome: 'danger',
    title: 'DNSResolverProbeFailed',
    detail: '',
    href: '/incidents/inc-1',
    relative: '2 minutes ago',
    absolute: '31 Aug 2026, 09:00:00',
    iso: '2026-08-31T09:00:00.000Z',
    subjectKey: 'detector:dns:resource:adguard-primary',
    count: 1,
    kindLabel: '',
    duration: '',
    ...over,
  };
}

describe('collapseFeed', () => {
  it('folds five consecutive firings of the same subject into one entry with a count of five', () => {
    const five = Array.from({ length: 5 }, (_, index) =>
      entry({ id: `inc-${String(index)}` }),
    );
    const collapsed = collapseFeed(five);
    expect(collapsed).toHaveLength(1);
    expect(collapsed[0]?.count).toBe(5);
    // The surviving entry is the first one seen -- the newest, since callers
    // sort newest-first before collapsing.
    expect(collapsed[0]?.id).toBe('inc-0');
  });

  it('does not fold two different subjects, even when adjacent', () => {
    const collapsed = collapseFeed([
      entry({ id: 'a', subjectKey: 'detector:a:resource:one' }),
      entry({ id: 'b', subjectKey: 'detector:b:resource:two' }),
    ]);
    expect(collapsed).toHaveLength(2);
    expect(collapsed.map((item) => item.count)).toEqual([1, 1]);
  });

  it('does not fold two firings of the same subject that are not adjacent', () => {
    const collapsed = collapseFeed([
      entry({ id: 'a', subjectKey: 'detector:a:resource:one' }),
      entry({
        id: 'mid',
        kind: 'investigation',
        subjectKey: '',
        title: 'Investigation started',
      }),
      entry({ id: 'b', subjectKey: 'detector:a:resource:one' }),
    ]);
    expect(collapsed).toHaveLength(3);
  });

  it('never folds two kinds together, even sharing a subject key by coincidence', () => {
    const collapsed = collapseFeed([
      entry({ id: 'a', kind: 'incident', subjectKey: 'k' }),
      entry({ id: 'b', kind: 'resolution', subjectKey: 'k' }),
    ]);
    expect(collapsed).toHaveLength(2);
  });

  it('never folds entries with no subject key, whatever their kind', () => {
    const collapsed = collapseFeed([
      entry({
        id: 'a',
        kind: 'approval',
        subjectKey: '',
        title: 'Remediation proposed',
      }),
      entry({
        id: 'b',
        kind: 'approval',
        subjectKey: '',
        title: 'Remediation proposed',
      }),
    ]);
    expect(collapsed).toHaveLength(2);
  });
});

describe('ActivityFeed', () => {
  it('renders one entry per item, newest first, exactly as given', () => {
    render(
      <ActivityFeed locale="en" entries={[entry({ id: 'a' }), entry({ id: 'b' })]} />,
    );
    expect(screen.getAllByTestId('activity-feed-entry')).toHaveLength(2);
  });

  it("carries the kind on the entry's own attribute, for the acceptance suite to read", () => {
    render(
      <ActivityFeed
        locale="en"
        entries={[
          entry({ id: 'a', kind: 'investigation' }),
          entry({ id: 'b', kind: 'resolution' }),
          entry({ id: 'c', kind: 'incident' }),
          entry({ id: 'd', kind: 'approval' }),
        ]}
      />,
    );
    const kinds = screen
      .getAllByTestId('activity-feed-entry')
      .map((node) => node.getAttribute('data-kind'));
    expect(kinds).toEqual(['investigation', 'resolution', 'incident', 'approval']);
  });

  it('shows the fold count only for an entry collapseFeed actually folded', () => {
    render(
      <ActivityFeed
        locale="en"
        entries={[entry({ id: 'a', count: 1 }), entry({ id: 'b', count: 5 })]}
      />,
    );
    const rows = screen.getAllByTestId('activity-feed-entry');
    expect(rows[0]).not.toHaveTextContent('×');
    expect(screen.getByTestId('activity-feed-count')).toBeInTheDocument();
  });

  it('carries the typed objective in the newest entry, for a run just started', () => {
    render(
      <ActivityFeed
        locale="en"
        entries={[
          entry({
            id: 'run-started',
            kind: 'investigation',
            subjectKey: '',
            title: 'Investigation started',
            detail: 'Procurar anomalias no cluster Proxmox',
          }),
        ]}
      />,
    );
    expect(screen.getByTestId('activity-feed-entry')).toHaveTextContent(
      'Procurar anomalias no cluster Proxmox',
    );
  });

  it('renders nothing when there are no entries, without error', () => {
    render(<ActivityFeed locale="en" entries={[]} />);
    expect(screen.queryByTestId('activity-feed-entry')).toBeNull();
  });
});

describe('ActivityFeed shapes', () => {
  /**
   * Four kinds, four shapes -- and a shape is only a shape if it is not a
   * circle. The marks were written at the icon scale with a `rounded-1`
   * corner, which on a 14px box is a 6px radius: two pixels of flat edge per
   * side, so the "diamond" and the "square" both drew as circles and three of
   * the four kinds were indistinguishable on screen.
   */
  function marks(): readonly Element[] {
    return screen
      .getAllByTestId('activity-feed-entry')
      .map((row) => row.querySelector('[aria-hidden="true"]'))
      .filter((node): node is Element => node !== null);
  }

  it('draws the investigation mark as a diamond with corners, never a rounded blob', () => {
    render(
      <ActivityFeed
        locale="en"
        entries={[entry({ id: 'a', kind: 'investigation' })]}
      />,
    );
    const mark = marks()[0];
    expect(mark?.className).toContain('rotate-45');
    expect(mark?.className).not.toContain('rounded');
  });

  it('draws the incident mark as a square with corners, never a rounded blob', () => {
    render(<ActivityFeed locale="en" entries={[entry({ id: 'a', kind: 'incident' })]} />);
    const mark = marks()[0];
    expect(mark?.className).not.toContain('rounded');
    expect(mark?.className).not.toContain('rotate');
  });

  it('gives the four kinds four different marks', () => {
    render(
      <ActivityFeed
        locale="en"
        entries={[
          entry({ id: 'a', kind: 'investigation' }),
          entry({ id: 'b', kind: 'resolution' }),
          entry({ id: 'c', kind: 'incident' }),
          entry({ id: 'd', kind: 'approval' }),
        ]}
      />,
    );
    const shapes = marks().map((mark) =>
      mark.className
        .split(/\s+/)
        .filter((name) => name.startsWith('rounded') || name.startsWith('rotate') || name === 'clip-triangle')
        .sort()
        .join(' '),
    );
    expect(new Set(shapes).size).toBe(4);
  });
});

describe('ActivityFeed second line', () => {
  /**
   * Time, then what produced the entry, then how long it took where there is
   * a duration -- the board's own `agora mesmo · manual`,
   * `há 2 min · investigação · 1m 27s`. The feed used to render the relative
   * time alone, which left every entry saying only when, never by what.
   */
  it("names what produced the entry beside its time", () => {
    render(
      <ActivityFeed
        locale="en"
        entries={[entry({ id: 'a', kindLabel: 'Alertmanager' })]}
      />,
    );
    expect(screen.getByTestId('activity-feed-entry')).toHaveTextContent('Alertmanager');
  });

  it('shows the duration when the entry has one', () => {
    render(
      <ActivityFeed
        locale="en"
        entries={[
          entry({ id: 'a', kind: 'resolution', kindLabel: 'investigation', duration: '1m 27s' }),
        ]}
      />,
    );
    expect(screen.getByTestId('activity-feed-entry')).toHaveTextContent('1m 27s');
  });

  it('renders the time alone when the entry has nothing else to say', () => {
    render(<ActivityFeed locale="en" entries={[entry({ id: 'a' })]} />);
    const meta = screen.getByTestId('activity-feed-meta');
    expect(meta.textContent?.trim()).toBe('2 minutes ago');
  });
});
