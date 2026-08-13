import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Schedules, type ScheduleRecord } from '@/surfaces/schedules';
import type { Viewer } from '@/session/viewer';

/**
 * Scheduled investigations: created, changed, turned off, or removed — never
 * computed here.
 *
 * Deleting is destructive and gets the library's own confirmation rather than
 * a bespoke one, and a cron expression the deployment refuses is shown
 * exactly as the deployment worded the refusal — this console does not parse
 * cron and has no sentence of its own to offer instead.
 */

let sent: { jobId: string; operation: string; payload: unknown }[] = [];

const WEEKLY: ScheduleRecord = {
  jobId: 'weekly-storage-review',
  name: 'Weekly storage review',
  cron: '0 7 * * 1',
  objective: 'Check datastore fill and backup coverage across the estate.',
  timezone: 'Europe/Lisbon',
  enabled: true,
  nextRun: {
    relative: 'in 6 days',
    absolute: '17 Aug 2026, 07:00',
    iso: '2026-08-17T07:00:00.000Z',
  },
};

const NIGHTLY: ScheduleRecord = {
  jobId: 'nightly-quorum-check',
  name: 'Nightly quorum check',
  cron: '0 3 * * *',
  objective: 'Establish whether the cluster would survive losing a node.',
  timezone: 'Europe/Lisbon',
  enabled: false,
  nextRun: null,
};

