import { describe, expect, it } from 'vitest';

import { RUN_BAND_STAGE_COUNT, inFlightRuns, runCardOf, stageStates } from '@/surfaces/run-band';
import { text } from '@/surfaces/read';

function run(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: 'run-1',
    status: 'running',
    trigger: 'manual',
    headline: 'Look for anomalies on the Proxmox cluster',
    started_at: '2026-08-27T11:58:00.000Z',
    ...over,
  };
}

describe('stageStates', () => {
  it('draws all six segments future when the field is absent', () => {
    expect(stageStates(undefined)).toEqual(Array(RUN_BAND_STAGE_COUNT).fill('future'));
  });

  it('draws the first segment current and nothing completed at stage 0', () => {
    expect(stageStates(0)).toEqual(['current', 'future', 'future', 'future', 'future', 'future']);
  });

  it('draws completed up to the index, current at index+1, future after', () => {
    expect(stageStates(3)).toEqual([
      'completed',
      'completed',
      'completed',
      'current',
      'future',
      'future',
    ]);
  });

  it('draws all six completed and no current segment at the last stage', () => {
    // A segment cannot carry both states at once -- the literal reading of
    // "completed up to N, current at N+1" would put segment 6 in both.
    expect(stageStates(6)).toEqual(Array(RUN_BAND_STAGE_COUNT).fill('completed'));
  });
});

describe('inFlightRuns', () => {
  it('keeps running and suspended runs, and drops every settled status', () => {
    const records = [
      run({ run_id: 'a', status: 'running' }),
      run({ run_id: 'b', status: 'suspended' }),
      run({ run_id: 'c', status: 'completed' }),
      run({ run_id: 'd', status: 'failed' }),
      run({ run_id: 'e', status: 'cancelled' }),
      // The zombie band: a run the reaper marked interrupted days ago is
      // settled, not "not yet terminated" -- this is the whole point.
      run({ run_id: 'f', status: 'interrupted' }),
    ];

    const flight = inFlightRuns(records);

    expect(flight.map((record) => text(record, 'run_id'))).toEqual(['a', 'b']);
  });
});

describe('runCardOf', () => {
  it('reads the title from the served headline, never deriving one', () => {
    const card = runCardOf(
      run({ headline: 'Look for anomalies on the Proxmox cluster' }),
      'en',
      new Date('2026-08-27T12:00:00.000Z'),
      'UTC',
    );

    expect(card.title).toBe('Look for anomalies on the Proxmox cluster');
  });

  it('carries no stage index when the field is absent from the record', () => {
    const card = runCardOf(run({}), 'en', new Date('2026-08-27T12:00:00.000Z'), 'UTC');
    expect(card.stageIndex).toBeUndefined();
  });

  it('carries the served stage index when present', () => {
    const card = runCardOf(
      run({ stage_index: 3 }),
      'en',
      new Date('2026-08-27T12:00:00.000Z'),
      'UTC',
    );
    expect(card.stageIndex).toBe(3);
  });

  it('treats an out-of-range stage index as absent rather than crashing the bar', () => {
    const card = runCardOf(
      run({ stage_index: 99 }),
      'en',
      new Date('2026-08-27T12:00:00.000Z'),
      'UTC',
    );
    expect(card.stageIndex).toBeUndefined();
  });
});
