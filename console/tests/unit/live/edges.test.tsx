import { act as reactAct, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { act } from '@/live/act';
import { attentionFrom } from '@/live/attention';
import { Announcer } from '@/live/announcer';
import { RunConnection } from '@/live/connection';
import { cursorOf, positionIn } from '@/live/cursor';
import { eventFrom, eventFromFrame, type StreamEvent } from '@/live/events';
import { AnswerControls, TakeoverControls } from '@/live/controls';
import { InvestigateDrawer } from '@/live/investigate';
import { listOf, receive, settle, type ListRules } from '@/live/lists';
import { attempt, refused, resting } from '@/live/optimism';
import { applyEvent, openCount, openRun, waitingFor } from '@/live/reducer';
import { framesIn } from '@/live/sse';
import { RunStore } from '@/live/store';

/**
 * The edges: the answers this layer gives when it is handed something wrong.
 *
 * Every one of these is a case a deployment can actually produce — a frame that
 * is not JSON, an event with no payload, a run that reports a status nobody has
 * heard of, a console process that has itself gone away. None of them may take
 * the transcript with it, and each of them has exactly one right answer, so
 * each of them is asserted rather than assumed.
 */

afterEach(() => {
  vi.unstubAllGlobals();
});

/** The event a wire document describes, or a failure naming the document. */
function must(document: unknown): StreamEvent {
  const event = eventFrom(document);
  if (event === null)
    throw new Error(`not a stream event: ${JSON.stringify(document)}`);
  return event;
}

describe('a frame the console cannot read', () => {
  it('is skipped rather than raised on', () => {
    expect(eventFromFrame('')).toBeNull();
    expect(eventFromFrame('not json at all')).toBeNull();
    expect(eventFromFrame('"a string"')).toBeNull();
    expect(eventFrom({ run_id: 'run-3' })).toBeNull();
    expect(eventFrom({ sequence: 1 })).toBeNull();
    // A sequence has to be a whole number; a fractional one is not a position.
    expect(eventFrom({ run_id: 'run-3', sequence: 1.5 })).toBeNull();
  });

  it('carries an empty payload rather than nothing when the deployment sent none', () => {
    const event = eventFromFrame(JSON.stringify({ run_id: 'run-3', sequence: 0 }));

    expect(event?.payload).toEqual({});
    expect(event?.kind).toBe('');
    expect(event?.occurredAt).toBe('');
  });

  it('reads a frame with no colon in a line, and one with several data lines', () => {
    const { frames } = framesIn('id\ndata: one\ndata: two\nunknown: x\n\n');

    expect(frames[0]?.data).toBe('one\ntwo');
    expect(frames[0]?.id).toBe('');
  });

  it('reads frames however the sender ends its lines', () => {
    const { frames } = framesIn('id: run-3:1\r\ndata: {}\r\n\r\n');

    expect(frames[0]?.id).toBe('run-3:1');
  });

  it('skips a blank block rather than reporting an event with nothing in it', () => {
    expect(framesIn('\n\ndata: {}\n\n').frames).toHaveLength(1);
  });
});

describe('a cursor that is not one', () => {
  it('reads as nothing seen, whatever it says', () => {
    expect(positionIn('run-3:not-a-number', 'run-3')).toBe(-1);
    expect(positionIn('run-3:-4', 'run-3')).toBe(-1);
    expect(positionIn(':4', 'run-3')).toBe(-1);
    expect(cursorOf('', 4)).toBe('');
  });
});

describe('a run reporting something the console has not met', () => {
  it('treats an unrecognised terminal status as a completion rather than as still running', () => {
    const state = applyEvent(
      openRun('run-3'),
      must({
        run_id: 'run-3',
        kind: 'run_finished',
        sequence: 0,
        payload: { status: 'wound-down' },
      }),
    );

    expect(state.phase).toBe('completed');
  });

  it('opens a question as a question, and counts what is still waiting', () => {
    const state = applyEvent(
      openRun('run-3'),
      must({
        run_id: 'run-3',
        kind: 'interaction_opened',
        sequence: 0,
        payload: {
          interaction_id: 'int-1',
          text: 'which datastore?',
          options: ['a', 'b'],
        },
      }),
    );

    expect(waitingFor(state, 'int-1')?.kind).toBe('question');
    expect(waitingFor(state, 'int-1')?.options).toEqual(['a', 'b']);
    expect(openCount(state)).toBe(1);
    expect(
      attentionFrom(state, { approval: 'A', question: 'Q', elsewhere: 'x' })[0]?.title,
    ).toBe('Q');
  });

  it('does not open the same interaction twice, or close one it never opened', () => {
    const opened = {
      run_id: 'run-3',
      kind: 'approval_requested',
      payload: { approval_id: 'ap-1' },
    };

    let state = applyEvent(openRun('run-3'), must({ ...opened, sequence: 0 }));
    state = applyEvent(state, must({ ...opened, sequence: 1 }));
    state = applyEvent(
      state,
      must({ run_id: 'run-3', kind: 'attention_changed', sequence: 2, payload: {} }),
    );

    expect(state.waiting).toHaveLength(1);
    expect(state.decided).toHaveLength(0);
  });
});

describe('a connection nobody injected time or a tab into', () => {
  it('uses the browser’s own, and still closes completely', () => {
    const opened: string[] = [];
    const connection = new RunConnection({
      runId: 'run-3',
      source: {
        open: (address) => {
          opened.push(address);
          return { close: () => undefined };
        },
      },
      cursor: () => '',
      onState: () => undefined,
      onEvents: () => undefined,
    });

    connection.open();
    // A second open is not a second stream: the screen is already watching.
    connection.open();
    connection.close();

    expect(opened).toHaveLength(1);
    expect(connection.state).toBe('disconnected');
  });

  it('does nothing at all once it has been closed', () => {
    const connection = new RunConnection({
      runId: 'run-3',
      source: { open: () => ({ close: () => undefined }) },
      cursor: () => '',
      onState: () => undefined,
      onEvents: () => undefined,
    });
    connection.close();

    connection.open();

    expect(connection.state).toBe('disconnected');
    expect(connection.attempts).toBe(0);
  });
});

describe('a store nobody injected time or a tab into', () => {
  it('opens through the browser’s own timer and visibility, and tears both down', () => {
    vi.useFakeTimers();
    let closed = 0;
    const store = new RunStore({
      source: {
        open: () => ({
          close: () => {
            closed += 1;
          },
        }),
      },
    });

    const stop = store.subscribe('run-3', {}, () => undefined);
    document.dispatchEvent(new Event('visibilitychange'));
    vi.runOnlyPendingTimers();
    stop();

    expect(closed).toBe(1);
    vi.useRealTimers();
  });

  it('has nothing to reopen for a run nobody is watching', () => {
    const store = new RunStore({
      source: { open: () => ({ close: () => undefined }) },
    });

    // A no-op rather than an error: the screen that asked has already gone, and
    // a throw here would take an unmounting page down with it.
    expect(() => {
      store.reopen('run-3');
    }).not.toThrow();
  });
});

describe('a list with nothing in it', () => {
  interface Row {
    readonly id: string;
    readonly age: number;
  }
  const rules: ListRules<Row> = {
    identify: (row) => row.id,
    order: (first, second) => first.age - second.age,
  };

  it('settles to itself rather than to a new list', () => {
    const empty = listOf<Row>([], rules);

    expect(settle(empty, rules)).toBe(empty);
  });

  it('reorders on an update when nobody is pointing at it', () => {
    const held = listOf(
      [
        { id: 'a', age: 1 },
        { id: 'b', age: 2 },
      ],
      rules,
    );

    const after = receive(held, { id: 'a', age: 9 }, rules, false);

    expect(after.items.map((row) => row.id)).toEqual(['b', 'a']);
  });

  it('puts the list back in order when it settles with nothing pending', () => {
    const held = listOf([{ id: 'a', age: 1 }], rules);

    expect(settle(held, rules).items).toHaveLength(1);
  });
});

describe('an optimistic write with nothing behind it', () => {
  it('reverts to what it is showing rather than to nothing at all', () => {
    // A refusal of a write nobody attempted: the value stands, and the reason
    // is still stated. Reverting to `null` would blank the control instead.
    expect(refused(resting('a'), 'no').value).toBe('a');
    expect(attempt(resting('a'), 'b').snapshot).toBe('a');
  });
});

describe('the console’s own process going away', () => {
  it('reads as unreachable rather than as a refusal', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('the console has no server'))),
    );

    const applied = await act('/api/run', { runId: 'run-3', action: 'cancel' });

    expect(applied.ok).toBe(false);
    expect(applied.reachable).toBe(false);
  });

  it('reads a body that is not JSON as an answer with nothing in it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('not json', { status: 200 }))),
    );

    const applied = await act('/api/run', { runId: 'run-3', action: 'cancel' });

    expect(applied.ok).toBe(true);
    expect(applied.reason).toBe('');
    expect(applied.runId).toBe('');
  });
});

