'use client';

import type { ReactNode } from 'react';

import NextLink from 'next/link';

import { StatusDot } from '@/components/status';
import { formatNumber } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { StageRail } from '@/surfaces/stage-rail';
import type { Seed } from './reducer';
import { useRun } from './use-run';
import type { RunStore } from './store';

/**
 * The three panels of a run's rail, read live — the client half of "the rail
 * never claims absence about a run still writing".
 *
 * Each of these subscribes to the same store `LiveRun`/`LiveEventCount`
 * already read (`console/src/live/use-run.ts`): one connection per run,
 * shared by every consumer on the page, so a count and a chip cannot
 * disagree about what has arrived the way the transcript's header and body
 * once did. `StageRail` itself is presentational and reused unchanged from
 * the settled path — only what feeds it differs.
 */

export interface LiveRailProps {
  readonly runId: string;
  readonly locale: Locale;
  /** What the server already rendered — always empty for these three: none
   * of them has anything to show before the stream's own catch-up read
   * delivers it, the same reasoning `run-detail.tsx` already documents for
   * the transcript's own seed. */
  readonly seed: Seed;
  /** Injected so the suite can drive a stream without a network. */
  readonly store?: RunStore;
}

/** The pipeline rail, moved by the `stage_completed` events the stream carries. */
export function LiveStageRail({
  runId,
  locale,
  seed,
  store,
}: LiveRailProps): ReactNode {
  const snapshot = useRun(runId, seed, store);
  return (
    <StageRail
      locale={locale}
      stages={snapshot.live.stages}
      running={snapshot.live.phase === 'running'}
    />
  );
}

/** The chip a resource gets wherever "what it touched" lists one — live or settled. */
export function TouchedChip({ resource }: { readonly resource: string }): ReactNode {
  return (
    <NextLink
      data-testid="touched-resource"
      href={`/resources?selected=${encodeURIComponent(resource)}`}
      prefetch={false}
      className="slide-in inline-flex items-center rounded-full edge border-border bg-sunken px-2 py-1 font-mono text-meta text-muted motion-hover hover:text-text hover:bg-hover"
    >
      {resource}
    </NextLink>
  );
}

/** "What it touched", appended one chip at a time as the stream names a resource. */
export function LiveTouched({ runId, locale, seed, store }: LiveRailProps): ReactNode {
  const snapshot = useRun(runId, seed, store);
  const touched = snapshot.live.touched;
  if (touched.length === 0) {
    return (
      <p data-testid="run-links-watching" className="text-small text-muted">
        {message(locale, 'run.links.watching')}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap gap-2">
        {touched.map((resource) => (
          <TouchedChip key={resource} resource={resource} />
        ))}
      </div>
      <p data-testid="run-links-read-only" className="text-micro text-muted">
        {message(locale, 'run.links.readOnly')}
      </p>
    </div>
  );
}

/** One finding, the way both the live and the settled rail draw it. */
export function FindingItem({
  finding,
  failed,
}: {
  readonly finding: string;
  readonly failed: boolean;
}): ReactNode {
  return (
    <div data-testid="finding-item" className="flex items-start gap-2">
      <span className="mt-1">
        <StatusDot status={failed ? 'failure' : 'info'} />
      </span>
      <span className="text-small">{finding}</span>
    </div>
  );
}

/** "Descobertas até agora": the finding of each stage that has one, as it arrives. */
export function LiveFindings({ runId, locale, seed, store }: LiveRailProps): ReactNode {
  const snapshot = useRun(runId, seed, store);
  const findings = snapshot.live.stages.filter((stage) => stage.finding !== '');
  if (findings.length === 0) {
    return (
      <p data-testid="run-findings-none" className="text-small text-muted">
        {message(locale, 'run.findings.none')}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {findings.map((stage) => (
        <FindingItem key={stage.stage} finding={stage.finding} failed={stage.failed} />
      ))}
    </div>
  );
}

/** The cost panel's body, read live: real per-turn tokens, summed as they arrive. */
export function LiveUsage({ runId, locale, seed, store }: LiveRailProps): ReactNode {
  const snapshot = useRun(runId, seed, store);
  const usage = snapshot.live.usage;
  if (usage.turns === 0) {
    return (
      <p data-testid="run-usage-awaiting" className="text-small text-muted">
        {message(locale, 'run.usage.awaiting')}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2 text-small">
      <div className="flex items-baseline gap-2">
        <span
          data-testid="usage-tokens"
          className="font-sans text-section font-bold tabular-nums"
        >
          {formatNumber(locale, usage.tokens)}
        </span>
        <span className="text-meta text-muted">
          {message(locale, 'run.usage.tokens')} ·{' '}
          {message(locale, usage.turns === 1 ? 'run.usage.turn' : 'run.usage.turns')}{' '}
          {formatNumber(locale, usage.turns)}
        </span>
      </div>
    </div>
  );
}
