import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AutoRefresh } from '@/live/auto-refresh';
import { CHIP_SHAPE } from '@/components/status';
import {
  BACKOFF_MS,
  type StreamHandle,
  type StreamHandlers,
  type StreamSource,
} from '@/live/connection';
import {
  FRESHNESS_STATES,
  REFRESH_INTERVAL_MS,
  STALE_AFTER_FAILURES,
} from '@/live/freshness';

/**
 * The one chip that is on every screen, held to the shape every other chip has.
 *
 * The freshness indicator sits in the utility bar, so it is beside a run's
 * status chip, a credential's chip and a side effect's chip on nearly every
 * page in the console. It was written with its own geometry — a control height
 * and horizontal padding, where a chip has padding on all four sides — and so
 * rendered eight pixels shorter in the box and with its label pressed against
 * the top and bottom edges. Individually trivial; sitting in a row with three
 * chips that were drawn correctly, it is the one that looks wrong, and it is
 * the one a reader sees most often.
 *
 * The assertion is against the shared constant rather than against a list of
 * classes written out here, because a list written out here is a third copy of
 * the geometry and would drift from both.
 *
 * `deploymentSource` is a fake in every test here: `AutoRefresh` now opens a
 * deployment-channel connection on mount, and a test that let it reach the
 * real `fetchStreamSource` would be making a network request from a unit
 * suite — and would pollute `fetch` call counts the timer-fallback tests
 * assert on. The inert fake below opens and does nothing until a test
 * explicitly drives it, which is what a channel that has not connected yet
 * looks like — the same state the timer-fallback tests already assume.
 */

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: () => undefined }),
}));

/** A deployment-channel source a test drives by hand, or leaves inert. */
class FakeDeploymentSource implements StreamSource {
  #handlers: StreamHandlers | null = null;
  readonly closed: boolean[] = [];

  open(_address: string, handlers: StreamHandlers): StreamHandle {
    this.#handlers = handlers;
    return {
      close: () => {
        this.closed.push(true);
      },
    };
  }

  get handlers(): StreamHandlers {
    if (this.#handlers === null) throw new Error('nothing has opened this source');
    return this.#handlers;
  }
}

function deploymentEvent(sequence: number): string {
  return JSON.stringify({
    scope: 'run',
    kind: 'run_started',
    sequence,
    occurred_at: '2026-08-27T12:00:00+00:00',
    payload: { run_id: 'run-0003' },
  });
}

describe('the frame’s freshness chip', () => {
  it('is drawn with the same geometry as every other chip', () => {
    render(<AutoRefresh locale="en" deploymentSource={new FakeDeploymentSource()} />);

    const chip = screen.getByTestId('freshness');
    for (const utility of CHIP_SHAPE.split(' ')) {
      expect([...chip.classList], utility).toContain(utility);
    }
  });

  it('does not set its own height, which is what removed the padding', () => {
    render(<AutoRefresh locale="en" deploymentSource={new FakeDeploymentSource()} />);

    const classes = [...screen.getByTestId('freshness').classList];
    expect(classes).not.toContain('h-control');
  });

  it('draws its mark on the icon scale, like every other status shape', () => {
    render(<AutoRefresh locale="en" deploymentSource={new FakeDeploymentSource()} />);

    // `icon-inline` is the thirteen pixels every `ShapeMark` in the library
    // uses. This mark was eight — a spacing step borrowed for a glyph, which
    // is the exact swap `status.tsx` documents as the thing not to do, because
    // a glyph sized off the spacing scale drifts away from the letters beside
    // it the moment either scale moves.
    const mark = screen.getByTestId('freshness').querySelector('[aria-hidden]');
    expect(mark).not.toBeNull();
    const classes = [...(mark?.classList ?? [])];
    expect(classes).toContain('icon-inline');
    expect(classes).not.toContain('size-2');
  });

  it('declares a state the indicator is allowed to be in', () => {
    render(<AutoRefresh locale="en" deploymentSource={new FakeDeploymentSource()} />);

    const state = screen.getByTestId('freshness').getAttribute('data-state');
    expect(FRESHNESS_STATES as readonly string[]).toContain(state);
  });

  it('reschedules another timer after a successful refresh, while the channel has not connected', async () => {
    vi.useFakeTimers();
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })));

    render(<AutoRefresh locale="en" deploymentSource={new FakeDeploymentSource()} />);

    // First timer fires and settles
    await vi.runOnlyPendingTimersAsync();
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // Let fetch promise and finally block settle so React schedules next timer
    await vi.advanceTimersByTimeAsync(0);

