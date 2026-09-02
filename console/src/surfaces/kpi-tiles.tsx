import type { ReactNode } from 'react';

import NextLink from 'next/link';

import { cx } from '@/design/cx';
import { formatDuration, formatNumber } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';

/**
 * "Cada número tem dono, e o dono tem história": the five KPI tiles, each
 * rendering exactly what `GET /v1/overview` served for it -- number,
 * sparkline, decomposition -- and nothing this component recomputed on its
 * own. `dashboard.tsx` is the only reader of the panel; this component takes
 * the five already-extracted `KpiData` values and a `failed` flag for the
 * one case that is not a property of any single KPI: the whole overview
 * read coming back unreadable.
 */

/** One daily bucket of a KPI's sparkline, exactly as the overview served it. */
export interface KpiSeriesPoint {
  readonly date: string;
  readonly value: number;
}

/** One KPI's own value, decomposition and trend -- the overview's own shape. */
export interface KpiData {
  /** `null` when nothing in the window can answer the question -- never a
   * fabricated zero for "no terminal item yet". */
  readonly value: number | null;
  readonly breakdown: Readonly<Record<string, number>>;
  readonly series: readonly KpiSeriesPoint[];
  /** Set only for the one KPI that has something to say beyond numbers. */
  readonly note: string;
}

export interface KpiTilesProps {
  readonly locale: Locale;
  /** The overview panel itself could not be read -- distinct from any one
   * KPI's own `value` being `null`, which means the read succeeded and found
   * nothing to measure yet. */
  readonly failed: boolean;
  readonly watched: KpiData;
  readonly degraded: KpiData;
  readonly selfResolved: KpiData;
  readonly successRate: KpiData;
  readonly timeToCause: KpiData;
}

const SPARKLINE_WIDTH = 92;
const SPARKLINE_HEIGHT = 26;

/** The polyline `points` attribute for `series`, one point per bucket returned.
 *
 * Never invents a bucket the series did not carry -- the edge case named in
 * this feature's spec ("primeiro dia após o deploy, fotografia diária
 * vazia") is exactly a short series, drawn short rather than padded.
 */
