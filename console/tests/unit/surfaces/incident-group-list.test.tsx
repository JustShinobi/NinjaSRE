import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { IncidentGroupList } from '@/surfaces/incident-group-list';
import type { IncidentGroup } from '@/surfaces/incident-groups';

/**
 * What a row shouts about, and what it puts where a subject's name belongs.
 *
 * Two faults, both visible on the staging estate at once. Fifteen rows read
 * "Critical" in danger red beside a quiet green "Resolved", so the loudest
 * thing on a screen where nothing was currently wrong was the alarm — the
 * severity of something that is over is history, and history does not get the
 * emphasis of a live problem.
 *
 * And four of those rows carried `res-7a73b8aa1194c1ed14dd87f7e0e80b81` as
 * their subject line: thirty-six characters that identify the row for a
 * database and for nobody else, repeated identically down the column that is
 * supposed to tell one row from the next.
 */

const NOW = new Date('2026-08-26T12:00:00Z');

function group(overrides: Partial<IncidentGroup> = {}): IncidentGroup {
  return {
    key: 'ck-1',
    title: 'RedisExporterDown',
    subjects: ['res-7a73b8aa1194c1ed14dd87f7e0e80b81'],
    detector: 'alertmanager',
    count: 8,
    severity: 'critical',
    state: 'resolved',
    live: false,
    lastAt: '2026-08-26T09:00:00Z',
    firstAt: '2026-08-26T06:00:00Z',
    occurrences: [],
    ...overrides,
  };
}

function list(groups: readonly IncidentGroup[]): void {
  render(
    <IncidentGroupList groups={groups} locale="en" now={NOW} zone="UTC" />,
  );
}

describe('severity yields to state once a cause is over', () => {
  it('demotes the severity of a group nothing is still happening in', () => {
    list([group({ live: false })]);

    const severity = screen.getByTestId('incident-group-severity');
    // Still said — a critical that resolved itself is not the same event as a
    // low one that did — but said as history, not as an alarm.
    expect(severity).toHaveTextContent(/critical/i);
    expect(severity).toHaveAttribute('data-past', 'true');
    expect(severity.querySelector('[data-role="danger"]')).toBeNull();
  });

  it('leaves the severity loud while a cause is still live', () => {
    list([group({ live: true, state: 'investigating' })]);

    const severity = screen.getByTestId('incident-group-severity');
    expect(severity).toHaveAttribute('data-past', 'false');
    expect(severity.querySelector('[data-role="danger"]')).not.toBeNull();
  });
});

describe('the subject line carries something a person can read', () => {
  it('shortens an opaque identifier and keeps the whole of it reachable', () => {
    list([group()]);

    const subjects = screen.getByTestId('incident-group-subjects');
    expect(subjects).toHaveTextContent('res-7a73b8aa…');
    expect(subjects).not.toHaveTextContent('1194c1ed14dd87f7e0e80b81');
    // Shortened for reading, never lost: the full key is what somebody pastes
    // into a query.
    expect(subjects).toHaveAttribute(
      'title',
      'res-7a73b8aa1194c1ed14dd87f7e0e80b81',
    );
  });

  it('leaves a subject that is already a name exactly as it is', () => {
    list([group({ subjects: ['adguard-primary', 'blackbox-dns-adguard'] })]);

    const subjects = screen.getByTestId('incident-group-subjects');
    expect(subjects).toHaveTextContent('adguard-primary · blackbox-dns-adguard');
    expect(subjects).not.toHaveTextContent('…');
  });

  it('falls back to the detector when a group names no subject at all', () => {
    list([group({ subjects: [] })]);

    expect(screen.getByTestId('incident-group-subjects')).toHaveTextContent(
      'alertmanager',
    );
  });
});

describe('the row still says everything it said before', () => {
  it('keeps the title, the state and the count', () => {
    list([group()]);

    const row = screen.getByTestId('incident-group');
    expect(within(row).getByText('RedisExporterDown')).toBeInTheDocument();
    expect(within(row).getByTestId('incident-group-count')).toHaveTextContent('8');
    expect(within(row).getByTestId('incident-group-state')).toHaveTextContent(
      /resolved/i,
    );
  });
});
