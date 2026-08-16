'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input, Select } from '@/components/form';
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

/**
 * A readable frequency, standing in for a cron expression.
 *
 * `'custom'` is not a fifth kind of schedule — it is "generate nothing", the
 * state that leaves the cron field exactly as the operator typed it. The other
 * four are the shapes an investigation is actually scheduled on: every day,
 * every weekday, once a week on a chosen day, once a month.
 */
export const SCHEDULE_FREQUENCIES = [
  'custom',
  'daily',
  'weekdays',
  'weekly',
  'monthly',
] as const;

export type ScheduleFrequency = (typeof SCHEDULE_FREQUENCIES)[number];

/** The seven days a weekly preset can land on, Monday first — a calendar week. */
export const WEEKDAYS = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday',
] as const;

export type Weekday = (typeof WEEKDAYS)[number];

/** The cron day-of-week digit each name stands for — the ordinary crontab numbering, Sunday is 0. */
const WEEKDAY_CRON_DAY: Readonly<Record<Weekday, number>> = {
  sunday: 0,
  monday: 1,
  tuesday: 2,
  wednesday: 3,
  thursday: 4,
  friday: 5,
  saturday: 6,
};

/**
 * The cron expression `frequency` stands for, at `time` (`HH:MM`) — or `null`
 * for `'custom'`, and for a time this cannot parse.
 *
 * A pure function rather than a piece of the form's own state, because the
 * question it answers — what does "every Monday at 08:00" mean, in five
 * fields — has nothing to do with a browser and everything to do with being
 * checked without one. What it never touches is whether the deployment
 * *accepts* the expression: that answer still comes only from the preview
 * this generates a value for, never from a second opinion written here.
 */
export function cronFromPreset(
  frequency: ScheduleFrequency,
  weekday: Weekday,
  time: string,
): string | null {
  if (frequency === 'custom') return null;
  const [hourText = '', minuteText = ''] = time.split(':');
  const hour = Number.parseInt(hourText, 10);
  const minute = Number.parseInt(minuteText, 10);
  if (
    !Number.isInteger(hour) ||
    !Number.isInteger(minute) ||
    hour < 0 ||
    hour > 23 ||
    minute < 0 ||
    minute > 59
  ) {
    return null;
  }
  switch (frequency) {
    case 'daily':
      return `${String(minute)} ${String(hour)} * * *`;
    case 'weekdays':
      return `${String(minute)} ${String(hour)} * * 1-5`;
    case 'weekly':
      return `${String(minute)} ${String(hour)} * * ${String(WEEKDAY_CRON_DAY[weekday])}`;
    case 'monthly':
      return `${String(minute)} ${String(hour)} 1 * *`;
  }
}

/** What a stored cron expression says, when a preset could have written it. */
export interface CronFrequency {
  readonly frequency: Exclude<ScheduleFrequency, 'custom'>;
  /** The day a weekly schedule lands on; `null` for every other shape. */
  readonly weekday: Weekday | null;
  /** `HH:MM`, zero-padded, so a column of these lines up. */
  readonly time: string;
}

/** The weekday a cron day-of-week digit names, or `undefined` for anything else. */
const CRON_DAY_WEEKDAY: ReadonlyMap<string, Weekday> = new Map(
  WEEKDAYS.map((weekday) => [String(WEEKDAY_CRON_DAY[weekday]), weekday]),
);

/** `value` as a clock field, or `null` unless it is a plain integer in `[0, bound]`. */
function clockField(value: string, bound: number): number | null {
  // Anchored and digits-only: `Number.parseInt` alone would read `9-17` as 9
  // and `*/15` as NaN-then-something, and reading a range as its first hour is
  // precisely the wrong sentence this function exists to refuse.
  if (!/^\d{1,2}$/.test(value)) return null;
  const parsed = Number.parseInt(value, 10);
  return parsed >= 0 && parsed <= bound ? parsed : null;
}