function sparklinePoints(series: readonly KpiSeriesPoint[]): string {
  if (series.length === 0) return '';
  const values = series.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return series
    .map((point, index) => {
      const x =
        series.length === 1
          ? SPARKLINE_WIDTH
          : (index / (series.length - 1)) * SPARKLINE_WIDTH;
      const y = SPARKLINE_HEIGHT - ((point.value - min) / span) * SPARKLINE_HEIGHT;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

/** The sparkline, in the tile's own colour, or nothing for an empty series. */
function Sparkline({
  locale,
  series,
  className,
}: {
  locale: Locale;
  series: readonly KpiSeriesPoint[];
  className: string;
}): ReactNode {
  if (series.length === 0) return null;
  return (
    <svg
      data-testid="kpi-sparkline"
      width={SPARKLINE_WIDTH}
      height={SPARKLINE_HEIGHT}
      viewBox={`0 0 ${String(SPARKLINE_WIDTH)} ${String(SPARKLINE_HEIGHT)}`}
      role="img"
      aria-label={message(locale, 'dashboard.kpi.sparkline.label', {
        count: formatNumber(locale, series.length),
      })}
      className={className}
    >
      <polyline
        points={sparklinePoints(series)}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

interface TileProps {
  readonly testId: string;
  readonly label: string;
  /** `undefined` renders no value region at all -- the overview read itself
   * failed, so there is nothing here to even call unmeasured. A `null`
   * `KpiData.value` is a different, narrower case: the read succeeded and
   * this one figure has nothing to report yet, which still earns an em dash
   * in this same region rather than silence. */
  readonly value: ReactNode | undefined;
  /**
   * The role colour the number carries, matching the tile's own sparkline.
   *
   * Absent leaves it in body colour, which is right for a figure that is
   * neither good nor bad -- how many resources are watched, how long a
   * diagnosis takes. A tile whose line is drawn in danger and whose number is
   * drawn in body colour is a tile disagreeing with itself.
   */
  readonly tone?: string | undefined;
  readonly legend: ReactNode;
  readonly sparkline: ReactNode;
  readonly href?: string | undefined;
}

/** One tile's shell: label, big number, sparkline, legend -- the same four
 * regions for every KPI, whatever failed or is still unmeasured. */
function Tile({
  testId,
  label,
  value,
  tone,
  legend,
  sparkline,
  href,
}: TileProps): ReactNode {
  const body = (
    <div
      data-testid="kpi-tile"
      data-kpi={testId}
      className="bg-raised edge border-border rounded-3 shadow-1 p-3 flex flex-col gap-2 h-full"
    >
      <span className="text-meta text-muted">{label}</span>
      {value === undefined ? null : (
        <span
          data-testid="kpi-value"
          className={cx('font-display text-display tabular-nums', tone)}
        >
          {value}
        </span>
      )}
      {sparkline}
      <span data-testid="kpi-legend" className="text-meta text-muted">
        {legend}
      </span>
    </div>
  );
  if (href === undefined) return body;
  return (
    <NextLink href={href} className="block h-full motion-hover hover:opacity-90">
      {body}
    </NextLink>
  );
}

/** `{count} kind · {count} kind`, straight from the breakdown's own keys --
 * never a translated or reordered vocabulary this component invented. */
function joinedBreakdown(
  locale: Locale,
  breakdown: Readonly<Record<string, number>>,
): string {
  return Object.entries(breakdown)
    .map(([kind, count]) => `${formatNumber(locale, count)} ${kind}`)
    .join(message(locale, 'dashboard.kpi.watched.breakdownJoiner'));
}

function bigValue(
  locale: Locale,
  value: number | null,
  unit: 'count' | 'percent' | 'duration',
): ReactNode {
  if (value === null) return '—';
  if (unit === 'percent') {
    return (
      <>
        {formatNumber(locale, value)}
        <span className="text-meta">%</span>
      </>
    );
  }
  if (unit === 'duration') return formatDuration(locale, value);
  return formatNumber(locale, value);
}

/** The five KPI tiles, from one overview read -- never a client recomputation. */
export function KpiTiles({
  locale,
  failed,
  watched,
  degraded,
  selfResolved,
  successRate,
  timeToCause,
}: KpiTilesProps): ReactNode {
  if (failed) {
    const failedLegend = message(locale, 'dashboard.kpi.readFailed');
    return (
      <div
        data-testid="main-figures"
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5 mb-5"
      >
        {(
          [
            ['watched', message(locale, 'dashboard.kpi.watched')],
            ['degraded', message(locale, 'dashboard.kpi.degraded')],
            ['selfResolved', message(locale, 'dashboard.kpi.selfResolved')],
            ['successRate', message(locale, 'dashboard.kpi.successRate')],
            ['timeToCause', message(locale, 'dashboard.kpi.timeToCause')],
          ] as const
        ).map(([id, label]) => (
          <Tile
            key={id}
            testId={id}
            label={label}
            value={undefined}
            legend={failedLegend}
            sparkline={null}
          />
        ))}
      </div>
    );
  }

  // This is the tile's one link in the no-detector state -- below, `Tile`
  // itself is given no `href` for that same state, specifically so it does
  // not wrap this anchor in a second one. Nesting an anchor inside an anchor
  // is invalid HTML and was the concrete cause of a hydration failure (React
  // error #418) on a deployment with no detector enabled: the browser's
  // parser splits a nested `<a>` apart while parsing the server's markup, so
  // the tree it hydrates against never matches the one React rendered.
  const degradedLegend =
    degraded.note === 'no_detector_enabled' ? (
      <NextLink href="/config?tab=detectors" className="text-accent hover:underline">
        {message(locale, 'dashboard.kpi.degraded.noDetector')}
      </NextLink>
    ) : (
      message(locale, 'dashboard.kpi.degraded.context')
    );

  return (
    <div
      data-testid="main-figures"
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5 mb-5"
    >
      <Tile
        testId="watched"
        label={message(locale, 'dashboard.kpi.watched')}
        value={bigValue(locale, watched.value, 'count')}
        legend={joinedBreakdown(locale, watched.breakdown)}
        sparkline={
          <Sparkline locale={locale} series={watched.series} className="text-accent" />
        }
        href="/estate"
      />
      <Tile
        testId="degraded"
        tone="text-danger"
        label={message(locale, 'dashboard.kpi.degraded')}
        value={bigValue(locale, degraded.value, 'count')}
        legend={degradedLegend}
        sparkline={
          <Sparkline locale={locale} series={degraded.series} className="text-danger" />
        }
        // No tile-level `href` in the no-detector state: `degradedLegend`
        // above already carries the one anchor this tile gets in that state,
        // to this exact destination. A deployment with a detector enabled
        // gets the whole card wrapped in a link to the estate, same as every
        // other tile; a deployment with none gets one link, to configuration,
        // never two.
        href={
          degraded.note === 'no_detector_enabled' ? undefined : '/estate?health=problem'
        }
      />
      <Tile
        testId="selfResolved"
        tone="text-success"
        label={message(locale, 'dashboard.kpi.selfResolved')}
        value={bigValue(locale, selfResolved.value, 'percent')}
        legend={
          selfResolved.value === null
            ? message(locale, 'dashboard.kpi.selfResolved.context.none')
            : message(locale, 'dashboard.kpi.selfResolved.context', {
                closed: formatNumber(locale, selfResolved.breakdown.self_resolved ?? 0),
                total: formatNumber(locale, selfResolved.breakdown.total ?? 0),
              })
        }
        sparkline={
          <Sparkline
            locale={locale}
            series={selfResolved.series}
            className="text-success"
          />
        }
        href="/incidents"
      />
      <Tile
        testId="successRate"
        tone="text-success"
        label={message(locale, 'dashboard.kpi.successRate')}
        value={bigValue(locale, successRate.value, 'percent')}
        legend={
          successRate.value === null
            ? message(locale, 'dashboard.kpi.successRate.context.none')
            : message(locale, 'dashboard.kpi.successRate.context', {
                succeeded: formatNumber(locale, successRate.breakdown.succeeded ?? 0),
                total: formatNumber(locale, successRate.breakdown.total ?? 0),
              })
        }
        sparkline={
          <Sparkline
            locale={locale}
            series={successRate.series}
            className="text-success"
          />
        }
        href="/runs"
      />
      <Tile
        testId="timeToCause"
        label={message(locale, 'dashboard.kpi.timeToCause')}
        value={bigValue(locale, timeToCause.value, 'duration')}
        legend={
          timeToCause.value === null
            ? message(locale, 'dashboard.kpi.timeToCause.context.none')
            : message(locale, 'dashboard.kpi.timeToCause.context', {
                median: formatDuration(
                  locale,
                  timeToCause.breakdown.median_seconds ?? 0,
                ),
                worst: formatDuration(locale, timeToCause.breakdown.worst_seconds ?? 0),
              })
        }
        sparkline={
          <Sparkline
            locale={locale}
            series={timeToCause.series}
            className="text-info"
          />
        }
        href="/runs"
      />
    </div>
  );
}
