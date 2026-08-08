'use client';

import { useCallback, useMemo, useRef, useSyncExternalStore } from 'react';

import { fetchStreamSource } from './transport';
import type { Seed } from './reducer';
import { RunStore, type RunSnapshot } from './store';

/**
 * The one store a screen reads a live run from.
 *
 * A module-level instance rather than a React context, for the same reason the
 * session controller is one: the thing that opens a stream is not a component,
 * and a context would mean every consumer had to be inside one tree. It is also
 * what makes "one subscription per run" true across a page whose transcript,
 * cost panel and approval card do not know about each other.
 */
export const runStore = new RunStore({ source: fetchStreamSource });

/**
 * Watch a run, and re-render when something arrives.
 *
 * `useSyncExternalStore` rather than an effect writing to state: a subscription
 * read inside an effect renders once with a stale value and once with the real
 * one, which on a transcript is a visible correction on every mount.
 */
export function useRun(
  runId: string,
  seed: Seed,
  store: RunStore = runStore,
): RunSnapshot {
  // The seed describes what the server already rendered. It is captured once,
  // because a second consumer arriving mid-run must join what is there rather
  // than resetting it to what its own props say.
  const held = useRef(seed);
  const subscribe = useCallback(
    (listener: () => void) => store.subscribe(runId, held.current, listener),
    [runId, store],
  );
  const snapshot = useCallback(
    () => store.snapshot(runId, held.current),
    [runId, store],
  );
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

/** Ask the store to try again after it gave up. */
export function useReopen(runId: string, store: RunStore = runStore): () => void {
  return useMemo(
    () => () => {
      store.reopen(runId);
    },
    [runId, store],
  );
}
