'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input } from '@/components/form';
import { Badge } from '@/components/status';
import { ConfirmDestructive } from '@/components/overlay';
import { timestamp, type Timestamp } from '@/i18n/format';
import type { Locale } from '@/i18n/messages';
import { may, type Viewer } from '@/session/viewer';

/**
 * The recurring investigations this team has scheduled: created, changed,
 * turned off, or removed — never computed here.
 *
 * A recurring investigation is watched for on a clock rather than raised by a
 * detector, which is why it sits beside detection instead of in a queue of its
 * own: both are "what runs without somebody starting it", and an operator
 * checking what is watching this team's estate should not have to know which
 * of the two mechanisms produced a given entry.
 *
 * **Deleting is destructive, and gets the library's own confirmation.** A
 * removed schedule is not recoverable from here, so it goes through
 * `ConfirmDestructive` the same way every other irreversible write in this
 * console does, naming the schedule rather than asking "are you sure".
 *
 * **A cron expression the deployment refuses is shown exactly as refused.**
 * `platform.scheduler.cron` writes a sentence naming what is wrong with which
 * field, and inventing a friendlier one here would be a second, competing
 * opinion about a syntax this console does not parse.
 */

/** Where every write goes. The console's own process, forwarding once. */
export const SCHEDULE_ENDPOINT = '/api/schedules';

/** Who may see or change this team's scheduled investigations. */
const MANAGE = 'schedule.manage';

export interface ScheduleLabels {
  readonly column: {
    readonly name: string;
    readonly cron: string;
    readonly objective: string;
    readonly timezone: string;
    readonly nextRun: string;
    readonly enabled: string;
  };
  readonly never: string;
  readonly enable: string;
  readonly enabling: string;
  readonly disable: string;
  readonly disabling: string;
  readonly save: string;
  readonly saving: string;
  readonly delete: string;
  readonly deleteConsequence: string;
  readonly deleteCancel: string;
  readonly deleteClose: string;
  readonly create: {
    readonly title: string;
    readonly jobId: string;
    readonly name: string;
    readonly cron: string;
    readonly objective: string;
    readonly timezone: string;
    /**
     * What each field is, beside the field.
     *
     * A cron box with no example is a box somebody guesses at, and the
     * deployment's refusal does not say which of the five positions was wrong.
     * The identifier-versus-name distinction has the same shape: both are
     * strings, only one of them is safe to change later, and nothing on the
     * form said which.
     */
    readonly help: {
      readonly jobId: string;
      readonly name: string;
      readonly cron: string;
      readonly objective: string;
      readonly timezone: string;
    };
    readonly submit: string;
    readonly submitting: string;
    /**
     * Confirms what was just created and carries `{name}`.
     *
     * Shown beside the next run rather than folded into it: the two are
     * different facts an operator checks separately — "did the form take
     * my identifier" and "did I get the cron field right" — and the second
     * is the one a preview exists for at all.
     */
    readonly created: string;
    readonly previewing: string;
    /** Precedes the firings a valid cron expression would produce. */
    readonly previewLabel: string;
  };
  readonly failed: string;
  readonly unreachable: string;
}

export interface ScheduleRecord {
  readonly jobId: string;
  readonly name: string;
  readonly cron: string;
  readonly objective: string;
  readonly timezone: string;
  readonly enabled: boolean;
  readonly nextRun: Timestamp | null;
}

export interface SchedulesProps {
  readonly schedules: readonly ScheduleRecord[];
  readonly viewer: Viewer;
  readonly labels: ScheduleLabels;
  readonly locale: Locale;
  /** The deployment's own timezone, for the same reason every other timestamp on the page reads it. */
  readonly zone: string;
  /** The instant a written response is read against, once. */
  readonly now: Date;
}

function text(record: unknown, name: string): string {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'string' ? found : '';
}

const BLANK_CREATE = { jobId: '', name: '', cron: '', objective: '', timezone: 'UTC' };

/**
 * What a preview answered for one `(cron, timezone)` pair.
 *
 * Tagged by outcome rather than nullable fields on one shape: a preview
 * either has firings or it has a refusal, never both and never neither, and
 * a caller reading `.status` cannot reach for the field the other branch
 * would have populated.
 */
type CronPreview =
  | {
      readonly cron: string;
      readonly timezone: string;
      readonly status: 'ready';
      readonly firings: readonly Timestamp[];
    }
  | {
      readonly cron: string;
      readonly timezone: string;
      readonly status: 'refused';
      readonly reason: string;
    };

