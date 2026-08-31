/**
 * Derivations the Pipeline tab's metro line and Tools card need, none of
 * them served directly: what regime a stage runs under, which of the three
 * station treatments it draws in, and how many enabled tools fall into each
 * of the three side-effect buckets the artboard's hero card names.
 */

/** The one stage whose own step is deterministic rather than model-driven. */
const DETERMINISTIC_STAGE = 'plan_evidence';

/**
 * What a stage's own mono line reads: the bound model role, "deterministic"
 * for the one stage that is not model-driven, or "no model" otherwise.
 */
export function stageRegime(stageName: string, modelRole: string): string {
  if (modelRole !== '') return `model: ${modelRole}`;
  if (stageName === DETERMINISTIC_STAGE) return 'deterministic';
  return 'no model';
}

/**
 * The one of three wells a stage's own station draws in the metro line: it
 * already ran in this run, it is the one running right now, or nothing has
 * reached it yet.
 */
export type StageTreatment = 'passed' | 'running' | 'not-reached';

/**
 * Which of the three `StageTreatment`s `stageName` draws in, given the
 * pipeline's own order and the one stage (if any) a run is currently on.
 *
 * `currentStageName` is `undefined` whenever nothing names it -- no run in
 * flight, or one in flight that nothing yet records the stage of. Both read
 * the same way here: every station honestly draws not-reached rather than
 * guessing which one is lit. A `currentStageName` this pipeline's own order
 * does not contain degrades the same way, for the same reason.
 */
export function stageTreatment(
  order: readonly string[],
  stageName: string,
  currentStageName: string | undefined,
): StageTreatment {
  if (currentStageName === undefined) return 'not-reached';
  if (stageName === currentStageName) return 'running';
  const current = order.indexOf(currentStageName);
  const mine = order.indexOf(stageName);
  if (current === -1 || mine === -1) return 'not-reached';
  return mine < current ? 'passed' : 'not-reached';
}

/**
 * The well each treatment draws its icon in, coloured by role rather than by
 * a state-specific hex so a theme change reaches these for free. `passed`
 * and `running` share the accent ring the board draws on both, and differ
 * only in how filled the well is -- tinted for one, solid for the other --
 * which is what keeps "already ran" legible beside "running now".
 */
export const STAGE_TREATMENT_CLASSES: Readonly<Record<StageTreatment, string>> = {
  passed: 'border-accent bg-success-bg text-accent',
  running: 'border-accent bg-accent text-on-accent',
  'not-reached': 'border-border-strong bg-neutral-bg text-muted',
};

export interface ToolSummary {
  readonly read: number;
  readonly writeReversible: number;
  readonly destructive: number;
  /** Enabled tools total -- read + writeReversible + destructive. */
  readonly enabled: number;
}

/** A capability row, as `capability-rows.ts` already shapes one. */
interface ToolRow {
  readonly known: boolean;
  readonly available: boolean;
  readonly sideEffect: string;
}

/**
 * `rows`, folded into the three buckets AN-A5 names: leitura (read +
 * read_sensitive), escrita reversível, and destrutiva (write_irreversible +
 * destructive, both carrying real risk). Counts only enabled tools -- known
 * and available -- the same test "X of Y enabled" already applies.
 */
export function toolSummary(rows: readonly ToolRow[]): ToolSummary {
  let read = 0;
  let writeReversible = 0;
  let destructive = 0;
  for (const row of rows) {
    if (!row.known || !row.available) continue;
    if (row.sideEffect === 'read' || row.sideEffect === 'read_sensitive') read += 1;
    else if (row.sideEffect === 'write_reversible') writeReversible += 1;
    else if (
      row.sideEffect === 'write_irreversible' ||
      row.sideEffect === 'destructive'
    )
      destructive += 1;
  }
  return {
    read,
    writeReversible,
    destructive,
    enabled: read + writeReversible + destructive,
  };
}