describe('announcing and dismissing', () => {
  it('shows nothing when nothing has happened, and removes what is dismissed', async () => {
    const dropped: string[] = [];
    const outcome = {
      id: 'a',
      role: 'success' as const,
      message: 'it worked',
      recordedAt: { href: '/runs/run-3', label: 'in the transcript' },
    };

    const view = render(
      <Announcer locale="en" outcomes={[]} onDismiss={() => undefined} />,
    );
    expect(screen.queryByTestId('outcomes')).toBeNull();
    view.unmount();

    render(
      <Announcer
        locale="en"
        outcomes={[outcome]}
        onDismiss={(id) => dropped.push(id)}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /dismiss/i }));

    expect(dropped).toEqual(['a']);
  });
});

describe('the investigation drawer when the deployment refuses', () => {
  it('stays open and says why, rather than going somewhere that does not exist', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ reason: 'this deployment is shutting down' }), {
            status: 400,
          }),
        ),
      ),
    );
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

    expect(went).toEqual([]);
    expect(await screen.findByTestId('outcomes')).toHaveTextContent('shutting down');
    // The refusal is recorded where somebody looks when they are sure they
    // pressed the button.
    expect(screen.getByRole('link', { name: /audit/i })).toHaveAttribute(
      'href',
      '/audit',
    );
  });

  it('goes to the new run through the router when nobody injected a navigation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ runId: 'run-9' }), { status: 200 }),
        ),
      ),
    );
    let closed = false;

    render(
      <InvestigateDrawer
        open
        locale="en"
        onClose={() => {
          closed = true;
        }}
      />,
    );
    await userEvent.type(
      screen.getByLabelText(/looked into/i),
      'the primary is unreachable',
    );
    await reactAct(async () => {
      await userEvent.click(screen.getByTestId('start-investigation'));
    });

    // The router is the suite's own floor mock, so what is observable here is
    // the success path being taken at all: the drawer closes and nothing is
    // announced, which is the shape only a start that worked produces.
    expect(closed).toBe(true);
    expect(screen.queryByTestId('outcomes')).toBeNull();
  });
});

