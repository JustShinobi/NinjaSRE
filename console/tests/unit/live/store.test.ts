import { describe, expect, it } from 'vitest';

import { attentionFrom, decidedElsewhere } from '@/live/attention';
import type {
  Scheduler,
  StreamHandlers,
  StreamSource,
  Visibility,
} from '@/live/connection';
import { arrivedCount, listOf, receive, settle, type ListRules } from '@/live/lists';
import {
  attempt,
  confirmed,
  isPending,
  refused,
  resting,
  superseded,
} from '@/live/optimism';
import { announce, dismiss, OUTCOME_LIMIT, type Outcome } from '@/live/outcomes';
import { RunStore } from '@/live/store';

/**
 * The store, the optimism and the two shapes of live data around them.
 *
 * The claim the store carries is fan-out: a page with four consumers of one run
 * opens one stream, and the four cannot disagree about what has arrived because
 * there is one place the answer lives. The claim optimism carries is that a
 * refusal puts back what was there and says why — the failure mode being that a
 * screen goes on asserting something the deployment refused.
 */

class RecordingSource implements StreamSource {
  opened = 0;
  closed = 0;
  handlers: StreamHandlers | null = null;

  open(_address: string, handlers: StreamHandlers): { close: () => void } {
    this.opened += 1;
    this.handlers = handlers;
    return {
      close: () => {
        this.closed += 1;
      },
    };
  }

  deliver(
    sequence: number,
    kind = 'observation_recorded',
    payload: unknown = {},
  ): void {
    this.handlers?.onFrame(
      JSON.stringify({ run_id: 'run-3', kind, sequence, occurred_at: '', payload }),
    );
  }
}

class ImmediateClock implements Scheduler {
  after(_ms: number, run: () => void): () => void {
    run();
    return () => undefined;
  }
}

const alwaysVisible: Visibility = {
  hidden: () => false,
  onChange: () => () => undefined,
};

function store(source: RecordingSource): RunStore {
  return new RunStore({
    source,
    scheduler: new ImmediateClock(),
    visibility: alwaysVisible,
  });
}

describe('one subscription per run', () => {
  it('opens one stream for a page with four consumers of the same run', () => {
    const source = new RecordingSource();
    const held = store(source);
    const stops = [0, 1, 2, 3].map(() => held.subscribe('run-3', {}, () => undefined));

    expect(source.opened).toBe(1);
    expect(held.opened).toBe(1);

    for (const stop of stops) stop();
  });

  it('closes it when the last screen watching it goes, and not before', () => {
    const source = new RecordingSource();
    const held = store(source);
    const first = held.subscribe('run-3', {}, () => undefined);
    const second = held.subscribe('run-3', {}, () => undefined);

    first();
    expect(source.closed).toBe(0);

    second();
    expect(source.closed).toBe(1);
  });

  it('hands every consumer the same events, so none of them can be behind', () => {
    const source = new RecordingSource();
    const held = store(source);
    let seen = 0;
    const stops = [0, 1, 2].map(() =>
      held.subscribe('run-3', {}, () => {
        seen += 1;
      }),
    );

    source.deliver(0);

    expect(held.snapshot('run-3').live.events).toHaveLength(1);
    // Three listeners, one state change each: one stream, one reducer, one
    // answer to "what has arrived".
    expect(seen).toBeGreaterThanOrEqual(3);

    for (const stop of stops) stop();
  });

  it('joins a run in progress rather than resetting it to a later seed', () => {
    const source = new RecordingSource();
    const held = store(source);
    const first = held.subscribe('run-3', {}, () => undefined);
    source.deliver(0);

    const second = held.subscribe('run-3', { position: 99 }, () => undefined);

    expect(held.snapshot('run-3').live.position).toBe(0);

    first();
    second();
  });

  it('returns the same resting snapshot for a run nobody is watching', () => {
    const held = store(new RecordingSource());

    // Identity, not equality: React compares snapshots by reference, and a
    // fresh object each call is a render loop with no events in it.
    expect(held.snapshot('run-3')).toBe(held.snapshot('run-3'));
  });

  it('reopens on request after it has given up, keeping what is on screen', () => {
    const source = new RecordingSource();
    const held = store(source);
    const stop = held.subscribe('run-3', {}, () => undefined);
    source.deliver(0);

    held.reopen('run-3');

    expect(source.opened).toBe(2);
    expect(held.snapshot('run-3').live.events).toHaveLength(1);
    stop();
  });
});

describe('the notification centre and the screens', () => {
  it('cannot disagree, because the count is the length of the one list', () => {
    const source = new RecordingSource();
    const held = store(source);
    const stop = held.subscribe('run-3', {}, () => undefined);

    source.deliver(0, 'approval_requested', {
      interaction_id: 'int-1',
      summary: 'Restart the hardening unit',
    });
    source.deliver(1, 'approval_requested', {
      interaction_id: 'int-2',
      summary: 'Reclaim the datastore',
    });
    source.deliver(2, 'attention_changed', {
      interaction_id: 'int-1',
      waiting: false,
      decided_by: 'Avery Lockhart',
      decided_on: 'chat',
    });

    const labels = {
      approval: 'Approval',
      question: 'Question',
      elsewhere: 'elsewhere',
    };
    const items = attentionFrom(held.snapshot('run-3').live, labels);

    expect(items.map((item) => item.id)).toEqual(['int-2']);
    expect(items).toHaveLength(1);
    stop();
  });

  it('says who decided one, and says something when the deployment did not', () => {
    const labels = {
      approval: 'Approval',
      question: 'Question',
      elsewhere: 'somewhere else',
    };

    expect(decidedElsewhere('Avery Lockhart', 'chat', labels)).toBe(
      'Avery Lockhart · chat',
    );
    expect(decidedElsewhere('Avery Lockhart', '', labels)).toBe('Avery Lockhart');
    expect(decidedElsewhere('', 'chat', labels)).toBe('chat');
    // Never blank: a card that closed with nothing on it reads as one the
    // person looking at it closed themselves.
    expect(decidedElsewhere('', '', labels)).toBe('somewhere else');
  });
});

