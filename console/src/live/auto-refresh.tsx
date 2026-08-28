'use client';

import type { ReactNode } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

import { message, type Locale } from '@/i18n/messages';
import { CHIP_SHAPE } from '@/components/status';
import { cx } from '@/design/cx';
import type { ConnectionState, StreamSource } from './connection';
import { DeploymentConnection } from './deployment';
import { STALE_AFTER_FAILURES, delayAfter, type Freshness } from './freshness';
import { fetchStreamSource } from './transport';

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
 *
 * **The deployment channel is now the trigger; the timer is the fallback.**
 * While `DeploymentConnection` reports `connected`, the timer below is
 * suspended — every event (or batch, inside `DEPLOYMENT_REFRESH_BATCH_MS`)
 * calls the same `refresh()` the timer used to call on its own schedule, and
 * a `resync` calls it immediately, unbatched. The instant the channel is
 * anything other than `connected` — attempting to open, backed off and
 * retrying, or given up — the timer resumes exactly as it always has,
 * `delayAfter(failures)` and all: SC-002's thirty-second bound is met by the
 * timer covering from the first sign of trouble, not from the channel giving
 * up on it. `freshnessOf` (three consecutive *timer* failures means stale)
 * only ever runs during that fallback window now; `freshnessFromConnection`
 * is what the chip reads while the channel is the one in charge.
 *
 * **Why the chip does not simply wait for `disconnected`.** `BACKOFF_MS` and
 * `MAX_RECONNECTIONS` are `connection.ts`'s own — ten attempts, the last
 * five capped at eight seconds apiece — and a connection that keeps
 * retrying does not reach `disconnected` until roughly fifty-five seconds
 * have passed. Mapping `reconnecting` to `refreshing` for the whole of that
 * window, as a literal reading of the five-states-to-four table would, is
 * what a real run of this feature's own acceptance spec against the local
 * mock harness caught: the chip stayed on `refreshing` for the full
 * thirty-second budget the spec (and SC-002) allow, never once reaching
 * `stale`. `STALE_AFTER_FAILURES` — the same three-failures threshold
 * `freshnessOf` already uses for the timer-only mechanism — is reused here
 * as the point past which a `reconnecting` channel is shown as `stale`
 * rather than `refreshing`: real trouble, not a first blip, and well inside
 * thirty seconds (`BACKOFF_MS[0] + BACKOFF_MS[1]` is under two seconds
 * before the third attempt even starts).
 */

/**
 * The four `Freshness` states the five `ConnectionState` values collapse
 * onto — no new chip state, as the decision that governs every indicator on
 * this console requires. `connecting` reads the same as `reconnecting`
 * below `STALE_AFTER_FAILURES` attempts (`refreshing`): both are "not
 * delivering yet, trying to be", and the chip has never distinguished a
 * first attempt from an early retry. Past that many attempts, `reconnecting`
 * reads as `stale` instead — see the module docstring for why the plain
 * one-to-one mapping is not what this returns.
 */
function freshnessFromConnection(state: ConnectionState, attempts: number): Freshness {
  switch (state) {
    case 'connected':
      return 'live';
    case 'connecting':
    case 'reconnecting':
      return attempts >= STALE_AFTER_FAILURES ? 'stale' : 'refreshing';
    case 'idle':
      return 'paused';
    case 'disconnected':
      return 'stale';
  }
}

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
  /**
   * Where the deployment channel's connection actually reads from. Defaults
   * to the real `fetch`-backed transport every screen uses; a test replaces
   * it with a fake so this component never makes a real network request —
   * `RunConnection`'s own tests inject the identical seam for the same reason.
   */
  readonly deploymentSource?: StreamSource;
}

/** Re-reads the current route while the deployment channel is quiet, and always says how it is going. */
export function AutoRefresh({ locale, deploymentSource = fetchStreamSource }: AutoRefreshProps): ReactNode {
  const router = useRouter();
  const [failures, setFailures] = useState(0);
  const [visible, setVisible] = useState(true);
  const [tick, setTick] = useState(0);
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const [connectionAttempts, setConnectionAttempts] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connection = useRef<DeploymentConnection | null>(null);

  const state = freshnessFromConnection(connectionState, connectionAttempts);

  const refresh = useCallback(() => {
    // A reachability probe rather than a guess: `router.refresh()` returns
    // nothing and reports nothing, so the failure count has to come from
    // somewhere that can actually fail. This asks the console's own origin for
    // the cheapest thing it serves, which is exactly the hop that breaks when
    // the deployment is unreachable. Also what the deployment channel calls,
    // on every event batch and on every resync: one mechanism, two triggers.
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
        setTick((current) => current + 1);
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

  // Read through a ref rather than closed over directly, so the effect below
  // can declare an empty dependency array honestly: the connection opens
  // once, on mount, and must not be torn down and reopened merely because
  // `refresh` was recreated (`useRouter()`'s own router reference is not
  // guaranteed stable across every render this component sees).
  const refreshRef = useRef(refresh);
  useEffect(() => {
    refreshRef.current = refresh;
  }, [refresh]);

  useEffect(() => {
    const opened = new DeploymentConnection({
      source: deploymentSource,
      onState: setConnectionState,
      // Not read from inside `onState`: a second, third, ... consecutive
      // failure leaves the connection state as `reconnecting` both before
      // and after, and `connection.ts`'s own `#setState` drops a call that
      // would not change the state string — `onState` would fire exactly
      // once per retry *sequence*, not once per attempt. `onAttempt` is the
      // hook that does fire every time, which is what lets the chip notice
      // the third failure and switch to `stale` instead of staying on
      // `refreshing` for the whole of a ten-attempt backoff — found by
      // running this feature's own acceptance spec for real and watching
      // the chip never leave `refreshing` despite five failed attempts.
      onAttempt: setConnectionAttempts,
      onEvents: () => {
        refreshRef.current();
      },
      onResync: () => {
        refreshRef.current();
      },
    });
    connection.current = opened;
    opened.open();
    return () => {
      opened.close();
      connection.current = null;
    };
    // `deploymentSource` is a test-only override; in production it is
    // `fetchStreamSource`, a module-level constant, so this effect only ever
    // re-runs (tearing down and reopening the connection) in a test that
    // deliberately swaps the source.
  }, [deploymentSource]);

  useEffect(() => {
    // The timer is the fallback. Suspended for as long as the channel is
    // actually delivering (`connected`) — resumed the instant it is not,
    // which includes the first attempt to reconnect, not only the moment it
    // gives up: SC-002's thirty-second bound is measured from the channel
    // dropping, and waiting for full exhaustion (worst case, tens of
    // seconds of backoff) would blow well past it.
    if (!visible || connectionState === 'connected') {
      if (timer.current !== null) clearTimeout(timer.current);
      return;
    }
    timer.current = setTimeout(refresh, delayAfter(failures));
    return () => {
      if (timer.current !== null) clearTimeout(timer.current);
    };
  }, [visible, failures, tick, refresh, connectionState]);

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
