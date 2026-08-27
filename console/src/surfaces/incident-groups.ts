import { isTerminalIncident } from '@/design/status';
import { list, text } from './read';

/**
 * A repeating estate, folded back into the problems it actually has.
 *
 * An estate that raises the same seven conditions all day produces fifty
 * incidents, and a screen that lists them one per row says there are fifty
 * problems. There are seven. The second firing of one cause is a recurrence,
 * and the store already knows which firings those are: it carries a
 * correlation key built from the condition and the resource, and it is the key
 * it would have reopened the incident under had the first one still been open.
 *
 * So the group key is that field, never the title. Two firings of one cause
 * share a key by construction, and two unrelated incidents can easily share
 * prose — `Target down` says nothing about which target.
 *
 * Nothing here decides anything the deployment decides. It folds rows the
 * gateway sent, by a field the gateway sent, and every value on a group is
 * taken from one of its own occurrences rather than invented to describe a
 * set.
 */

/** Most severe first. The order the deployment's own listing sorts by. */
const SEVERITY_ORDER: readonly string[] = ['critical', 'high', 'medium', 'low', 'info'];

/** One firing, as a row of an expanded group. */
export interface IncidentOccurrence {
  readonly id: string;
  /** The short address the row links to. */
  readonly publicId: string;
  readonly summary: string;
  readonly state: string;
  readonly severity: string;
  /** ISO 8601, as the deployment recorded it. */
  readonly at: string;
  /** The investigation that ran against it, when one did. */
  readonly runId: string;
}

/** One cause, and every time it fired. */
export interface IncidentGroup {
  /** The correlation key, or the incident's own id when it carries none. */
  readonly key: string;
  /** The condition, taken from the newest firing rather than composed. */
  readonly title: string;
  /** Every resource anything under this group fired on, in the order met. */
  readonly subjects: readonly string[];
  readonly detector: string;
  readonly count: number;
  /** The worst severity anything under it fired at. */
  readonly severity: string;
  /**
   * What the group reads as: the newest firing that has not ended, or the
   * newest of all when every one of them has.
   *
   * Never a word invented to describe a set, and never simply the newest —
   * a group whose latest firing resolved while an earlier one is still being
   * investigated would then read "Resolved" while carrying an open incident,
   * which is the same class of lie as counting a finished incident as one
   * waiting on a person.
   */
  readonly state: string;
  /** Whether anything under it has not ended. */
  readonly live: boolean;
  /** The newest firing, ISO 8601. */
  readonly lastAt: string;
  /** The oldest, so a group can say how long it has been recurring. */
  readonly firstAt: string;
  /** Newest first. */
  readonly occurrences: readonly IncidentOccurrence[];
}

function severityRank(severity: string): number {
  const found = SEVERITY_ORDER.indexOf(severity);
  return found === -1 ? SEVERITY_ORDER.length : found;
}

/** The instant `at` names, or negative infinity when it names none. */
function instant(at: string): number {
  const parsed = Date.parse(at);
  return Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed;
}

function occurrenceOf(record: unknown): IncidentOccurrence {
  return {
    id: text(record, 'incident_id'),
    publicId: text(record, 'public_id'),
    summary: text(record, 'summary'),
    state: text(record, 'state'),
    severity: text(record, 'severity'),
    at: text(record, 'opened_at'),
    runId: text(record, 'run_id'),
  };
}

/**
 * The key `record` groups under.
 *
 * An incident with no correlation key gets its own identifier, so it stands
 * alone. Folding every keyless incident together under the empty string would
 * invent a problem nobody has — and a deployment one version behind, which is
 * the only way a key goes missing, is not a fault.
 */
function keyOf(record: unknown): string {
  const correlation = text(record, 'correlation_key');
  return correlation === '' ? text(record, 'incident_id') : correlation;
}

/**
 * `records` folded into one row per cause, most pressing first.
 *
 * The order is: anything still happening above anything that is over, then by
 * severity, then by the newest firing. Sorting by time alone is what made the
 * flat listing unreadable — it put this morning's closure above last week's
 * outage, every time.
 */
export function groupBySubject(records: readonly unknown[]): readonly IncidentGroup[] {
  const collected = new Map<string, unknown[]>();
  for (const record of records) {
    const key = keyOf(record);
    const held = collected.get(key);
    if (held === undefined) collected.set(key, [record]);
    else held.push(record);
  }

  const groups: IncidentGroup[] = [];
  for (const [key, firings] of collected) {
    const newestFirst = [...firings].sort(
      (left, right) =>
        instant(text(right, 'opened_at')) - instant(text(left, 'opened_at')),
    );
    const newest = newestFirst[0];
    const oldest = newestFirst[newestFirst.length - 1];

    const subjects: string[] = [];
    for (const firing of newestFirst) {
      for (const subject of list(firing, 'subjects')) {
        const named = typeof subject === 'string' ? subject : '';
        if (named !== '' && !subjects.includes(named)) subjects.push(named);
      }
    }

    // What the row reads as. The newest *live* firing when there is one, so a
    // group can never announce an ending it has not had.
    const live = newestFirst.filter(
      (firing) => !isTerminalIncident(text(firing, 'state')),
    );
    const speaking = live.length > 0 ? live[0] : newest;

    const worst = [...newestFirst].sort(
      (left, right) =>
        severityRank(text(left, 'severity')) - severityRank(text(right, 'severity')),
    )[0];

    groups.push({
      key,
      title: text(newest, 'title'),
      subjects,
      detector: text(newest, 'detector'),
      count: newestFirst.length,
      severity: text(worst, 'severity'),
      state: text(speaking, 'state'),
      live: live.length > 0,
      lastAt: text(newest, 'opened_at'),
      firstAt: text(oldest, 'opened_at'),
      occurrences: newestFirst.map(occurrenceOf),
    });
  }

  return groups.sort((left, right) => {
    if (left.live !== right.live) return left.live ? -1 : 1;
    const bySeverity = severityRank(left.severity) - severityRank(right.severity);
    if (bySeverity !== 0) return bySeverity;
    return instant(right.lastAt) - instant(left.lastAt);
  });
}
