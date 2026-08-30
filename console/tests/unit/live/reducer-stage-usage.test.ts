import { describe, expect, it } from 'vitest';

import { eventFrom, type StreamEvent } from '@/live/events';
import { applyEvents, openRun } from '@/live/reducer';

/**
 * The rail's live half: stages, usage and touched resources, accumulated from
 * exactly the events that already cross the wire — never a second opinion
 * about what the deployment sent.
 *
 * Proved as a pure reducer property, the same way the ordering guarantee is:
 * a sequence of `stage_completed`, `turn_completed` and `tool_called` events,
 * fed through in and out of order, has to leave the same accumulated state
 * either way, and an event held for a gap must not be counted before it is
 * actually released.
 */

/** One wire document, with whatever payload the caller wants on it. */
function frame(sequence: number, kind: string, payload: unknown): unknown {
  return {
    run_id: 'run-0003',
    kind,
    sequence,
    occurred_at: '2026-08-07T11:57:00+00:00',
    turn_id: null,
    payload,
  };
}

function must(document: unknown): StreamEvent {
  const event = eventFrom(document);
  if (event === null) throw new Error(`not a stream event: ${JSON.stringify(document)}`);
  return event;
}

const STAGE_COMPLETED = (sequence: number, stage: string, opts: Partial<{
  durationMs: number;
  finding: string;
  failed: boolean;
}> = {}): StreamEvent =>
  must(
    frame(sequence, 'stage_completed', {
      stage,
      duration_ms: opts.durationMs ?? 100,
      finding: opts.finding ?? `${stage} finding`,
      failed: opts.failed ?? false,
    }),
  );

const TURN_COMPLETED = (sequence: number, tokens: number): StreamEvent =>
  must(frame(sequence, 'turn_completed', { index: 0, tokens }));

const TOOL_CALLED = (sequence: number, name: string, args: Record<string, unknown>): StreamEvent =>
  must(frame(sequence, 'tool_called', { name, arguments: args }));

describe('the live reducer accumulates the stages a run completes', () => {
  it('adds one entry per stage_completed event, in arrival order, with its own facts', () => {
    let state = openRun('run-0003');
    state = applyEvents(state, [
      STAGE_COMPLETED(0, 'resolve_integrations', { durationMs: 175, finding: 'six capabilities' }),
      STAGE_COMPLETED(1, 'intake', { durationMs: 1260, finding: 'a new incident' }),
    ]);

    expect(state.stages).toEqual([
      { stage: 'resolve_integrations', finding: 'six capabilities', durationMs: 175, failed: false },
      { stage: 'intake', finding: 'a new incident', durationMs: 1260, failed: false },
    ]);
  });

  it('records a failed stage with its own failure, and does not invent the ones after it', () => {
    let state = openRun('run-0003');
    state = applyEvents(state, [
      STAGE_COMPLETED(0, 'resolve_integrations'),
      STAGE_COMPLETED(1, 'intake'),
      STAGE_COMPLETED(2, 'plan_evidence', { failed: true, finding: 'the model could not be reached' }),
    ]);

    expect(state.stages).toHaveLength(3);
    expect(state.stages[2]).toEqual({
      stage: 'plan_evidence',
      finding: 'the model could not be reached',
      durationMs: 100,
      failed: true,
    });
  });

  it('does not count a stage twice when the event that named it arrives again on reconnection', () => {
    let state = openRun('run-0003');
    const event = STAGE_COMPLETED(0, 'resolve_integrations');
    state = applyEvents(state, [event]);
    state = applyEvents(state, [event]);

    expect(state.stages).toHaveLength(1);
  });

  it('holds a stage completion that arrived out of order, and applies it once the gap fills', () => {
    let state = openRun('run-0003');
    // Sequence 1 arrives before sequence 0: held, not counted yet.
    state = applyEvents(state, [STAGE_COMPLETED(1, 'intake')]);
    expect(state.stages).toEqual([]);

    state = applyEvents(state, [STAGE_COMPLETED(0, 'resolve_integrations')]);
    expect(state.stages.map((stage) => stage.stage)).toEqual([
      'resolve_integrations',
      'intake',
    ]);
  });
});

describe('the live reducer accumulates usage from the turns a run finishes', () => {
  it('starts at nothing, before any turn has completed', () => {
    const state = openRun('run-0003');
    expect(state.usage).toEqual({ tokens: 0, turns: 0 });
  });

  it('sums the tokens of each turn_completed event and counts the turns', () => {
    let state = openRun('run-0003');
    state = applyEvents(state, [TURN_COMPLETED(0, 1_840), TURN_COMPLETED(1, 612)]);

    expect(state.usage).toEqual({ tokens: 2_452, turns: 2 });
  });

  it('is unaffected by events that are not about a turn finishing', () => {
    let state = openRun('run-0003');
    state = applyEvents(state, [
      STAGE_COMPLETED(0, 'resolve_integrations'),
      TOOL_CALLED(1, 'estate.failed_units', { node: 'node01' }),
    ]);

    expect(state.usage).toEqual({ tokens: 0, turns: 0 });
  });
});

describe('the live reducer accumulates the resources a run touches', () => {
  it('adds the resource a tool_called event names, from the argument key the deployment used', () => {
    let state = openRun('run-0003');
    state = applyEvents(state, [TOOL_CALLED(0, 'estate.failed_units', { node: 'node01' })]);

    expect(state.touched).toEqual(['node01']);
  });

  it('recognises every one of the resource-shaped argument keys the recorder itself knows', () => {
    let state = openRun('run-0003');
    state = applyEvents(state, [
      TOOL_CALLED(0, 'a', { resource_id: 'r-1' }),
      TOOL_CALLED(1, 'b', { resource: 'r-2' }),
      TOOL_CALLED(2, 'c', { instance: 'r-3' }),
      TOOL_CALLED(3, 'd', { host: 'r-4' }),
      TOOL_CALLED(4, 'e', { pod: 'r-5' }),
      TOOL_CALLED(5, 'f', { vmid: 'r-6' }),
      TOOL_CALLED(6, 'g', { vm_id: 'r-7' }),
    ]);

    expect(state.touched).toEqual(['r-1', 'r-2', 'r-3', 'r-4', 'r-5', 'r-6', 'r-7']);
  });

  it('never lists the same resource twice, however many calls name it', () => {
    let state = openRun('run-0003');
    state = applyEvents(state, [
      TOOL_CALLED(0, 'estate.failed_units', { node: 'node01' }),
      TOOL_CALLED(1, 'estate.disk_usage', { node: 'node01' }),
    ]);

    expect(state.touched).toEqual(['node01']);
  });

  it('adds nothing for a call whose arguments name no resource-shaped key', () => {
    let state = openRun('run-0003');
    state = applyEvents(state, [TOOL_CALLED(0, 'knowledge.search', { query: 'hardening' })]);

    expect(state.touched).toEqual([]);
  });
});