/** Every scheduled investigation this team holds, with the four writes on it. */
export function Schedules({
  schedules,
  viewer,
  labels,
  locale,
  zone,
  now,
}: SchedulesProps): ReactNode {
  const [records, setRecords] = useState<readonly ScheduleRecord[]>(schedules);
  const [cronDraft, setCronDraft] = useState<Readonly<Record<string, string>>>({});
  const [deleting, setDeleting] = useState<string | null>(null);
  const [create, setCreate] = useState(BLANK_CREATE);
  const [created, setCreated] = useState<ScheduleRecord | null>(null);
  const [busy, setBusy] = useState('');
  const [failure, setFailure] = useState('');
  const [cronPreview, setCronPreview] = useState<CronPreview | null>(null);
  const [previewingCron, setPreviewingCron] = useState(false);

  /**
   * `body`, as the deployment answers a write — formatted the same way the
   * server-rendered table already formats its own `nextRun`, so a schedule
   * created, toggled or re-cronned in this session reads no differently to
   * one that was already here when the page loaded.
   */
  function scheduleFrom(body: unknown): ScheduleRecord {
    const nextRunAt = text(body, 'next_run_at');
    return {
      jobId: text(body, 'job_id'),
      name: text(body, 'name'),
      cron: text(body, 'cron'),
      objective: text(body, 'objective'),
      timezone: text(body, 'timezone'),
      enabled: Reflect.get(Object(body), 'enabled') === true,
      nextRun: nextRunAt === '' ? null : timestamp(locale, nextRunAt, now, zone),
    };
  }

  /**
   * Ask what `cron` would fire, storing nothing — kept apart from `ask` and
   * `failure` above on purpose. A refused preview names what is wrong with
   * the field the operator has not left yet; folding it into the same
   * banner every write shares would either clear a write's own refusal the
   * moment a preview runs, or leave a preview's refusal sitting under a
   * button it has nothing to do with.
   */
  async function requestCronPreview(): Promise<void> {
    const cron = create.cron;
    const timezone = create.timezone;
    if (cron.trim() === '') return;
    setPreviewingCron(true);
    let response: Response;
    try {
      response = await fetch(SCHEDULE_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          jobId: '',
          operation: 'preview',
          payload: { cron, timezone },
        }),
      });
    } catch {
      setPreviewingCron(false);
      setCronPreview({ cron, timezone, status: 'refused', reason: labels.unreachable });
      return;
    }
    const body: unknown = await response.json().catch(() => ({}));
    setPreviewingCron(false);
    if (!response.ok) {
      const reason: unknown = Reflect.get(Object(body), 'reason');
      setCronPreview({
        cron,
        timezone,
        status: 'refused',
        reason: typeof reason === 'string' && reason !== '' ? reason : labels.failed,
      });
      return;
    }
    const answer: unknown = Reflect.get(Object(body), 'answer');
    const rawFirings: unknown = Reflect.get(Object(answer), 'firings');
    const firings = (Array.isArray(rawFirings) ? rawFirings : [])
      .map((entry) => text(entry, 'at'))
      .filter((at) => at !== '')
      .map((at) => timestamp(locale, at, now, zone));
    setCronPreview({ cron, timezone, status: 'ready', firings });
  }

  async function ask(
    jobId: string,
    operation: string,
    payload?: unknown,
  ): Promise<unknown> {
    setFailure('');
    let response: Response;
    try {
      response = await fetch(SCHEDULE_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ jobId, operation, payload }),
      });
    } catch {
      setFailure(labels.unreachable);
      return null;
    }
    const body: unknown = await response.json().catch(() => ({}));
    if (!response.ok) {
      const reason: unknown = Reflect.get(Object(body), 'reason');
      setFailure(typeof reason === 'string' && reason !== '' ? reason : labels.failed);
      return null;
    }
    return Reflect.get(Object(body), 'answer');
  }

  async function toggle(schedule: ScheduleRecord): Promise<void> {
    const operation = schedule.enabled ? 'disable' : 'enable';
    setBusy(`${operation}-${schedule.jobId}`);
    const found = await ask(schedule.jobId, operation);
    setBusy('');
    if (found === null) return;
    const updated = scheduleFrom(found);
    setRecords((was) =>
      was.map((each) => (each.jobId === updated.jobId ? updated : each)),
    );
  }

  async function saveCron(schedule: ScheduleRecord): Promise<void> {
    const cron = cronDraft[schedule.jobId] ?? schedule.cron;
    setBusy(`save-${schedule.jobId}`);
    const found = await ask(schedule.jobId, 'update', {
      cron,
      timezone: schedule.timezone,
    });
    setBusy('');
    if (found === null) return;
    const updated = scheduleFrom(found);
    setRecords((was) =>
      was.map((each) => (each.jobId === updated.jobId ? updated : each)),
    );
    setCronDraft((was) =>
      Object.fromEntries(
        Object.entries(was).filter(([jobId]) => jobId !== schedule.jobId),
      ),
    );
  }

  async function confirmDelete(): Promise<void> {
    const jobId = deleting;
    if (jobId === null) return;
    setBusy(`delete-${jobId}`);
    const found = await ask(jobId, 'delete');
    setBusy('');
    setDeleting(null);
    if (found === null) return;
    setRecords((was) => was.filter((each) => each.jobId !== jobId));
  }

  async function submitCreate(): Promise<void> {
    setBusy('create');
    setCreated(null);
    const found = await ask('', 'create', {
      job_id: create.jobId,
      name: create.name,
      cron: create.cron,
      objective: create.objective,
      timezone: create.timezone,
    });
    setBusy('');
    if (found === null) return;
    const record = scheduleFrom(found);
    setRecords((was) => [...was, record]);
    setCreate(BLANK_CREATE);
    setCreated(record);
  }

  if (!may(viewer, MANAGE)) return null;

  const deletingRecord = records.find((each) => each.jobId === deleting) ?? null;
  const creatable =
    create.jobId.trim() !== '' &&
    create.name.trim() !== '' &&
    create.cron.trim() !== '' &&
    create.objective.trim() !== '';
  // Only while it still answers the field as it now reads — the moment
  // either input changes again, the preview it was taken of is a different
  // question and showing the old answer would be showing the wrong one.
  const currentPreview =
    cronPreview !== null &&
    cronPreview.cron === create.cron &&
    cronPreview.timezone === create.timezone
      ? cronPreview
      : null;

  return (
    <div data-testid="schedules" className="flex flex-col gap-5">
      <div className="w-full overflow-x-auto">
        <table className="w-full text-small">
          <thead>
            <tr>
              {[
                labels.column.name,
                labels.column.cron,
                labels.column.objective,
                labels.column.timezone,
                labels.column.nextRun,
                labels.column.enabled,
              ].map((header) => (
                <th
                  key={header}
                  scope="col"
                  className="text-left text-micro uppercase text-muted px-3 pb-2 edge border-border border-t-0 border-x-0"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map((schedule) => {
              const draft = cronDraft[schedule.jobId] ?? schedule.cron;
              const changed = draft !== schedule.cron;
              return (
                <tr
                  key={schedule.jobId}
                  data-testid="schedule"
                  data-job={schedule.jobId}
                >
                  <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-all">
                    {schedule.name}
                  </td>
                  <td className="px-3 py-2 edge border-border border-t-0 border-x-0 min-w-0">
                    <div className="flex items-center gap-2">
                      <Input
                        label={labels.column.cron}
                        name={`cron-${schedule.jobId}`}
                        value={draft}
                        onValueChange={(value) => {
                          setCronDraft((was) => ({ ...was, [schedule.jobId]: value }));
                        }}
                      />
                      {changed ? (
                        <Button
                          data-testid="save-schedule-cron"
                          data-job={schedule.jobId}
                          state={
                            busy === `save-${schedule.jobId}` ? 'loading' : 'default'
                          }
                          onClick={() => {
                            void saveCron(schedule);
                          }}
                        >
                          {busy === `save-${schedule.jobId}`
                            ? labels.saving
                            : labels.save}
                        </Button>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-3 py-2 edge border-border border-t-0 border-x-0 break-all">
                    {schedule.objective}
                  </td>
                  <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                    {schedule.timezone}
                  </td>
                  <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                    {schedule.nextRun === null ? (
                      <span className="text-muted">{labels.never}</span>
                    ) : (
                      <time
                        dateTime={schedule.nextRun.iso}
                        title={schedule.nextRun.absolute}
                      >
                        {schedule.nextRun.relative}
                      </time>
                    )}
                  </td>
                  <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge status={schedule.enabled ? 'healthy' : 'disabled'} />
                      <Button
                        data-testid="toggle-schedule"
                        data-job={schedule.jobId}
                        state={
                          busy ===
                          `${schedule.enabled ? 'disable' : 'enable'}-${schedule.jobId}`
                            ? 'loading'
                            : 'default'
                        }
                        onClick={() => {
                          void toggle(schedule);
                        }}
                      >
                        {schedule.enabled
                          ? busy === `disable-${schedule.jobId}`
                            ? labels.disabling
                            : labels.disable
                          : busy === `enable-${schedule.jobId}`
                            ? labels.enabling
                            : labels.enable}
                      </Button>
                      <Button
                        variant="destructive"
                        data-testid="delete-schedule"
                        data-job={schedule.jobId}
                        onClick={() => {
                          setDeleting(schedule.jobId);
                        }}
                      >
                        {labels.delete}
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ConfirmDestructive
        open={deletingRecord !== null}
        target={deletingRecord?.name ?? ''}
        action={labels.delete}
        consequence={labels.deleteConsequence}
        labels={{ close: labels.deleteClose, cancel: labels.deleteCancel }}
        onConfirm={() => {
          void confirmDelete();
        }}
        onCancel={() => {
          setDeleting(null);
        }}
      />

      <div data-testid="create-schedule" className="flex flex-col gap-3">
        <h4 className="text-strong">{labels.create.title}</h4>
        <div className="flex flex-wrap items-end gap-3">
          <Input
            label={labels.create.jobId}
            description={labels.create.help.jobId}
            name="create-job-id"
            value={create.jobId}
            onValueChange={(value) => {
              setCreate((was) => ({ ...was, jobId: value }));
            }}
          />
          <Input
            label={labels.create.name}
            description={labels.create.help.name}
            name="create-name"
            value={create.name}
            onValueChange={(value) => {
              setCreate((was) => ({ ...was, name: value }));
            }}
          />
          <Input
            label={labels.create.cron}
            description={labels.create.help.cron}
            name="create-cron"
            value={create.cron}
            onValueChange={(value) => {
              setCreate((was) => ({ ...was, cron: value }));
            }}
            onBlur={() => {
              void requestCronPreview();
            }}
          />
          <Input
            label={labels.create.objective}
            description={labels.create.help.objective}
            name="create-objective"
            value={create.objective}
            onValueChange={(value) => {
              setCreate((was) => ({ ...was, objective: value }));
            }}
          />
          <Input
            label={labels.create.timezone}
            description={labels.create.help.timezone}
            name="create-timezone"
            value={create.timezone}
            onValueChange={(value) => {
              setCreate((was) => ({ ...was, timezone: value }));
            }}
            onBlur={() => {
              // The preview is of the pair, not of the cron field alone —
              // a zone changed after the cron already settled makes the
              // firings shown wrong for the pair now on the form.
              void requestCronPreview();
            }}
          />
          <Button
            variant="primary"
            data-testid="submit-create-schedule"
            state={busy === 'create' ? 'loading' : creatable ? 'default' : 'disabled'}
            onClick={() => {
              void submitCreate();
            }}
          >
            {busy === 'create' ? labels.create.submitting : labels.create.submit}
          </Button>
        </div>

        {/* What "0 8 * * 1" actually means, before it is ever saved. Beside
            the field it describes rather than after the submit button,
            because the question it answers — did I get the field positions
            right — is one the cron helper text alone cannot answer. */}
        {previewingCron ? (
          <p data-testid="cron-preview-loading" className="text-meta text-muted">
            {labels.create.previewing}
          </p>
        ) : null}
        {currentPreview?.status === 'refused' ? (
          <p data-testid="cron-preview-refused" className="text-meta text-danger">
            {currentPreview.reason}
          </p>
        ) : null}
        {currentPreview?.status === 'ready' ? (
          <p data-testid="cron-preview" className="text-meta text-muted">
            {labels.create.previewLabel}{' '}
            {currentPreview.firings.map((firing, index) => (
              <span key={firing.iso}>
                {index > 0 ? ', ' : ''}
                <time dateTime={firing.iso} title={firing.absolute}>
                  {firing.relative}
                </time>
              </span>
            ))}
          </p>
        ) : null}
      </div>

      {/* The one thing a bare submit button never told anybody: whether the
          cron they typed produced the firing they meant. Named and dated
          rather than folded into the row it just added to the table above,
          because a table an operator has to go and find a row in is not a
          form telling them anything. */}
      {created === null ? null : (
        <p data-testid="schedule-created" className="text-meta text-success">
          {labels.create.created.replace('{name}', created.name)}{' '}
          {`${labels.column.nextRun}:`}{' '}
          {created.nextRun === null ? (
            labels.never
          ) : (
            <time dateTime={created.nextRun.iso} title={created.nextRun.absolute}>
              {created.nextRun.relative}
            </time>
          )}
        </p>
      )}

      {failure === '' ? null : (
        <span data-testid="schedule-failure" className="text-meta text-danger">
          {failure}
        </span>
      )}
    </div>
  );
}