    // Second timer must be scheduled and fire
    await vi.runOnlyPendingTimersAsync();
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    fetchSpy.mockRestore();
    vi.useRealTimers();
  });

  describe('the deployment channel as trigger', () => {
    it('maps connected to live', () => {
      const source = new FakeDeploymentSource();
      render(<AutoRefresh locale="en" deploymentSource={source} />);
      act(() => {
        source.handlers.onOpen();
      });
      expect(screen.getByTestId('freshness').getAttribute('data-state')).toBe('live');
    });

    it('maps a hidden tab to paused, once connected and then hidden', () => {
      const source = new FakeDeploymentSource();
      const originalHidden = Object.getOwnPropertyDescriptor(document, 'hidden');
      const originalVisibilityState = Object.getOwnPropertyDescriptor(
        document,
        'visibilityState',
      );
      let hidden = false;
      // `DeploymentConnection` reads `document.visibilityState` (`connection.ts`'s
      // `documentVisibility`); this component's own legacy timer-suspension
      // watch reads `document.hidden`. Both are mocked together so a single
      // `hidden` toggle drives both consistently, the way a real tab does.
      Object.defineProperty(document, 'hidden', {
        configurable: true,
        get: () => hidden,
      });
      Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        get: () => (hidden ? 'hidden' : 'visible'),
      });
      try {
        render(<AutoRefresh locale="en" deploymentSource={source} />);
        act(() => {
          source.handlers.onOpen();
        });
        expect(screen.getByTestId('freshness').getAttribute('data-state')).toBe('live');

        hidden = true;
        act(() => {
          document.dispatchEvent(new Event('visibilitychange'));
        });
        // The connection's own visibility watcher and the component's are
        // independent listeners on the same browser event; both react to it.
        expect(screen.getByTestId('freshness').getAttribute('data-state')).toBe(
          'paused',
        );
      } finally {
        // Restored unconditionally, not only `if (original…)`: jsdom exposes
        // both of these through a prototype getter rather than an own
        // property, so `getOwnPropertyDescriptor` on the instance found
        // nothing to save in the first place, and skipping the delete here
        // would leave this test's override — `hidden`, a `let` this closure
        // keeps referencing — answering every test that runs after it.
        if (originalHidden) {
          Object.defineProperty(document, 'hidden', originalHidden);
        } else {
          delete (document as { hidden?: boolean }).hidden;
        }
        if (originalVisibilityState) {
          Object.defineProperty(document, 'visibilityState', originalVisibilityState);
        } else {
          delete (document as { visibilityState?: string }).visibilityState;
        }
      }
    });

    it('does not schedule the fallback timer while the channel is connected', async () => {
      vi.useFakeTimers();
      const fetchSpy = vi
        .spyOn(globalThis, 'fetch')
        .mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })));
      const source = new FakeDeploymentSource();

      render(<AutoRefresh locale="en" deploymentSource={source} />);
      source.handlers.onOpen();
      await vi.advanceTimersByTimeAsync(0);

      // Whatever the ordinary re-read interval would have fired by now stays
      // silent: the channel, not the timer, is in charge.
      await vi.advanceTimersByTimeAsync(60_000);
      expect(fetchSpy).not.toHaveBeenCalled();

      fetchSpy.mockRestore();
      vi.useRealTimers();
    });

    it('a batch of events triggers exactly one refresh', async () => {
      vi.useFakeTimers();
      const fetchSpy = vi
        .spyOn(globalThis, 'fetch')
        .mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })));
      const source = new FakeDeploymentSource();

      render(<AutoRefresh locale="en" deploymentSource={source} />);
      source.handlers.onOpen();
      await vi.advanceTimersByTimeAsync(0);
      fetchSpy.mockClear();

      source.handlers.onFrame(deploymentEvent(1));
      source.handlers.onFrame(deploymentEvent(2));
      await vi.advanceTimersByTimeAsync(250);
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      fetchSpy.mockRestore();
      vi.useRealTimers();
    });

    it('a resync triggers refresh immediately, not after the batch window', async () => {
      vi.useFakeTimers();
      const fetchSpy = vi
        .spyOn(globalThis, 'fetch')
        .mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })));
      const source = new FakeDeploymentSource();

      render(<AutoRefresh locale="en" deploymentSource={source} />);
      source.handlers.onOpen();
      await vi.advanceTimersByTimeAsync(0);
      fetchSpy.mockClear();

      source.handlers.onFrame(
        JSON.stringify({ scope: 'control', kind: 'resync', sequence: 0, payload: {} }),
      );
      await vi.advanceTimersByTimeAsync(0);
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      fetchSpy.mockRestore();
      vi.useRealTimers();
    });

    it('the fallback timer resumes the instant the channel drops, not once it gives up', async () => {
      vi.useFakeTimers();
      const fetchSpy = vi
        .spyOn(globalThis, 'fetch')
        .mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })));
      const source = new FakeDeploymentSource();

      render(<AutoRefresh locale="en" deploymentSource={source} />);
      source.handlers.onOpen();
      await vi.advanceTimersByTimeAsync(0);
      fetchSpy.mockClear();

      // The channel drops once -- reconnecting, not yet exhausted.
      source.handlers.onError(0);
      await vi.advanceTimersByTimeAsync(0);
      expect(screen.getByTestId('freshness').getAttribute('data-state')).toBe(
        'refreshing',
      );

      // The fallback timer is already covering: the ordinary interval fires
      // well within SC-002's thirty-second bound, long before ten
      // reconnection attempts could exhaust themselves. Advanced by name
      // rather than drained by `runOnlyPendingTimersAsync`, which would also
      // run the connection's own, unrelated backoff retry.
      await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
      expect(fetchSpy).toHaveBeenCalled();

      fetchSpy.mockRestore();
      vi.useRealTimers();
    });

    it('refreshes once when the channel comes back, because the drop was a gap', async () => {
      // The hole this pins shut. A drop shorter than `REFRESH_INTERVAL_MS`
      // used to cost nothing and lose everything: the fallback timer was
      // scheduled on the drop and cleared again the moment the channel
      // reached `connected`, so it never fired, and reaching `connected`
      // refreshed nothing on its own. Whatever the deployment published in
      // between reached a connection that had gone, the chip read `live`,
      // and the screen stayed stale with no upper bound at all -- past this
      // feature's own thirty-second freshness claim.
      vi.useFakeTimers();
      const fetchSpy = vi
        .spyOn(globalThis, 'fetch')
        .mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })));
      const source = new FakeDeploymentSource();

      render(<AutoRefresh locale="en" deploymentSource={source} />);
      // Wrapped, unlike the fetch-counting tests around it, because this one
      // also reads the chip: a state update raised from outside `act` is
      // applied a flush later than the assertion would see it.
      act(() => {
        source.handlers.onOpen();
      });
      await vi.advanceTimersByTimeAsync(0);
      fetchSpy.mockClear();

      act(() => {
        source.handlers.onError(0);
      });
      // The first backoff step, which is well under the fallback interval --
      // so the timer is provably not what produces the refresh below.
      await vi.advanceTimersByTimeAsync(BACKOFF_MS[0] ?? 0);
      act(() => {
        source.handlers.onOpen();
      });
      await vi.advanceTimersByTimeAsync(0);

      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId('freshness').getAttribute('data-state')).toBe('live');

      // Exactly one: the channel is delivering again, so the fallback stays
      // suspended and nothing re-reads a second time.
      await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      fetchSpy.mockRestore();
      vi.useRealTimers();
    });

    it('does not refresh on a first connection, which the server has already answered', async () => {
      // The other half of the same seam, and the reason it is not simply
      // "refresh whenever the channel opens": this component mounts inside a
      // page the server rendered moments ago. A re-read there would buy
      // nothing and cost one round trip on every navigation in the console.
      vi.useFakeTimers();
      const fetchSpy = vi
        .spyOn(globalThis, 'fetch')
        .mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })));
      const source = new FakeDeploymentSource();

      render(<AutoRefresh locale="en" deploymentSource={source} />);
      source.handlers.onOpen();
      await vi.advanceTimersByTimeAsync(0);

      expect(fetchSpy).not.toHaveBeenCalled();

      fetchSpy.mockRestore();
      vi.useRealTimers();
    });

    it('marks the chip stale once attempts cross STALE_AFTER_FAILURES, not merely refreshing', async () => {
      // Regression pin for the bug the acceptance spec's own run against the
      // local mock harness caught: `freshnessFromConnection` used to map
      // `reconnecting` to `refreshing` unconditionally, and
      // MAX_RECONNECTIONS/BACKOFF_MS sum to roughly fifty-five seconds of
      // backoff — past SC-002's thirty-second fallback bound — so the chip
      // never reached `stale` at all. Below the threshold it must still say
      // `refreshing`; at the threshold it must say `stale`.
      vi.useFakeTimers();
      const source = new FakeDeploymentSource();

      render(<AutoRefresh locale="en" deploymentSource={source} />);

      for (let attempt = 1; attempt < STALE_AFTER_FAILURES; attempt += 1) {
        source.handlers.onError(0);
        await vi.advanceTimersByTimeAsync(0);
        expect(screen.getByTestId('freshness').getAttribute('data-state')).toBe(
          'refreshing',
        );
      }

      source.handlers.onError(0);
      await vi.advanceTimersByTimeAsync(0);
      expect(screen.getByTestId('freshness').getAttribute('data-state')).toBe('stale');

      vi.useRealTimers();
    });

    it('closes the connection on unmount', () => {
      const source = new FakeDeploymentSource();
      const { unmount } = render(<AutoRefresh locale="en" deploymentSource={source} />);
      source.handlers.onOpen();
      unmount();
      expect(source.closed).toEqual([true]);
    });
  });
});
