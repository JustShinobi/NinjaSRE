import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SUBJECT_VISIBLE_MAX, SubjectStrip } from '@/surfaces/subject-strip';
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

/** `count` firings of one subject, one hour apart, newest first. */
function firings(key: string, count: number): IncidentGroup {
  return group({
    key,
    count,
    occurrences: Array.from({ length: count }, (_unused, index) => ({
      id: `${key}-${String(index)}`,
      publicId: `inc_${key}_${String(index)}`,
      summary: '',
      state: 'investigating',
      severity: 'critical',
      at: new Date(NOW.getTime() - index * 60 * 60 * 1000).toISOString(),
      runId: '',
    })),
  });
}

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
    // The declared label for a state the product knows — the raw word is the
    // fallback for a state nobody declared, not the steady rendering.
    expect(within(row).getByText('Investigating')).toBeInTheDocument();
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

  it('carries a subtitle naming resource and node, never a raw identifier alone', () => {
    render(<SubjectStrip locale="en" now={NOW} groups={[group()]} />);
    const row = screen.getByTestId('subject-row');
    expect(within(row).getByTestId('subject-subtitle')).toBeInTheDocument();
  });

  it('draws a timeline strip for a subject that fired more than once', () => {
    render(<SubjectStrip locale="en" now={NOW} groups={[group()]} />);
    const row = screen.getByTestId('subject-row');
    const timeline = within(row).getByTestId('subject-timeline');
    expect(timeline).toBeVisible();
    expect(timeline.querySelector('svg')).not.toBeNull();
  });

  it('names the shaped chip with the same role its status colour uses', () => {
    render(
      <SubjectStrip locale="en" now={NOW} groups={[group({ state: 'resolved' })]} />,
    );
    const row = screen.getByTestId('subject-row');
    const chip = within(row).getByTestId('subject-chip');
    expect(chip.getAttribute('data-role')).toMatch(/.+/);
  });

  it("positions bars by each occurrence's own instant in the window, not by ordinal rank", () => {
    // Two firings an hour apart, and two firings twelve hours apart, both
    // pairs ending at `now` -- real instant-based positioning must draw the
    // first pair's bars closer together than the second pair's. Ordinal
    // placement cannot tell these two groups apart: with exactly two
    // occurrences each, it always spaces the bars by the same fixed offset
    // regardless of how far apart the firings actually were.
    const anHourApart = group({
      key: 'an-hour-apart',
      occurrences: [
        {
          id: 'hour-new',
          publicId: 'inc_hour_new',
          summary: '',
          state: 'investigating',
          severity: 'critical',
          at: NOW.toISOString(),
          runId: 'run-hour',
        },
        {
          id: 'hour-old',
          publicId: 'inc_hour_old',
          summary: '',
          state: 'resolved',
          severity: 'critical',
          at: new Date(NOW.getTime() - 60 * 60 * 1000).toISOString(),
          runId: '',
        },
      ],
    });
    const twelveHoursApart = group({
      key: 'twelve-hours-apart',
      occurrences: [
        {
          id: 'twelve-new',
          publicId: 'inc_twelve_new',
          summary: '',
          state: 'investigating',
          severity: 'critical',
          at: NOW.toISOString(),
          runId: 'run-twelve',
        },
        {
          id: 'twelve-old',
          publicId: 'inc_twelve_old',
          summary: '',
          state: 'resolved',
          severity: 'critical',
          at: new Date(NOW.getTime() - 12 * 60 * 60 * 1000).toISOString(),
          runId: '',
        },
      ],
    });
    render(
      <SubjectStrip locale="en" now={NOW} groups={[anHourApart, twelveHoursApart]} />,
    );
    const rows = screen.getAllByTestId('subject-row');
    expect(rows).toHaveLength(2);
    // A test that indexes into `rows` and asserts on `undefined` would fail
    // by saying "cannot read property of undefined", which says nothing
    // about what the strip drew -- this names the row instead.
    const barDistance = (row: HTMLElement | undefined): number => {
      if (row === undefined) {
        throw new Error('the subject row this test is about is not there');
      }
      const xs = Array.from(row.querySelectorAll('rect')).map((rect) =>
        Number(rect.getAttribute('x')),
      );
      expect(xs).toHaveLength(2);
      return Math.abs((xs[0] ?? 0) - (xs[1] ?? 0));
    };
    const hourDistance = barDistance(rows[0]);
    const twelveHourDistance = barDistance(rows[1]);
    expect(hourDistance).toBeLessThan(twelveHourDistance);
  });

  it('draws every subject over the same span, so two rows can be compared', () => {
    // A strip whose width is a function of its own firing count is not a
    // timeline: two firings get twelve pixels, in which "an hour apart" and
    // "a day apart" land on the same two dots. The window is the same
    // window for every row, so the axis it is drawn on has to be too.
    render(
      <SubjectStrip
        locale="en"
        now={NOW}
        groups={[firings('few', 2), firings('many', 6)]}
      />,
    );

    const widths = screen
      .getAllByTestId('subject-row')
      .map((row) => row.querySelector('svg')?.getAttribute('width'));
    expect(widths[0]).toBe(widths[1]);
    expect(Number(widths[0])).toBeGreaterThanOrEqual(96);
  });

  it('draws at most five subjects, however many the window holds', () => {
    render(
      <SubjectStrip
        locale="en"
        now={NOW}
        groups={Array.from({ length: 8 }, (_unused, index) =>
          firings(`subject-${String(index)}`, 2),
        )}
      />,
    );
    expect(screen.getAllByTestId('subject-row')).toHaveLength(SUBJECT_VISIBLE_MAX);
    expect(SUBJECT_VISIBLE_MAX).toBe(5);
  });

  it('marks a row by its severity while live, and by its outcome once settled', () => {
    render(
      <SubjectStrip
        locale="en"
        now={NOW}
        groups={[
          group({ key: 'live' }),
          group({ key: 'settled', live: false, state: 'resolved' }),
        ]}
      />,
    );

    const shapeOf = (row: HTMLElement | undefined): string | null | undefined => {
      if (row === undefined) throw new Error('the row this test is about is not there');
      return within(row)
        .getByTestId('subject-mark')
        .querySelector('[data-shape]')
        ?.getAttribute('data-shape');
    };
    const rows = screen.getAllByTestId('subject-row');
    // Critical, and still happening: the square the severity scale gives it.
    expect(shapeOf(rows[0])).toBe('square');
    // Over: the circle that means an outcome, not an alarm.
    expect(shapeOf(rows[1])).toBe('filled-circle');
  });
});

describe('SubjectStrip row treatment', () => {
  /**
   * Two treatments, because the two rows mean different things. A subject
   * still firing sits on its own raised surface with a border; one that is
   * over sits flat, its name dimmed. The strip used to draw both identically,
   * so the only thing separating "this is happening" from "this happened" was
   * the chip at the far right of the row.
   */
  it('gives a live subject a bordered, raised row', () => {
    render(
      <SubjectStrip
        locale="en"
        now={NOW}
        groups={[group({ live: true, state: 'investigating' })]}
      />,
    );
    const row = screen.getByTestId('subject-row');
    expect(row.getAttribute('data-live')).toBe('true');
    expect(row.className).toContain('border-border');
  });

  it('gives a settled subject a flat row with a dimmed name', () => {
    render(
      <SubjectStrip
        locale="en"
        now={NOW}
        groups={[group({ live: false, state: 'resolved' })]}
      />,
    );
    const row = screen.getByTestId('subject-row');
    expect(row.getAttribute('data-live')).toBe('false');
    expect(row.className).toContain('border-transparent');
    expect(within(row).getByTestId('subject-title').className).toContain('text-muted');
  });
});
