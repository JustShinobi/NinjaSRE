import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EN } from '@/i18n/en';
import { CopyReport } from '@/surfaces/copy-report';
import {
  RunCard,
  namedEvidence,
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
  decisions: [],
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
      <EvidenceChip locale="en" evidence={{ assessed: true, backed: 2, missing: 1 }} />,
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

  it('reads an assessment that named nothing as silence rather than as proof', () => {
    render(
      <EvidenceChip locale="en" evidence={{ assessed: true, backed: 0, missing: 0 }} />,
    );

    const chip = screen.getByTestId('run-evidence');
    expect(chip).toHaveTextContent(EN['run.evidence.unassessed']);
    expect(chip).toHaveAttribute('data-role', 'neutral');
  });

  it('refuses a count the gateway sent as something other than a positive number', () => {
    expect(
      evidenceOf({
        evidence_assessed: true,
        evidence_backed: 'four',
        evidence_missing: -3,
      }),
    ).toEqual({ assessed: true, backed: 0, missing: 0 });
    // A fraction and an infinity are both numbers and neither is a count.
    expect(
      evidenceOf({
        evidence_assessed: true,
        evidence_backed: 2.7,
        evidence_missing: Number.POSITIVE_INFINITY,
      }),
    ).toEqual({ assessed: true, backed: 2, missing: 0 });
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

  it('says a call and a run with no recorded duration have none', () => {
    card(
      { seconds: 0 },
      {
        turns: [
          {
            index: 1,
            rationale: 'ask',
            model: 'a-model',
            calls: [
              {
                callId: 'call-1',
                name: 'proxmox_quorum_status',
                status: 'succeeded',
                error: '',
                durationMs: 0,
              },
            ],
          },
        ],
      },
    );

    // Twice for the run itself — in its header row and in its own measurement
    // — and not once in the trace: a call whose duration nobody recorded shows
    // no duration rather than repeating "not recorded" down the whole list.
    expect(screen.getAllByText(EN['surface.none'])).toHaveLength(2);
    expect(screen.getByTestId('run-call')).not.toHaveTextContent(EN['surface.none']);
  });

  it('groups the calls under the turn that made them, and names a silent turn', () => {
    card();

    expect(screen.getAllByTestId('run-turn')).toHaveLength(2);
    expect(screen.getAllByTestId('run-call')).toHaveLength(2);
    expect(screen.getByText(EN['run.did.noRationale'])).toBeInTheDocument();
    expect(screen.getByText('no log source configured')).toBeInTheDocument();
  });
});

describe('reading what the run recorded', () => {
  it('returns nothing at all for a replay that carries no turns', () => {
    expect(turnsFrom({})).toEqual([]);
  });

  it('takes the turns and their calls off the replay', () => {
    const replay = {
      turns: [
        {
          index: 1,
          model_rationale: 'look at the cluster',
          calls: [{ call_id: 'a', name: 'proxmox_quorum_status', status: 'succeeded' }],
        },
        { index: 2, calls: [] },
      ],
    };

    const turns = turnsFrom(replay);
    expect(turns).toHaveLength(2);
    expect(turns[0]?.calls[0]?.name).toBe('proxmox_quorum_status');
    expect(turns[1]?.rationale).toBe('');
  });

  it("never puts capability scoring where the turn's reasoning goes", () => {
    // `selection_rationale` reads "ranked 75, offered 40, cut by the ceiling
    // 19" and is the same on every turn of a run. A card that fell back to it
    // filled six group headings with one machine sentence.
    const turns = turnsFrom({
      turns: [
        {
          index: 1,
          model_rationale: '',
          selection_rationale: 'ranked 75, offered 40, cut by the ceiling 19',
          calls: [],
        },
      ],
    });

    expect(turns[0]?.rationale).toBe('');
  });

  it('reads the named evidence off the run, dropping anything that is not a sentence', () => {
    expect(
      namedEvidence({
        evidence_supporting_names: ['the guest task log names a person', 7],
        evidence_missing_names: 'nothing',
      }),
    ).toEqual({ supporting: ['the guest task log names a person'], missing: [] });
  });

  it('is empty for a run whose record carries neither list', () => {
    expect(namedEvidence({})).toEqual({ supporting: [], missing: [] });
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

/**
 * The header is a handle, and a handle does not resize itself when pressed.
 *
 * Opening a card used to change the subject's own type — `text-strong` in
 * place of `text-body` — and let it grow from one line to two. Both land at
 * the instant the body appears, so the row under the pointer got heavier and
 * taller while everything below it jumped down. Read as a whole that is not a
 * disclosure; it is the row being replaced by a different row, which is what
 * "the expansion does not feel natural" describes.
 *
 * What opens is the body. The header is identical either way, and the whole
 * subject is in the tooltip closed and in the report open.
 */
describe('the header of a card', () => {
  function subjectClass(open: boolean): string {
    const { unmount } = render(
      <RunCard
        locale="en"
        now={new Date('2026-08-05T12:00:00+00:00')}
        zone="UTC"
        head={HEAD}
        toggleHref="/runs"
        open={open}
        {...(open ? { body: BODY } : {})}
      />,
    );
    const found = screen.getByTestId('run-card-subject').className;
    unmount();
    return found;
  }

  it('renders the subject identically whether the card is open or shut', () => {
    expect(subjectClass(true)).toBe(subjectClass(false));
  });

  it('never lets the subject take a second line, in either state', () => {
    expect(subjectClass(true)).toContain('truncate');
    expect(subjectClass(true)).not.toContain('line-clamp');
  });
});

/**
 * The report is written once on this card, at the top, rendered as a document.
 *
 * The last turn of a run is the turn that produced the answer, so the model's
 * own account of that turn *is* the report — and the trace printed it raw,
 * Markdown syntax and all, in the one-line slot meant for "why these
 * capabilities". A reader who scrolled to the working-out found the conclusion
 * again, unrendered, several times taller than the box it sat in.
 */
describe('the trace under a card', () => {
  it("does not print the report again as the last turn's reasoning", () => {
    const report = '### Incident Investigation Report\n\nThe node was down.';
    card(
      {},
      {
        report,
        turns: [
          { index: 1, rationale: 'Asked the cluster.', model: 'm', calls: [] },
          { index: 2, rationale: report, model: 'm', calls: [] },
        ],
      },
    );

    const turns = screen.getAllByTestId('run-turn');
    expect(turns[0]?.textContent).toContain('Asked the cluster.');
    expect(turns[1]?.textContent).not.toContain('Incident Investigation Report');
  });
});

/**
 * An action waiting on a person is decided where it is read.
 *
 * The artboard puts this inside the card, under "What to do", and it is the
 * gesture the whole screen is arranged around: an investigation that ends in
 * "start the container" is worth nothing until somebody says yes, and the
 * proposal in the design had been waiting twenty-two minutes. Sending the
 * reader to another screen to say it is how a queue becomes six open tabs and
 * the wrong one gets approved — which is why `DecisionControls` already
 * decides in place everywhere else it appears.
 *
 * Approvals and questions are kept apart because they ask for different
 * things. A question wants an answer; an approval wants a verdict, and only
 * one of them can be given by pressing a button.
 */
describe('an action waiting on a person', () => {
  it('offers the decision on the card rather than a link to it', () => {
    card(
      {},
      {
        decisions: [
          {
            interactionId: 'int-0001',
            text: "Start the container: proxmox_start_guest(kind='lxc', node='pve01', vmid=122)",
          },
        ],
      },
    );

    const waiting = screen.getByTestId('run-decision');
    expect(waiting).toHaveTextContent('proxmox_start_guest');
    expect(waiting.querySelector('[data-testid="decision"]')).not.toBeNull();
  });

  it('keeps a question a question, with nothing to press', () => {
    card(
      {},
      { decisions: [], waiting: ['Which datastore should this be measured against?'] },
    );

    expect(screen.getByTestId('run-waiting')).toHaveTextContent('Which datastore');
    expect(screen.queryByTestId('run-decision')).toBeNull();
  });

  it('says nothing is waiting only when neither kind is', () => {
    card({}, { decisions: [], waiting: [] });

    expect(screen.getByText(EN['run.todo.none'])).toBeInTheDocument();
  });
});
