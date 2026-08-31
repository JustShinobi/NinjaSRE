import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { KpiTiles, type KpiData } from '@/surfaces/kpi-tiles';

/**
 * "Cada número tem dono, e o dono tem história": each of the five KPIs
 * renders the overview's own number, a sparkline over its own series, and a
 * decomposition legend -- straight from the fields `GET /v1/overview`
 * serves, never a client-side recomputation.
 */

function kpi(over: Partial<KpiData> = {}): KpiData {
  return {
    value: 42,
    breakdown: {},
    series: [
      { date: '2026-08-25', value: 40 },
      { date: '2026-08-26', value: 41 },
      { date: '2026-08-27', value: 42 },
    ],
    note: '',
    ...over,
  };
}

function tiles(over: Partial<Parameters<typeof KpiTiles>[0]> = {}) {
  return render(
    <KpiTiles
      locale="en"
      failed={false}
      watched={kpi({
        value: 86,
        breakdown: { container: 82, node: 2, 'virtual-machine': 2 },
      })}
      degraded={kpi({ value: 14, note: '' })}
      selfResolved={kpi({ value: 100, breakdown: { self_resolved: 45, total: 45 } })}
      successRate={kpi({ value: 100, breakdown: { succeeded: 48, total: 48 } })}
      timeToCause={kpi({
        value: 75,
        breakdown: { median_seconds: 75, worst_seconds: 190 },
      })}
      {...over}
    />,
  );
}

/** The one tile whose `data-kpi` names it -- the same disambiguation the
 * acceptance suite's own `kpiTile()` locator uses against the live page. */
function tileFor(name: string): HTMLElement {
  const found = screen
    .getAllByTestId('kpi-tile')
    .find((tile) => tile.getAttribute('data-kpi') === name);
  if (found === undefined) throw new Error(`no kpi-tile carries data-kpi="${name}"`);
  return found;
}

describe('KpiTiles', () => {
  it('renders one tile per KPI, five total', () => {
    tiles();
    expect(screen.getAllByTestId('kpi-tile')).toHaveLength(5);
  });

  it('shows the watched count and its breakdown by kind, straight from the field', () => {
    tiles();
    const tile = tileFor('watched');
    expect(within(tile).getByTestId('kpi-value')).toHaveTextContent('86');
    // Every kind the breakdown named, none invented and none dropped.
    expect(within(tile).getByText(/82/)).toBeInTheDocument();
    expect(within(tile).getByText(/container/)).toBeInTheDocument();
    expect(within(tile).getByText(/virtual-machine/)).toBeInTheDocument();
    // The legend carries its own hook -- the same one the acceptance suite
    // asserts is visible on the live page.
    expect(within(tile).getByTestId('kpi-legend')).toBeInTheDocument();
  });

  it('draws one sparkline point per bucket the series actually returned', () => {
    tiles({
      watched: kpi({
        series: [
          { date: '2026-08-24', value: 10 },
          { date: '2026-08-25', value: 20 },
        ],
      }),
    });
    const tile = tileFor('watched');
    const polyline = within(tile)
      .getByTestId('kpi-sparkline')
      .querySelector('polyline');
    expect(polyline).not.toBeNull();
    // Two buckets in, two points out -- neither a third invented nor one dropped.
    expect(polyline?.getAttribute('points')?.trim().split(/\s+/)).toHaveLength(2);
  });

  it('draws no sparkline, without error, when the series is empty', () => {
    tiles({ watched: kpi({ series: [] }) });
    const tile = tileFor('watched');
    expect(within(tile).queryByTestId('kpi-sparkline')).not.toBeInTheDocument();
  });

  it('says a rate with nothing to measure is unmeasured, never a fabricated zero', () => {
    tiles({ successRate: kpi({ value: null, breakdown: {} }) });
    const tile = tileFor('successRate');
    expect(within(tile).getByTestId('kpi-value')).toHaveTextContent('—');
    expect(within(tile).queryByText('0')).not.toBeInTheDocument();
  });

  it('names the no-detector case on the degraded tile, with a link to configuration', () => {
    tiles({ degraded: kpi({ value: 0, note: 'no_detector_enabled' }) });
    const tile = tileFor('degraded');
    expect(
      within(tile).getByText('No detector promotes a finding to an incident'),
    ).toBeInTheDocument();
    expect(within(tile).getByRole('link')).toHaveAttribute(
      'href',
      expect.stringContaining('detector'),
    );
  });

  it('renders the median and the worst case on the time-to-cause tile as durations', () => {
    tiles();
    const tile = tileFor('timeToCause');
    expect(within(tile).getByTestId('kpi-value')).toHaveTextContent('1m 15s');
    expect(within(tile).getByText(/3m 10s/)).toBeInTheDocument();
  });

  it('marks every tile read-failed when the overview panel itself could not be read, inventing nothing', () => {
    tiles({ failed: true });
    const tiles_ = screen.getAllByTestId('kpi-tile');
    expect(tiles_).toHaveLength(5);
    for (const tile of tiles_) {
      expect(within(tile).getByText('Could not be read')).toBeInTheDocument();
      expect(within(tile).queryByTestId('kpi-value')).not.toBeInTheDocument();
    }
  });
});