function answerWith(answer: unknown, status = 200): void {
  vi.stubGlobal('fetch', (_url: unknown, init: RequestInit) => {
    const body: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    sent.push({
      jobId: String(Reflect.get(Object(body), 'jobId')),
      operation: String(Reflect.get(Object(body), 'operation')),
      payload: Reflect.get(Object(body), 'payload'),
    });
    return Promise.resolve(
      new Response(JSON.stringify({ ok: status < 400, reachable: true, answer }), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

/** What the console's own courier answers once the *gateway* has refused —
 * the `reason` field the route computed from the gateway's own words, which
 * is what the component actually reads. */
function refusedWith(reason: string, status = 400): void {
  vi.stubGlobal('fetch', () =>
    Promise.resolve(
      new Response(JSON.stringify({ ok: false, reachable: true, reason }), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    ),
  );
}

beforeEach(() => {
  sent = [];
  answerWith({});
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const LABELS = {
  column: {
    name: 'Name',
    cron: 'Cron',
    objective: 'Objective',
    timezone: 'Timezone',
    nextRun: 'Next run',
    enabled: 'Enabled',
  },
  never: 'Not scheduled',
  enable: 'Enable',
  enabling: 'Enabling…',
  disable: 'Disable',
  disabling: 'Disabling…',
  save: 'Save',
  saving: 'Saving…',
  delete: 'Delete schedule',
  deleteConsequence:
    'This scheduled investigation is removed immediately, and nothing restores it from here.',
  deleteCancel: 'Cancel',
  deleteClose: 'Close',
  create: {
    title: 'Schedule a new investigation',
    jobId: 'Identifier',
    name: 'Name',
    cron: 'Cron',
    objective: 'Objective',
    timezone: 'Timezone',
    help: {
      jobId: 'a stable identifier',
      name: 'what operators see',
      cron: 'five fields',
      objective: 'the instruction',
      timezone: 'the zone it is read in',
    },
    submit: 'Create schedule',
    submitting: 'Creating…',
  },
  failed: 'The deployment refused this.',
  unreachable: 'The deployment could not be reached.',
};

function viewer(permissions: readonly string[]): Viewer {
  return {
    principalId: 'user-under-test',
    displayName: 'Avery Lockhart',
    email: null,
    roles: [],
    permissions: [...permissions],
    teamNodeId: 'team-platform',
    impersonating: false,
    impersonatedBy: null,
  };
}

function schedules(
  records: readonly ScheduleRecord[] = [WEEKLY, NIGHTLY],
  permissions: readonly string[] = ['schedule.manage'],
): void {
  render(
    <Schedules schedules={records} viewer={viewer(permissions)} labels={LABELS} />,
  );
}

function rowFor(jobId: string): HTMLElement {
  const found = screen
    .getAllByTestId('schedule')
    .find((row) => row.getAttribute('data-job') === jobId);
  if (found === undefined) throw new Error(`no row for ${jobId}`);
  return found;
}

describe('a viewer without schedule.manage', () => {
  it('sees no schedule control at all', () => {
    const { container } = render(
      <Schedules
        schedules={[WEEKLY]}
        viewer={viewer(['incident.read'])}
        labels={LABELS}
      />,
    );

    expect(container.firstChild).toBeNull();
    expect(sent).toHaveLength(0);
  });
});

describe('the schedule listing', () => {
  it('shows every schedule this team has, enabled and not', () => {
    schedules();

    expect(rowFor('weekly-storage-review')).toHaveTextContent('Weekly storage review');
    expect(rowFor('nightly-quorum-check')).toHaveTextContent('Nightly quorum check');
  });

  it('says a disabled schedule with no next run is not scheduled', () => {
    schedules();

    expect(rowFor('nightly-quorum-check')).toHaveTextContent(LABELS.never);
  });
});

describe('enabling and disabling', () => {
  it('toggles through the deployment and reflects what it sent back', async () => {
    answerWith({ ...NIGHTLY, enabled: true, next_run_at: '2026-08-12T03:00:00+00:00' });
    schedules();

    const toggle = rowFor('nightly-quorum-check').querySelector(
      '[data-testid="toggle-schedule"]',
    );
    if (toggle === null) throw new Error('no toggle control');
    await userEvent.click(toggle);

    expect(sent).toEqual([
      { jobId: 'nightly-quorum-check', operation: 'enable', payload: undefined },
    ]);
  });
});

describe('deleting a schedule', () => {
  it('confirms before anything is removed', async () => {
    schedules();

    const del = rowFor('weekly-storage-review').querySelector(
      '[data-testid="delete-schedule"]',
    );
    if (del === null) throw new Error('no delete control');
    await userEvent.click(del);

    expect(screen.getByRole('dialog')).toHaveTextContent(LABELS.deleteConsequence);
    // Naming the target, not "this item".
    expect(screen.getByRole('dialog')).toHaveTextContent('Weekly storage review');
    expect(sent).toHaveLength(0);
  });

  it('removes nothing when the confirmation is cancelled', async () => {
    schedules();

    const del = rowFor('weekly-storage-review').querySelector(
      '[data-testid="delete-schedule"]',
    );
    if (del === null) throw new Error('no delete control');
    await userEvent.click(del);
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: LABELS.deleteCancel,
      }),
    );

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(sent).toHaveLength(0);
    expect(screen.getAllByTestId('schedule')).toHaveLength(2);
  });

  it('removes the row once the deployment confirms it is gone', async () => {
    schedules();

    const del = rowFor('weekly-storage-review').querySelector(
      '[data-testid="delete-schedule"]',
    );
    if (del === null) throw new Error('no delete control');
    await userEvent.click(del);
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: new RegExp(LABELS.delete),
      }),
    );

    expect(sent).toEqual([
      { jobId: 'weekly-storage-review', operation: 'delete', payload: undefined },
    ]);
    expect(await screen.findAllByTestId('schedule')).toHaveLength(1);
  });
});

describe('a cron expression the deployment refuses', () => {
  it('renders the refusal exactly as the deployment worded it', async () => {
    schedules([]);
    const refusal = "'99 7 * * 1' is outside 0–59 in the minute field of '99 7 * * 1'.";
    refusedWith(refusal);

    await userEvent.type(screen.getByLabelText(LABELS.create.jobId), 'bad-cron');
    await userEvent.type(screen.getByLabelText(LABELS.create.name), 'Bad cron');
    await userEvent.type(screen.getByLabelText(LABELS.create.cron), '99 7 * * 1');
    await userEvent.type(
      screen.getByLabelText(LABELS.create.objective),
      'Test the refusal.',
    );
    await userEvent.click(screen.getByTestId('submit-create-schedule'));

    expect(await screen.findByTestId('schedule-failure')).toHaveTextContent(refusal);
    expect(screen.queryAllByTestId('schedule')).toHaveLength(0);
  });

  it('says it could not be reached, which is a different machine to look at', async () => {
    schedules([]);
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.type(screen.getByLabelText(LABELS.create.jobId), 'bad-cron');
    await userEvent.type(screen.getByLabelText(LABELS.create.name), 'Bad cron');
    await userEvent.type(screen.getByLabelText(LABELS.create.cron), '99 7 * * 1');
    await userEvent.type(
      screen.getByLabelText(LABELS.create.objective),
      'Test the refusal.',
    );
    await userEvent.click(screen.getByTestId('submit-create-schedule'));

    expect(await screen.findByTestId('schedule-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});

describe('creating a schedule', () => {
  it('will not submit until every required field is filled', () => {
    schedules([]);

    expect(screen.getByTestId('submit-create-schedule')).toBeDisabled();
  });

  it('adds the schedule the deployment created, and clears the form', async () => {
    schedules([]);
    answerWith({
      job_id: 'new-check',
      name: 'New check',
      cron: '0 9 * * *',
      objective: 'Watch something new.',
      timezone: 'UTC',
      enabled: true,
      next_run_at: '2026-08-12T09:00:00+00:00',
    });

    await userEvent.type(screen.getByLabelText(LABELS.create.jobId), 'new-check');
    await userEvent.type(screen.getByLabelText(LABELS.create.name), 'New check');
    await userEvent.type(screen.getByLabelText(LABELS.create.cron), '0 9 * * *');
    await userEvent.type(
      screen.getByLabelText(LABELS.create.objective),
      'Watch something new.',
    );
    await userEvent.click(screen.getByTestId('submit-create-schedule'));

    expect(await screen.findAllByTestId('schedule')).toHaveLength(1);
    expect(screen.getByLabelText(LABELS.create.jobId)).toHaveValue('');
  });
});

describe('editing a cron expression', () => {
  it('shows a save control only once the draft differs, and sends exactly the draft', async () => {
    answerWith({ ...WEEKLY, cron: '0 8 * * 1' });
    schedules();

    const row = rowFor('weekly-storage-review');
    expect(row.querySelector('[data-testid="save-schedule-cron"]')).toBeNull();

    const cronField = row.querySelector('input[name="cron-weekly-storage-review"]');
    if (cronField === null) throw new Error('no cron field');
    await userEvent.clear(cronField);
    await userEvent.type(cronField, '0 8 * * 1');

    const save = row.querySelector('[data-testid="save-schedule-cron"]');
    if (save === null) throw new Error('no save control appeared');
    await userEvent.click(save);

    expect(sent).toEqual([
      {
        jobId: 'weekly-storage-review',
        operation: 'update',
        payload: { cron: '0 8 * * 1', timezone: 'Europe/Lisbon' },
      },
    ]);
  });
});