describe('an optimistic write', () => {
  it('is on screen immediately and keeps what it replaced', () => {
    const write = attempt(resting('propose-only'), 'act-with-approval');

    expect(write.value).toBe('act-with-approval');
    expect(write.snapshot).toBe('propose-only');
    expect(isPending(write)).toBe(true);
  });

  it('reverts to what was there and states the deployment’s reason when refused', () => {
    const write = refused(
      attempt(resting('propose-only'), 'act-with-approval'),
      'a bound refuses unattended action on production',
    );

    expect(write.value).toBe('propose-only');
    expect(write.state).toBe('reverted');
    expect(write.reason).toBe('a bound refuses unattended action on production');
  });

  it('rolls back to the original value rather than to an unconfirmed one', () => {
    const first = attempt(resting('propose-only'), 'act-with-approval');
    const second = attempt(first, 'act-freely');

    expect(refused(second, 'no').value).toBe('propose-only');
  });

  it('drops the snapshot once the deployment agrees', () => {
    const write = confirmed(attempt(resting('a'), 'b'));

    expect(write.value).toBe('b');
    expect(write.snapshot).toBeNull();
    expect(isPending(write)).toBe(false);
  });

  it('is superseded by the event carrying the same change, rather than added to', () => {
    const write = superseded(
      attempt(resting('a'), 'b'),
      'b-as-the-deployment-recorded-it',
    );

    expect(write.value).toBe('b-as-the-deployment-recorded-it');
    expect(write.state).toBe('applied');
  });
});

describe('an announced outcome', () => {
  const outcome = (id: string): Outcome => ({
    id,
    role: 'success',
    message: 'the remediation was applied',
    recordedAt: { href: '/runs/run-3', label: 'in the transcript' },
  });

  it('refuses to exist without somewhere durable behind it', () => {
    expect(() =>
      announce([], { ...outcome('a'), recordedAt: { href: '', label: '' } }),
    ).toThrow('never the only one');
  });

  it('does not stack the same outcome twice', () => {
    const once = announce([], outcome('a'));

    expect(announce(once, outcome('a'))).toHaveLength(1);
  });

  it('is bounded, because a stack that grows covers what it is reporting on', () => {
    let held: readonly Outcome[] = [];
    for (let index = 0; index < OUTCOME_LIMIT + 2; index += 1) {
      held = announce(held, outcome(String(index)));
    }

    expect(held).toHaveLength(OUTCOME_LIMIT);
  });

  it('is dismissible', () => {
    expect(dismiss(announce([], outcome('a')), 'a')).toEqual([]);
  });
});

describe('a list that changes while it is being read', () => {
  interface Row {
    readonly id: string;
    readonly age: number;
  }

  const rules: ListRules<Row> = {
    identify: (row) => row.id,
    order: (first, second) => first.age - second.age,
  };

  it('updates a row in place rather than moving it under the pointer', () => {
    const held = listOf(
      [
        { id: 'a', age: 1 },
        { id: 'b', age: 2 },
      ],
      rules,
    );

    const after = receive(held, { id: 'a', age: 9 }, rules, true);

    // Same order, new content. A row that jumped here is a row somebody clicks
    // by mistake.
    expect(after.items.map((row) => row.id)).toEqual(['a', 'b']);
    expect(after.items[0]?.age).toBe(9);
  });

  it('holds a new row back and counts it while the pointer is over the list', () => {
    const held = listOf([{ id: 'a', age: 1 }], rules);

    const after = receive(held, { id: 'c', age: 0 }, rules, true);

    expect(after.items.map((row) => row.id)).toEqual(['a']);
    expect(arrivedCount(after)).toBe(1);

    const placed = settle(after, rules);
    expect(placed.items.map((row) => row.id)).toEqual(['c', 'a']);
    expect(arrivedCount(placed)).toBe(0);
  });

  it('places a row straight away when nobody is pointing at the list', () => {
    const held = listOf([{ id: 'a', age: 1 }], rules);

    const after = receive(held, { id: 'c', age: 0 }, rules, false);

    expect(after.items.map((row) => row.id)).toEqual(['c', 'a']);
    expect(arrivedCount(after)).toBe(0);
  });

  it('does not count the same arrival twice', () => {
    let held = listOf<Row>([], rules);
    held = receive(held, { id: 'c', age: 0 }, rules, true);
    held = receive(held, { id: 'c', age: 1 }, rules, true);

    expect(arrivedCount(held)).toBe(1);
  });
});
