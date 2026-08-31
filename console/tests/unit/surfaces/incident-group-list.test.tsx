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
    <IncidentGroupList
      groups={groups}
      locale="en"
      now={NOW}
      zone="UTC"
      runHeadlines={new Map()}
    />,
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
  it('leaves an unresolved opaque identifier out of the line, reachable only as a tooltip', () => {
    // FR-024/SC-007: an internal identifier is never text of the line, not
    // even shortened. The full key is still what a reader finds by hovering
    // the row, through its own `title`.
    list([group()]);

    const subjects = screen.getByTestId('incident-group-subjects');
    expect(subjects).not.toHaveTextContent('res-7a73b8aa');
    expect(subjects).not.toHaveTextContent('1194c1ed14dd87f7e0e80b81');
    expect(subjects).toHaveTextContent('alertmanager');
    expect(subjects).toHaveAttribute('title', 'res-7a73b8aa1194c1ed14dd87f7e0e80b81');
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

describe("the subject line prefers the estate's own name over the key that reaches it", () => {
  it('shows the resolved name alone, with an opaque id kept out of the line entirely', () => {
    // Staging showed this exact shape wrong: the name resolved ("pve01"),
    // and the opaque id still trailed it as visible text
    // ("pve01 · res-76ab1466…") -- FR-024 permits the id at most as a
    // tooltip, never as text of the line, whether or not a name was found
    // for it.
    render(
      <IncidentGroupList
        groups={[group({ subjects: ['res-dde476d5aa11bb22cc33dd44ee55ff66'] })]}
        locale="en"
        now={NOW}
        zone="UTC"
        subjectNames={
          new Map([['res-dde476d5aa11bb22cc33dd44ee55ff66', 'runner-orchestrator']])
        }
      />,
    );

    const subjects = screen.getByTestId('incident-group-subjects');
    expect(subjects).toHaveTextContent('runner-orchestrator');
    // The id is not lost -- it is exactly what a reader who hovers the row
    // finds, and it is not repeated anywhere in the visible line.
    expect(subjects).not.toHaveTextContent('res-dde476d5');
    expect(subjects).toHaveAttribute('title', 'res-dde476d5aa11bb22cc33dd44ee55ff66');
    const named = screen.getByTestId('incident-subject-name');
    expect(named).toHaveTextContent('runner-orchestrator');
    expect(named).not.toHaveTextContent('res-dde476d5');
    expect(named).toHaveAttribute(
      'data-resource-id',
      'res-dde476d5aa11bb22cc33dd44ee55ff66',
    );
  });

  it('keeps a resolved name trailed by its id when the id was never opaque to begin with', () => {
    // `ct-102` -> `anchor`: short, already legible, and matching neither of
    // SC-007's banned shapes -- the Incidents-by-subject screen relies on
    // exactly this trailing detail surviving, and this pins that it does.
    render(
      <IncidentGroupList
        groups={[group({ subjects: ['ct-102'] })]}
        locale="en"
        now={NOW}
        zone="UTC"
        subjectNames={new Map([['ct-102', 'anchor']])}
      />,
    );

    const named = screen.getByTestId('incident-subject-name');
    expect(named).toHaveTextContent('anchor');
    expect(named).toHaveTextContent('ct-102');
  });

  it('names nothing rather than the plain id, honestly, when the estate does not hold the subject', () => {
    // No `subjectNames` at all -- the same page that never fetched the
    // estate must still render nothing SC-007 bans; it falls back to the
    // detector, the same as a group naming no subject at all.
    list([group()]);

    const subjects = screen.getByTestId('incident-group-subjects');
    expect(subjects).not.toHaveTextContent('res-7a73b8aa');
    expect(subjects).toHaveTextContent('alertmanager');
    expect(screen.queryByTestId('incident-subject-name')).toBeNull();
  });

  it('does not repeat the id as if it were a name when the estate only echoes the id back', () => {
    // The gateway itself falls back to the id as `display_name` when a
    // resource has none -- that is not a name gained, and must not render
    // as one.
    render(
      <IncidentGroupList
        groups={[group({ subjects: ['ct-102'] })]}
        locale="en"
        now={NOW}
        zone="UTC"
        subjectNames={new Map([['ct-102', 'ct-102']])}
      />,
    );

    expect(screen.queryByTestId('incident-subject-name')).toBeNull();
    expect(screen.getByTestId('incident-group-subjects')).toHaveTextContent('ct-102');
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
