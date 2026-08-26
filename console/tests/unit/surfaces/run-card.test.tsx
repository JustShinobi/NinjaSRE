import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EN } from '@/i18n/en';
import { CopyReport } from '@/surfaces/copy-report';
import {
  RunCard,
  assessmentArguments,
  turnsFrom,
  type RunCardBody,
  type RunCardHead,
} from '@/surfaces/run-card';
import { EvidenceChip, evidenceOf } from '@/surfaces/run-evidence';

/**
 * The card an investigation is read in, and the two facts it must not fake.
 *
 * A run that never assessed its own evidence is not a run that found nothing
 * missing, and a section with no data behind it says so rather than being
 * filled with something that reads like data. Both are the kind of thing that
 * looks fine in a screenshot and is a lie on somebody's Tuesday.
 */

const HEAD: RunCardHead = {
  runId: 'e19e882a1c9b4d5e8f6a2b3c7d0e1f24',
  subject: 'a guest reached the ceiling of its own volume',
  subjectFull: 'a guest reached the ceiling of its own volume',
  status: 'succeeded',
  trigger: 'alert',
  startedAt: '2026-08-05T11:19:00+00:00',
  seconds: 36,
  evidence: { assessed: true, backed: 4, missing: 0 },
};

const BODY: RunCardBody = {
  report: '### Root cause\n\nThe container was stopped by hand.',
  headline: 'the container was stopped by hand',
  touchedResources: ['res-7a73b8aa'],
  incidentId: 'inc-1',
  tokens: 71141,
  priced: false,
  turns: [
    {
      index: 1,
      rationale: 'ask the cluster whether it still agrees with itself',
      model: 'a-model',
      calls: [
        {
          callId: 'call-1',
          name: 'proxmox_quorum_status',
          status: 'succeeded',
          error: '',
          durationMs: 1200,
        },
        {
          callId: 'call-2',
          name: 'logs_for_resource',
          status: 'failed',
          error: 'no log source configured',
          durationMs: 400,
        },
      ],
    },
    { index: 2, rationale: '', model: 'a-model', calls: [] },
  ],
  calls: 2,
  events: 5,
  waiting: ['May I start the container?'],
  supporting: ['the guest task log names a person'],
  missing: ['the container logs'],
};

function card(
  head: Partial<RunCardHead> = {},
  body: Partial<RunCardBody> | null = {},
): void {
  render(
    <RunCard
      locale="en"
      now={new Date('2026-08-05T12:00:00+00:00')}
      zone="UTC"
      head={{ ...HEAD, ...head }}
      toggleHref="/runs"
      open={body !== null}
      {...(body === null ? {} : { body: { ...BODY, ...body } })}
    />,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the evidence a run says it had', () => {
  it('reads a run that never assessed itself as having said nothing', () => {
    render(
      <EvidenceChip
        locale="en"
        evidence={evidenceOf({ evidence_assessed: false, evidence_backed: 0 })}
      />,
    );

    const chip = screen.getByTestId('run-evidence');
    expect(chip).toHaveTextContent(EN['run.evidence.unassessed']);
    expect(chip).toHaveAttribute('data-role', 'neutral');
  });

  it('counts what the run backed, and stays warning while anything is missing', () => {
    render(
      <EvidenceChip
        locale="en"
        evidence={{ assessed: true, backed: 2, missing: 1 }}
      />,
    );

    const chip = screen.getByTestId('run-evidence');
    expect(chip).toHaveTextContent('2 of 3 claims backed');
    expect(chip).toHaveAttribute('data-role', 'warning');
  });

  it('is only success when the run itself said nothing was outstanding', () => {
    render(
      <EvidenceChip locale="en" evidence={{ assessed: true, backed: 4, missing: 0 }} />,
    );

    expect(screen.getByTestId('run-evidence')).toHaveAttribute('data-role', 'success');
  });

  it('refuses a count the gateway sent as something other than a positive number', () => {
    expect(
      evidenceOf({
        evidence_assessed: true,
        evidence_backed: 'four',
        evidence_missing: -3,
      }),
    ).toEqual({ assessed: true, backed: 0, missing: 0 });
  });
});

describe('a closed card', () => {
  it('names the run, its trigger and its short id, and draws no body', () => {
    card({}, null);

    expect(screen.getByTestId('run-card')).toHaveAttribute('data-open', 'false');
    expect(screen.queryByTestId('run-card-body')).toBeNull();
    expect(screen.getByTestId('run-card')).toHaveTextContent('Alert');
    expect(screen.getByTestId('run-card')).toHaveTextContent('#e19e882a');
    expect(screen.getByTestId('run-card-toggle')).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });

  it('says a run that never finished has no duration rather than nought seconds', () => {
    card({ seconds: 0 }, null);

    expect(screen.getByTestId('run-card')).toHaveTextContent(EN['surface.none']);
  });
});

