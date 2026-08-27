'use client';

import type { ReactNode } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

import { message, type Locale } from '@/i18n/messages';
import { CHIP_SHAPE } from '@/components/status';
import { cx } from '@/design/cx';
import { delayAfter, freshnessOf, type Freshness } from './freshness';

/**
 * The screen keeping itself current, and saying whether it is.
 *
 * An operator was pressing reload to find out whether anything had moved, on a
 * console whose subject is a deployment that changes while nobody is looking.
 * This does the pressing, and the indicator says whether it is working.
 *
 * `router.refresh()` rather than a document load, which is the whole reason
 * this is cheap enough to do on a timer: the Server Components of the *current*
 * route re-run and the result is reconciled into the page. The frame is not
 * rebuilt, the scroll position survives, no client state is lost, and — the
 * part that matters for a page full of six independent panels — a panel whose
 * data did not change does not flicker, because nothing about it changed.
 *
 * Three things it deliberately does not do. It does not re-read a tab nobody
 * is looking at, because that is a request a person cannot benefit from and a
 * console left open overnight would make five thousand of them. It does not
 * shorten its interval under failure. And it does not claim to be current when
 * it is not: three consecutive failures and the indicator says so, which is
 * the one property that makes the indicator worth having at all.
 */

const SKIN: Readonly<Record<Freshness, string>> = {
  live: 'border-accent bg-accent-bg text-accent',
  refreshing: 'border-info bg-info-bg text-info',
  stale: 'border-border-strong bg-neutral-bg text-neutral',
  paused: 'border-border-strong bg-neutral-bg text-neutral',
};

const LABEL: Readonly<
  Record<
    Freshness,
    | 'live.state.live'
    | 'live.state.refreshing'
    | 'live.state.stale'
    | 'live.state.paused'
  >
> = {
  live: 'live.state.live',
  refreshing: 'live.state.refreshing',
  stale: 'live.state.stale',
  paused: 'live.state.paused',
};

/**
 * The mark each state carries, so colour is never the only difference.
 *
 * Sized on the icon scale, like every `ShapeMark` in the component library.
 * These four were written at `size-2` — eight pixels, a step of the *spacing*
 * scale — which put a five-pixel difference between this mark and the status
 * mark sitting a few centimetres away in the page header. `status.tsx` says
 * why the icon scale is the right one and the spacing scale is not: a glyph
 * sits on a text baseline, and one that grows with the padding drifts away
 * from the letters beside it.
 */
function Mark({ state }: { readonly state: Freshness }): ReactNode {
  if (state === 'live') {
    return (
      <span
        aria-hidden="true"
        className="pulse-live inline-block icon-inline rounded-full bg-accent"
      >
        <span className="pulse-live-ring" />
      </span>
    );
  }
  if (state === 'refreshing') {
    return (
      <span
        aria-hidden="true"
        className="inline-block icon-inline rounded-full edge-ring border-info bg-transparent"
      />
    );
  }
  if (state === 'stale') {
    return (
      <span
        aria-hidden="true"
        className="inline-block icon-inline rounded-full bg-neutral opacity-50"
      />
    );
  }
  // Paused: the dash, drawn the way `status.tsx` draws its own — a box with no
  // height, so the ring is the whole of the mark. It used to carry a width and
  // no height at all, which is the same picture arrived at by accident.
  return (
    <span
      aria-hidden="true"
      className="inline-block icon-inline h-0 rounded-full edge-ring border-border-strong"
    />
  );
}

export interface AutoRefreshProps {
  readonly locale: Locale;
  /** Injected so the suite can drive the clock without waiting on one. */
  readonly now?: () => number;
}

/** Re-reads the current route while the tab is watched, and says how it is going. */
export function AutoRefresh({ locale }: AutoRefreshProps): ReactNode {
  const router = useRouter();
  const [failures, setFailures] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [visible, setVisible] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const state = freshnessOf({ visible, refreshing, failures });

  const refresh = useCallback(() => {
    setRefreshing(true);
    // A reachability probe rather than a guess: `router.refresh()` returns
    // nothing and reports nothing, so the failure count has to come from
    // somewhere that can actually fail. This asks the console's own origin for
    // the cheapest thing it serves, which is exactly the hop that breaks when
    // the deployment is unreachable.
    fetch('/api/reachable', { cache: 'no-store' })
      .then((answer) => {
        if (!answer.ok) throw new Error(String(answer.status));
        setFailures(0);
        router.refresh();
      })
      .catch(() => {
        setFailures((count) => count + 1);
      })
      .finally(() => {
        setRefreshing(false);
      });
  }, [router]);

  useEffect(() => {
    const watch = (): void => {
      setVisible(!document.hidden);
    };
    watch();
    document.addEventListener('visibilitychange', watch);
    return () => {
      document.removeEventListener('visibilitychange', watch);
    };
  }, []);

  useEffect(() => {
    if (!visible) {
      if (timer.current !== null) clearTimeout(timer.current);
      return;
    }
    timer.current = setTimeout(refresh, delayAfter(failures));
    return () => {
      if (timer.current !== null) clearTimeout(timer.current);
    };
  }, [visible, failures, refresh]);

  return (
    <span
      data-testid="freshness"
      data-state={state}
      role="status"
      // The shared chip geometry, named rather than rewritten. Written out
      // here it had drifted to a control height with horizontal padding only,
      // so the one chip that appears on every screen was the one drawn
      // differently from all the others.
      className={cx(CHIP_SHAPE, 'edge', SKIN[state])}
    >
      <Mark state={state} />
      {message(locale, LABEL[state])}
    </span>
  );
}
