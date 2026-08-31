import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RunBand, runCardOf, type RunCardData } from '@/surfaces/run-band';

/**
 * "Em execução agora", drawn: the band and each card carry the run kind's own
 * mark, the header names what each of its three counts counts, and a card says
 * which of the six stages the run has reached rather than only drawing the bar.
 */

const NOW = new Date('2026-08-27T12:00:00.000Z');

function card(over: Partial<RunCardData> = {}): RunCardData {
  return {
    id: 'run-1',
    title: 'Look for anomalies on the Proxmox cluster',
    trigger: 'manual',
    elapsedSeconds: 47,
    stageIndex: 2,
    stage: 'plan_evidence',
    ...over,
  };
}

describe('RunBand header', () => {
  it("carries the run kind's own mark beside its name", () => {
    render(
      <RunBand
        locale="en"
        runs={[card()]}
        followedCount={14}
        blockedCount={1}
        moreHref="/runs"
      />,
    );
    expect(screen.getByTestId('run-band-mark')).toBeInTheDocument();
  });

  it('names what each of the three counts counts, not just the numbers', () => {
    render(
      <RunBand
        locale="en"
        runs={[card()]}
        followedCount={14}
        blockedCount={1}
        moreHref="/runs"
      />,
    );
    // The counts themselves stay in their own spans, which the acceptance
    // suite parses as bare numbers; what was missing is the noun beside each.
    const band = screen.getByTestId('run-band');
    expect(band.textContent).toContain('investigations in flight');
    expect(band.textContent).toContain('incidents followed');
    expect(band.textContent).toContain('blocked on you');
  });
});

describe('RunCard', () => {
  it("carries the run kind's own mark", () => {
    render(
      <RunBand
        locale="en"
        runs={[card()]}
        followedCount={0}
        blockedCount={0}
        moreHref="/runs"
      />,
    );
    expect(
      within(screen.getByTestId('run-card')).getByTestId('run-card-mark'),
    ).toBeInTheDocument();
  });

  it('says which stage the run has reached, and out of how many', () => {
    render(
      <RunBand
        locale="en"
        runs={[card({ stageIndex: 2, stage: 'plan_evidence' })]}
        followedCount={0}
        blockedCount={0}
        moreHref="/runs"
      />,
    );
    const label = screen.getByTestId('run-card-stage-label');
    // `stage_index` is the last stage *completed*, so the stage under way is
    // the next one -- the third of six here, and the console's own word for it.
    expect(label).toHaveTextContent('Gather evidence');
    expect(label).toHaveTextContent('3');
    expect(label).toHaveTextContent('6');
  });

  it('says nothing about a stage when no stage has completed and none is named', () => {
    render(
      <RunBand
        locale="en"
        runs={[card({ stageIndex: undefined, stage: '' })]}
        followedCount={0}
        blockedCount={0}
        moreHref="/runs"
      />,
    );
    expect(screen.queryByTestId('run-card-stage-label')).toBeNull();
  });
});

describe('runCardOf', () => {
  it("reads the last completed stage's own name from the listing", () => {
    const read = runCardOf(
      {
        run_id: 'run-1',
        status: 'running',
        trigger: 'manual',
        headline: 'Look for anomalies',
        started_at: '2026-08-27T11:59:13.000Z',
        stage_index: 2,
        last_completed_stage: 'intake',
      },
      NOW,
    );
    expect(read.stage).toBe('intake');
  });

  it("leaves the stage empty when the listing does not name one", () => {
    const read = runCardOf(
      {
        run_id: 'run-1',
        status: 'running',
        trigger: 'manual',
        headline: 'Look for anomalies',
        started_at: '2026-08-27T11:59:13.000Z',
      },
      NOW,
    );
    expect(read.stage).toBe('');
  });
});
