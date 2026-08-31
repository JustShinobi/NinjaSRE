/**
 * Two derivations the Pipeline tab's metro line and Tools card need, neither
 * served directly: what regime a stage runs under, and how many enabled
 * tools fall into each of the three side-effect buckets the artboard's hero
 * card names.
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
