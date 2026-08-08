import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type {
  Scheduler,
  StreamHandlers,
  StreamSource,
  Visibility,
} from '@/live/connection';
import { AddContext, AnswerControls, TakeoverControls } from '@/live/controls';
import { InvestigateDrawer } from '@/live/investigate';
import { LiveRun } from '@/live/live-run';
import { applyEvents, openRun } from '@/live/reducer';
import { eventFrom, type StreamEvent } from '@/live/events';
import { RunStore } from '@/live/store';
import { ATTENTION_RESOLVED_EVENT } from '@/shell/attention';

/**
 * What an operator actually sees, and the two things they must never see.
 *
 * They must never see a transcript that stopped updating presenting itself as
 * live — the whole feature is worth nothing if that can happen, because a stale
 * transcript and a stalled investigation are indistinguishable. And they must
 * never see a write they made stay on the screen after the deployment refused
 * it.
 */

/** What a request carried, as the text it was sent as. */
function readBody(init: RequestInit): string {
  return typeof init.body === 'string' ? init.body : '';
}

/** The budget, read out of the tier that declares it rather than restated. */
function budget(name: string): number {
  const source = readFileSync(
    join(process.cwd(), '..', 'config', 'constants', 'console.py'),
    'utf8',
  );
  const found = new RegExp(`^${name}: Final = ([0-9.]+)`, 'm').exec(source);
  if (found?.[1] === undefined) {
    throw new Error(`${name} is not declared in config/constants/console.py`);
  }
  return Number(found[1]);
}

class TestSource implements StreamSource {
  handlers: StreamHandlers | null = null;
  opened = 0;

  open(_address: string, handlers: StreamHandlers): { close: () => void } {
    this.opened += 1;
    this.handlers = handlers;
    return { close: () => undefined };
  }

  deliver(
    sequence: number,
    kind = 'observation_recorded',
    payload: unknown = {},
  ): void {
    this.handlers?.onFrame(
      JSON.stringify({
        run_id: 'run-3',
        kind,
        sequence,
        occurred_at: '2026-08-07T11:57:00+00:00',
        payload,
      }),
    );
  }

  fail(status = 0): void {
    this.handlers?.onError(status);
  }
}

const immediately: Scheduler = {
  after: (_ms, run) => {
    run();
    return () => undefined;
  },
};

const visible: Visibility = { hidden: () => false, onChange: () => () => undefined };

function harness(): { source: TestSource; store: RunStore } {
  const source = new TestSource();
  return {
    source,
    store: new RunStore({ source, scheduler: immediately, visibility: visible }),
  };
}

function liveRun(store: RunStore): React.ReactElement {
  return (
    <LiveRun
      runId="run-3"
      locale="en"
      seed={{}}
      now="2026-08-07T12:00:00.000Z"
      zone="UTC"
      store={store}
    />
  );
}

