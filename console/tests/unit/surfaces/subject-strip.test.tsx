import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SubjectStrip } from '@/surfaces/subject-strip';
import type { IncidentGroup } from '@/surfaces/incident-groups';

/**
 * "O que insiste em acontecer": one compact row per recurring subject, live
 * ones first, each with its own mini-timeline, an N× count and a state chip
 * -- never the flat `IncidentGroupList` disclosure, which is the Incidents
 * screen's own denser reading of the same groups.
 */

function group(over: Partial<IncidentGroup> = {}): IncidentGroup {
  return {
    key: 'detector:redis-exporter-down:resource:lxc-122',
    title: 'RedisExporterDown',
    subjects: ['lxc/122'],
    detector: 'alertmanager',
    count: 8,
    severity: 'critical',
    state: 'investigating',
    live: true,
    lastAt: '2026-08-27T09:00:00.000Z',
    firstAt: '2026-08-26T09:00:00.000Z',
    occurrences: [
      {
        id: 'inc-8',
        publicId: 'inc_8',
        summary: '',
        state: 'investigating',
        severity: 'critical',
        at: '2026-08-27T09:00:00.000Z',
        runId: 'run-8',
      },
      {
        id: 'inc-1',
        publicId: 'inc_1',
        summary: '',
        state: 'resolved',
        severity: 'critical',
        at: '2026-08-26T09:00:00.000Z',
        runId: 'run-1',
      },
    ],
    ...over,
  };
}

const NOW = new Date('2026-08-27T10:00:00.000Z');

describe('SubjectStrip', () => {
  it('renders one row per group', () => {
    render(
      <SubjectStrip
        locale="en"
        now={NOW}
        groups={[group({ key: 'a' }), group({ key: 'b' })]}
      />,
    );
    expect(screen.getAllByTestId('subject-row')).toHaveLength(2);
  });

  it('shows the live groups before the settled ones, whatever order they arrived in', () => {
    render(
      <SubjectStrip
        locale="en"
        now={NOW}
        groups={[
          group({
            key: 'settled',
            title: 'Settled cause',
            live: false,
            state: 'resolved',
          }),
          group({
            key: 'live',
            title: 'Live cause',
            live: true,
            state: 'investigating',
          }),
        ]}
      />,
    );
    const titles = screen.getAllByTestId('subject-row').map((row) => row.textContent);
    const liveIndex = titles.findIndex((text) => text.includes('Live cause'));
    const settledIndex = titles.findIndex((text) => text.includes('Settled cause'));
    expect(liveIndex).toBeGreaterThanOrEqual(0);
    expect(liveIndex).toBeLessThan(settledIndex);
  });

  it("shows the occurrence count as N×, from the group's own field", () => {
    render(<SubjectStrip locale="en" now={NOW} groups={[group({ count: 8 })]} />);
    expect(screen.getByText('8×')).toBeInTheDocument();
  });

  it("carries a shaped chip for the group's own state", () => {
    render(
      <SubjectStrip
        locale="en"
        now={NOW}
        groups={[group({ state: 'investigating' })]}
      />,
    );
    const row = screen.getByTestId('subject-row');
    expect(within(row).getByText('investigating')).toBeInTheDocument();
  });

  it("links the row to the newest firing's own public address, when nothing is running against it", () => {
    render(
      <SubjectStrip
        locale="en"
        now={NOW}
        groups={[
          group({
            occurrences: [
              {
                id: 'inc-8',
                publicId: 'inc_8',
                summary: '',
                state: 'resolved',
                severity: 'critical',
                at: '2026-08-27T09:00:00.000Z',
                runId: '',
              },
            ],
          }),
        ]}
      />,
    );
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/incidents?selected=inc_8');
  });

  it('links to the linked investigation instead, when the newest firing has one running', () => {
    render(
      <SubjectStrip
        locale="en"
        now={NOW}
        groups={[
          group({
            occurrences: [
              {
                id: 'inc-9',
                publicId: 'inc_9',
                summary: '',
                state: 'investigating',
                severity: 'critical',
                at: '2026-08-27T09:30:00.000Z',
                runId: 'run-9',
              },
            ],
          }),
        ]}
      />,
    );
    expect(screen.getByRole('link')).toHaveAttribute('href', '/runs?selected=run-9');
  });

  it('names why nothing repeated, and points at Incidents, when the window has no group', () => {
    render(<SubjectStrip locale="en" now={NOW} groups={[]} />);
    expect(screen.queryByTestId('subject-row')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Incidents/i })).toBeInTheDocument();
  });
});