/**
 * `cron` read back as the sentence a preset would have generated it from, or
 * `null` when nothing in the preset vocabulary produces it.
 *
 * `cronFromPreset` run backwards, and deliberately partial. Cron says far more
 * than four shapes — steps, ranges, lists, named months — and this recognises
 * only what the four presets can write. Everything else is refused rather than
 * approximated, because the list this feeds is where somebody checks *when an
 * investigation runs*, and a confidently wrong sentence there is worse than
 * the raw expression it replaced: the expression can at least be looked up.
 *
 * What it never claims is whether the deployment accepts the expression. That
 * answer comes from the preview, which asks the deployment, and from nowhere
 * else.
 */
export function frequencyOfCron(cron: string): CronFrequency | null {
  const fields = cron.trim().split(/\s+/);
  if (fields.length !== 5) return null;
  const [
    minuteField = '',
    hourField = '',
    dayField = '',
    monthField = '',
    weekField = '',
  ] = fields;

  const minute = clockField(minuteField, 59);
  const hour = clockField(hourField, 23);
  if (minute === null || hour === null) return null;
  // Every shape the presets write leaves the month alone.
  if (monthField !== '*') return null;

  const time = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;

  if (dayField === '1' && weekField === '*') {
    return { frequency: 'monthly', weekday: null, time };
  }
  if (dayField !== '*') return null;
  if (weekField === '*') return { frequency: 'daily', weekday: null, time };
  if (weekField === '1-5') return { frequency: 'weekdays', weekday: null, time };

  const weekday = CRON_DAY_WEEKDAY.get(weekField);
  return weekday === undefined ? null : { frequency: 'weekly', weekday, time };
}

/**
 * `cron` as one readable line, or `null` when no preset shape recognises it.
 *
 * Kept beside `frequencyOfCron` rather than inside the component for the
 * reason every pure function here is: what "every Monday at 08:00" reads as is
 * checkable without a browser, and a rendering bug and a vocabulary bug should
 * not have to be told apart in the same place.
 */
export function readableFrequency(cron: string, labels: ScheduleLabels): string | null {
  const read = frequencyOfCron(cron);
  if (read === null) return null;
  return labels.frequencyText[read.frequency]
    .replace('{time}', read.time)
    .replace(
      '{weekday}',
      read.weekday === null ? '' : labels.create.weekdayOptions[read.weekday],
    );
}