describe('steering a run that will not be steered', () => {
  it('gives control back when a hand-back is refused, rather than losing it', async () => {
    const answers = [
      new Response(JSON.stringify({ applied: true }), { status: 200 }),
      new Response(JSON.stringify({ reason: 'nobody has this run' }), { status: 409 }),
    ];
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(answers.shift() ?? new Response('{}', { status: 200 })),
      ),
    );
    render(<TakeoverControls runId="run-3" locale="en" running />);

    await userEvent.click(screen.getByTestId('take-over'));
    await userEvent.click(await screen.findByTestId('hand-back'));

    // Still held: the deployment refused to take it back, so the screen must
    // not say the agent has it.
    expect(await screen.findByTestId('hand-back')).toBeInTheDocument();
    expect(screen.getByTestId('takeover')).toHaveAttribute('data-held', 'true');
  });

  it('stops the run once the confirmation is confirmed, and not before', async () => {
    const fetching = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ applied: true }), { status: 200 })),
    );
    vi.stubGlobal('fetch', fetching);
    render(<TakeoverControls runId="run-3" locale="en" running />);

    await userEvent.click(screen.getByTestId('stop-run'));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(
      within(dialog).getByRole('button', { name: /stop this investigation/i }),
    );

    expect(fetching.mock.calls.length).toBeGreaterThan(0);
    expect(await screen.findByTestId('outcomes')).toBeInTheDocument();
  });

  it('keeps the run when the confirmation is declined', async () => {
    const fetching = vi.fn(() => Promise.resolve(new Response('{}', { status: 200 })));
    vi.stubGlobal('fetch', fetching);
    render(<TakeoverControls runId="run-3" locale="en" running />);

    await userEvent.click(screen.getByTestId('stop-run'));
    await userEvent.click(screen.getByRole('button', { name: /leave it running/i }));

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(fetching.mock.calls).toHaveLength(0);
  });

  it('answers with an option without anybody typing one', async () => {
    const fetching = vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ answered: true }), { status: 200 }),
      ),
    );
    vi.stubGlobal('fetch', fetching);
    render(
      <AnswerControls
        runId="run-3"
        locale="en"
        interactionId="int-1"
        question="Which datastore?"
        options={['the guest volume']}
      />,
    );

    await userEvent.click(screen.getByTestId('answer-option'));

    expect(await screen.findByTestId('answered')).toBeInTheDocument();
  });
});