describe('an open card', () => {
  it('draws the report, what it touched, why, and what is waiting', () => {
    card();

    expect(screen.getByTestId('run-card-body')).toBeInTheDocument();
    expect(screen.getByText('What happened')).toBeInTheDocument();
    expect(screen.getByTestId('run-touched')).toHaveTextContent('res-7a73b8aa');
    expect(screen.getByText('the guest task log names a person')).toBeInTheDocument();
    expect(screen.getByText('the container logs')).toBeInTheDocument();
    expect(screen.getByTestId('run-waiting')).toHaveTextContent(
      'May I start the container?',
    );
  });

  it('says the model publishes no price rather than printing a cost of nothing', () => {
    card();

    expect(screen.getByText(EN['run.measure.unpriced'])).toBeInTheDocument();
  });

  it('omits that note when every turn carried a price', () => {
    card({}, { priced: true });

    expect(screen.queryByText(EN['run.measure.unpriced'])).toBeNull();
  });

  it('falls back to the headline when the run wrote no document', () => {
    card({}, { report: '' });

    expect(screen.getByText('the container was stopped by hand')).toBeInTheDocument();
    expect(screen.queryByTestId('copy-report')).toBeNull();
  });

  it('says each empty section is empty instead of filling it', () => {
    card(
      {},
      {
        touchedResources: [],
        incidentId: '',
        waiting: [],
        supporting: [],
        missing: [],
      },
    );

    expect(screen.getByText(EN['run.reaches.none'])).toBeInTheDocument();
    expect(screen.getByText(EN['run.why.none'])).toBeInTheDocument();
    expect(screen.getByText(EN['run.todo.none'])).toBeInTheDocument();
  });

  it('draws no missing column when the run left nothing outstanding', () => {
    card({}, { missing: [] });

    expect(screen.queryByText(EN['run.why.missing'])).toBeNull();
    expect(screen.getByText(EN['run.why.supporting'])).toBeInTheDocument();
  });

  it('groups the calls under the turn that made them, and names a silent turn', () => {
    card();

    expect(screen.getAllByTestId('run-turn')).toHaveLength(2);
    expect(screen.getAllByTestId('run-call')).toHaveLength(2);
    expect(screen.getByText(EN['run.did.noRationale'])).toBeInTheDocument();
    expect(screen.getByText('no log source configured')).toBeInTheDocument();
  });
});

describe('reading the replay the card draws from', () => {
  it('returns nothing at all for a replay that carries no turns', () => {
    expect(turnsFrom({})).toEqual([]);
    expect(assessmentArguments({}, 'assess_evidence_sufficiency')).toEqual({
      supporting: [],
      missing: [],
    });
  });

  it('takes the last assessment, and drops an argument that is not a list', () => {
    const replay = {
      turns: [
        {
          index: 1,
          calls: [
            {
              call_id: 'a',
              name: 'assess_evidence_sufficiency',
              arguments: { supporting_evidence: ['one'], missing_evidence: ['logs'] },
            },
          ],
        },
        {
          index: 2,
          calls: [
            {
              call_id: 'b',
              name: 'assess_evidence_sufficiency',
              arguments: {
                supporting_evidence: ['one', 'two', 3],
                missing_evidence: 'nothing',
              },
            },
          ],
        },
      ],
    };

    expect(assessmentArguments(replay, 'assess_evidence_sufficiency')).toEqual({
      supporting: ['one', 'two'],
      missing: [],
    });
    expect(turnsFrom(replay)).toHaveLength(2);
  });
});

describe('putting the report on the clipboard', () => {
  const labels = {
    copy: EN['run.report.copy'],
    copied: EN['run.report.copied'],
    refused: EN['run.report.copyRefused'],
  };

  it('says so once the clipboard took it', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    render(<CopyReport text="# a report" labels={labels} />);
    fireEvent.click(screen.getByTestId('copy-report'));
    await vi.waitFor(() => {
      expect(screen.getByTestId('copy-report')).toHaveTextContent(labels.copied);
    });
    expect(writeText).toHaveBeenCalledWith('# a report');
  });

  it('says the browser refused rather than claiming a copy that never happened', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: () => Promise.reject(new Error('denied')) },
    });

    render(<CopyReport text="# a report" labels={labels} />);
    fireEvent.click(screen.getByTestId('copy-report'));
    await vi.waitFor(() => {
      expect(screen.getByTestId('copy-report')).toHaveTextContent(labels.refused);
    });
  });
});