export interface ScheduleLabels {
  readonly column: {
    readonly name: string;
    readonly cron: string;
    readonly objective: string;
    readonly timezone: string;
    readonly nextRun: string;
    readonly enabled: string;
  };
  /**
   * How a recognised expression reads in the list, one template per shape.
   *
   * Templates rather than finished sentences, because the clock and the day
   * differ per row and the catalogue is read once for the whole table.
   * `{time}` and `{weekday}` are filled here; the weekday words come from the
   * create form's own list, so the list and the form cannot drift into calling
   * Monday two different things.
   */
  readonly frequencyText: Readonly<
    Record<Exclude<ScheduleFrequency, 'custom'>, string>
  >;
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
    /** The frequency preset field: readable in, a cron expression out. */
    readonly frequency: string;
    readonly frequencyHelp: string;
    /** Every preset's own word, `'custom'` included. */
    readonly frequencyOptions: Readonly<Record<ScheduleFrequency, string>>;
    /** Shown only once `frequency` is `'weekly'` — a day means nothing otherwise. */
    readonly weekday: string;
    readonly weekdayOptions: Readonly<Record<Weekday, string>>;
    /** Shown once `frequency` names anything but `'custom'`. */
    readonly time: string;
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

/** Whether `value` is one of the frequencies this form declares presets for. */
function isFrequency(value: string): value is ScheduleFrequency {
  return (SCHEDULE_FREQUENCIES as readonly string[]).includes(value);
}

/** Whether `value` is one of the seven days a weekly preset can name. */
function isWeekday(value: string): value is Weekday {
  return (WEEKDAYS as readonly string[]).includes(value);
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
  // The preset selector's own state, apart from `create`: a preset is a way
  // of *writing* the cron field, not a second source of truth for it. Once
  // written, the cron field is what the deployment reads, and it stays fully
  // editable whether a preset wrote it or a person typed it.
  const [presetFrequency, setPresetFrequency] = useState<ScheduleFrequency>('custom');
  const [presetWeekday, setPresetWeekday] = useState<Weekday>('monday');
  const [presetTime, setPresetTime] = useState('08:00');

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
   *
   * Takes `cron` and `timezone` rather than reading `create` itself, so a
   * preset can preview the value it just generated in the same gesture that
   * writes it — `setCreate` has not necessarily re-rendered yet, and reading
   * `create.cron` here would ask about the field's previous content instead.
   */
  async function requestCronPreview(cron: string, timezone: string): Promise<void> {
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

  /**
   * `frequency`/`weekday`/`time`, turned into a cron expression and written
   * onto the field an operator would otherwise have typed by hand — then
   * previewed immediately, the same courtesy a manual edit gets on blur.
   *
   * A no-op for `'custom'` and for a time nothing can parse yet (the control
   * mid-edit): the cron field is not cleared or overwritten with nothing just
   * because the preset selector changed first.
   */
  function applyPreset(
    frequency: ScheduleFrequency,
    weekday: Weekday,
    time: string,
  ): void {
    const generated = cronFromPreset(frequency, weekday, time);
    if (generated === null) return;
    setCreate((was) => ({ ...was, cron: generated }));
    void requestCronPreview(generated, create.timezone);
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
    setPresetFrequency('custom');
    setPresetWeekday('monday');
    setPresetTime('08:00');
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
              // Read from the draft, not from the stored expression: while
              // somebody is editing, the sentence has to describe what they
              // are about to save, or it is reassuring them about the old one.
              const readable = readableFrequency(draft, labels);
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
                    {readable === null ? null : (
                      // The answer to "when does this run", above the syntax
                      // that encodes it. Absent rather than approximated when
                      // the expression is one no preset writes.
                      <p
                        className="text-meta text-muted mb-1"
                        data-testid="schedule-frequency"
                        data-job={schedule.jobId}
                      >
                        {readable}
                      </p>
                    )}
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
          <Select
            label={labels.create.frequency}
            description={labels.create.frequencyHelp}
            name="create-frequency"
            value={presetFrequency}
            options={SCHEDULE_FREQUENCIES.map((frequency) => ({
              value: frequency,
              label: labels.create.frequencyOptions[frequency],
            }))}
            onValueChange={(value) => {
              if (!isFrequency(value)) return;
              setPresetFrequency(value);
              applyPreset(value, presetWeekday, presetTime);
            }}
          />
          {presetFrequency === 'weekly' ? (
            <Select
              label={labels.create.weekday}
              name="create-weekday"
              value={presetWeekday}
              options={WEEKDAYS.map((weekday) => ({
                value: weekday,
                label: labels.create.weekdayOptions[weekday],
              }))}
              onValueChange={(value) => {
                if (!isWeekday(value)) return;
                setPresetWeekday(value);
                applyPreset(presetFrequency, value, presetTime);
              }}
            />
          ) : null}
          {presetFrequency === 'custom' ? null : (
            <Input
              label={labels.create.time}
              type="time"
              name="create-preset-time"
              value={presetTime}
              onValueChange={(value) => {
                setPresetTime(value);
                applyPreset(presetFrequency, presetWeekday, value);
              }}
            />
          )}
          <Input
            label={labels.create.cron}
            description={labels.create.help.cron}
            name="create-cron"
            value={create.cron}
            onValueChange={(value) => {
              setCreate((was) => ({ ...was, cron: value }));
            }}
            onBlur={() => {
              void requestCronPreview(create.cron, create.timezone);
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
              void requestCronPreview(create.cron, create.timezone);
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