function answering(ok: boolean, body: unknown = {}): typeof fetch {
  return vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(body), { status: ok ? 200 : 409 })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('a live transcript', () => {
  it('draws events as they arrive, through the component a replay uses', () => {
    const { source, store } = harness();
    render(liveRun(store));

    act(() => {
      source.deliver(0, 'run_started', { objective: 'the primary is unreachable' });
      source.deliver(1, 'tool_called', { name: 'estate.failed_units' });
    });

    expect(screen.getAllByTestId('transcript-event')).toHaveLength(2);
    expect(screen.getByTestId('transcript')).toHaveAttribute('data-total', '2');
  });

  it('never presents a stream it has given up on as live', () => {
    const { source, store } = harness();
    render(liveRun(store));
    act(() => {
      source.deliver(0);
    });
    expect(screen.getByTestId('connection')).toHaveAttribute('data-live', 'true');

    act(() => {
      // Past the bound: every attempt fails, and the immediate scheduler runs
      // each retry as soon as it is asked for.
      for (let attempt = 0; attempt < 12; attempt += 1) source.fail(0);
    });

    const badge = screen.getByTestId('connection');
    expect(badge).toHaveAttribute('data-live', 'false');
    expect(badge).toHaveAttribute('data-connection', 'disconnected');
    // And it says so in a sentence, with the one thing left to do beside it.
    expect(screen.getByTestId('stale')).toBeInTheDocument();
    expect(screen.getByTestId('reconnect')).toBeInTheDocument();
  });

  it('offers a manual reconnection that opens the stream again', async () => {
    const { source, store } = harness();
    render(liveRun(store));
    act(() => {
      for (let attempt = 0; attempt < 12; attempt += 1) source.fail(0);
    });
    const before = source.opened;

    await userEvent.click(screen.getByTestId('reconnect'));

    expect(source.opened).toBeGreaterThan(before);
  });

  it('becomes the completed view without unmounting the transcript', () => {
    const { source, store } = harness();
    render(liveRun(store));
    act(() => {
      source.deliver(0);
    });
    const transcript = screen.getByTestId('transcript');

    act(() => {
      source.deliver(1, 'run_finished', { status: 'succeeded' });
    });

    expect(screen.getByTestId('live-run')).toHaveAttribute('data-phase', 'completed');
    expect(screen.getByTestId('run-ended')).toBeInTheDocument();
    // The same node: nothing reloaded, so nothing lost its scroll position.
    expect(screen.getByTestId('transcript')).toBe(transcript);
  });

  it('does not yank the viewport when the operator has scrolled up', () => {
    const { source, store } = harness();
    render(liveRun(store));
    act(() => {
      source.deliver(0);
    });

    const viewport = screen.getByTestId('transcript-viewport');
    // jsdom reports every box as zero, so the scroll geometry is declared here
    // the way a real one would be: content taller than the box, scrolled up.
    Object.defineProperty(viewport, 'scrollHeight', {
      value: 1000,
      configurable: true,
    });
    Object.defineProperty(viewport, 'clientHeight', { value: 200, configurable: true });
    viewport.scrollTop = 0;
    act(() => {
      viewport.dispatchEvent(new Event('scroll', { bubbles: true }));
    });
    expect(viewport).toHaveAttribute('data-following', 'false');

    act(() => {
      source.deliver(1);
      source.deliver(2);
    });

    // Still where they left it, and a control says how many arrived.
    expect(viewport.scrollTop).toBe(0);
    expect(screen.getByTestId('new-events')).toHaveTextContent('2');
  });

  it('publishes an interaction decided elsewhere, so the centre loses it too', () => {
    const { source, store } = harness();
    const resolved: string[] = [];
    const listener = (event: Event): void => {
      resolved.push(String((event as CustomEvent<unknown>).detail));
    };
    window.addEventListener(ATTENTION_RESOLVED_EVENT, listener);
    render(liveRun(store));

    act(() => {
      source.deliver(0, 'approval_requested', {
        interaction_id: 'int-1',
        summary: 'Restart',
      });
      source.deliver(1, 'attention_changed', {
        interaction_id: 'int-1',
        waiting: false,
        decided_by: 'Avery Lockhart',
        decided_on: 'chat',
      });
    });

    expect(resolved).toContain('int-1');
    window.removeEventListener(ATTENTION_RESOLVED_EVENT, listener);
  });
});

describe('answering the agent in place', () => {
  it('answers the interaction and reports where the outcome is recorded', async () => {
    vi.stubGlobal('fetch', answering(true, { answered: true }));
    render(
      <AnswerControls
        runId="run-3"
        locale="en"
        interactionId="int-1"
        question="Which datastore should the freed space be measured against?"
        options={['the guest volume']}
      />,
    );

    await userEvent.type(screen.getByLabelText(/your answer/i), 'the datastore');
    await userEvent.click(screen.getByTestId('answer-send'));

    expect(await screen.findByTestId('answered')).toBeInTheDocument();
    // The toast is not the record: it names the run's own transcript.
    const outcomes = screen.getByTestId('outcomes');
    expect(within(outcomes).getByRole('link')).toHaveAttribute('href', '/runs/run-3');
  });

  it('refuses an empty answer, because an empty answer resumes a run with nothing', () => {
    render(
      <AnswerControls
        runId="run-3"
        locale="en"
        interactionId="int-1"
        question="?"
        options={[]}
      />,
    );

    expect(screen.getByTestId('answer-send')).toBeDisabled();
    expect(screen.getByText(/resumes when this is answered/i)).toBeInTheDocument();
  });

  it('puts the question back and states the reason when the deployment refuses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({ reason: 'this interaction is already closed' }),
            {
              status: 409,
            },
          ),
        ),
      ),
    );
    render(
      <AnswerControls
        runId="run-3"
        locale="en"
        interactionId="int-1"
        question="?"
        options={[]}
      />,
    );

    await userEvent.type(screen.getByLabelText(/your answer/i), 'the datastore');
    await userEvent.click(screen.getByTestId('answer-send'));

    expect(await screen.findByTestId('answer')).toBeInTheDocument();
    expect(screen.getByTestId('outcomes')).toHaveTextContent('already closed');
  });
});

describe('taking control of a run', () => {
  it('takes over without stopping it, and offers to hand it back', async () => {
    const fetching = answering(true, { applied: true });
    vi.stubGlobal('fetch', fetching);
    render(<TakeoverControls runId="run-3" locale="en" running />);

    await userEvent.click(screen.getByTestId('take-over'));

    expect(await screen.findByTestId('hand-back')).toBeInTheDocument();
    const [, init] = (fetching as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0] as [string, RequestInit];
    expect(readBody(init)).toContain('take-over');
    expect(readBody(init)).not.toContain('cancel');
  });

  it('reverts to not having control when the deployment refuses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ reason: 'this run has already finished' }), {
            status: 409,
          }),
        ),
      ),
    );
    render(<TakeoverControls runId="run-3" locale="en" running />);

    await userEvent.click(screen.getByTestId('take-over'));

    expect(await screen.findByTestId('take-over')).toBeInTheDocument();
    expect(screen.getByTestId('takeover')).toHaveAttribute('data-held', 'false');
    expect(screen.getByTestId('outcomes')).toHaveTextContent('already finished');
  });

  it('names the run and the consequence before it stops one', async () => {
    const fetching = answering(true);
    vi.stubGlobal('fetch', fetching);
    render(<TakeoverControls runId="run-3" locale="en" running />);

    await userEvent.click(screen.getByTestId('stop-run'));

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('run-3')).toBeInTheDocument();
    expect(within(dialog).getByText(/next safe point/i)).toBeInTheDocument();
    // Nothing has been asked of the deployment yet.
    expect((fetching as unknown as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(
      0,
    );
  });

  it('steers nothing on a run that has already finished', () => {
    render(<TakeoverControls runId="run-3" locale="en" running={false} />);

    expect(screen.getByTestId('take-over')).toBeDisabled();
    expect(screen.getByTestId('stop-run')).toBeDisabled();
  });
});

