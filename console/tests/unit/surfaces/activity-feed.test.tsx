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
      entry({ id: 'a', kind: 'approval', subjectKey: '', title: 'Remediation proposed' }),
      entry({ id: 'b', kind: 'approval', subjectKey: '', title: 'Remediation proposed' }),
    ]);
    expect(collapsed).toHaveLength(2);
  });
});

describe('ActivityFeed', () => {
  it('renders one entry per item, newest first, exactly as given', () => {
    render(
      <ActivityFeed
        locale="en"
        entries={[entry({ id: 'a' }), entry({ id: 'b' })]}
      />,
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