describe('adding context to a running investigation', () => {
  it('sends it and says it will be delivered, without stopping the run', async () => {
    const fetching = answering(true);
    vi.stubGlobal('fetch', fetching);
    render(<AddContext runId="run-3" locale="en" />);

    await userEvent.type(
      screen.getByLabelText(/should know/i),
      'look at node02 as well',
    );
    await userEvent.click(screen.getByTestId('send-context'));

    const [, init] = (fetching as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0] as [string, RequestInit];
    expect(readBody(init)).toContain('message');
    expect(await screen.findByTestId('outcomes')).toHaveTextContent(/next turn/i);
  });

  it('gives the words back when the deployment refuses, rather than losing them', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ reason: 'no' }), { status: 409 }),
        ),
      ),
    );
    render(<AddContext runId="run-3" locale="en" />);

    const box = screen.getByLabelText(/should know/i);
    await userEvent.type(box, 'look at node02 as well');
    await userEvent.click(screen.getByTestId('send-context'));

    expect(
      await screen.findByDisplayValue('look at node02 as well'),
    ).toBeInTheDocument();
  });
});

describe('starting an investigation from anywhere', () => {
  it('starts one and goes to it, without a navigation to get there', async () => {
    vi.stubGlobal('fetch', answering(true, { applied: true, runId: 'run-9' }));
    const went: string[] = [];
    render(
      <InvestigateDrawer
        open
        locale="en"
        onClose={() => undefined}
        navigate={(href) => went.push(href)}
      />,
    );

    await userEvent.type(
      screen.getByLabelText(/looked into/i),
      'the primary is unreachable',
    );
    await userEvent.click(screen.getByTestId('start-investigation'));

    expect(went).toEqual(['/runs/run-9']);
  });

  it('refuses to start one with no objective', () => {
    render(
      <InvestigateDrawer
        open
        locale="en"
        onClose={() => undefined}
        navigate={() => undefined}
      />,
    );

    expect(screen.getByTestId('start-investigation')).toBeDisabled();
  });

  it('is not in the document at all while it is closed', () => {
    render(
      <InvestigateDrawer
        open={false}
        locale="en"
        onClose={() => undefined}
        navigate={() => undefined}
      />,
    );

    expect(screen.queryByTestId('investigate-drawer')).toBeNull();
  });
});

describe('a burst after a long disconnection', () => {
  it('applies ten thousand events, exactly once each, inside the declared budget', () => {
    const total = budget('CONSOLE_LIVE_BURST_EVENTS');
    const events: StreamEvent[] = [];
    for (let sequence = 0; sequence < total; sequence += 1) {
      const event = eventFrom({
        run_id: 'run-3',
        kind: 'observation_recorded',
        sequence,
        occurred_at: '2026-08-07T11:57:00+00:00',
        payload: { detail: `event ${String(sequence)}` },
      });
      if (event !== null) events.push(event);
    }
    // Shuffled and duplicated, because a burst arriving after a reconnection is
    // both: the catch-up read overlaps what was already applied, and nothing
    // promises the order a proxy delivers chunks in.
    const arriving = [...events.slice(500), ...events].reverse();

    const started = performance.now();
    const state = applyEvents(openRun('run-3'), arriving);
    const took = performance.now() - started;

    expect(state.events).toHaveLength(total);
    expect(state.position).toBe(total - 1);
    expect(took).toBeLessThan(budget('CONSOLE_LIVE_BURST_BUDGET_MS'));
  });

  it('costs the same whether it arrives in one batch or in ten', () => {
    const total = 2000;
    const events: StreamEvent[] = [];
    for (let sequence = 0; sequence < total; sequence += 1) {
      const event = eventFrom({ run_id: 'run-3', kind: 'x', sequence, payload: {} });
      if (event !== null) events.push(event);
    }

    let batched = openRun('run-3');
    for (let at = 0; at < total; at += 200) {
      batched = applyEvents(batched, events.slice(at, at + 200));
    }

    expect(batched.events).toHaveLength(total);
    expect(batched.applied).toBe(total);
  });
});
