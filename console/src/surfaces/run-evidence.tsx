import type { ReactNode } from 'react';

import { ResolvedChip } from '@/components/status';
import { message, type Locale } from '@/i18n/messages';

/**
 * How sure a run was, as a chip, without inventing a percentage.
 *
 * The obvious design is the one the reference product ships: a number, "92%
 * confidence", beside the run's name. It is the wrong one. That number is the
 * model's opinion of its own output, and printing it in the column where
 * duration and token count live makes the whole row read as measured.
 *
 * What *is* measured is already in the trace. The run calls
 * `assess_evidence_sufficiency` with the evidence supporting its conclusion and
 * the evidence still missing, and the gateway counts those two arguments. So
 * this chip says "four of four claims backed" — a count of things the run
 * itself named, in the same place the percentage would have gone, doing the
 * same triage job for a reader scanning a list.
 *
 * Three states rather than two. A run that never assessed its evidence said
 * nothing, and is drawn as the neutral dash rather than borrowing the green of
 * a run that assessed and found nothing outstanding.
 *
 * A run that *did* assess and named nothing in either list is the same silence
 * wearing a different hat, and it is the one that shipped wrong: staging drew
 * fifty runs as a green "0 of 0 claims backed", which reads as proof and was
 * the absence of any. Nought claims is the dash too.
 */

/** What a run's record says about its own evidence. */
export interface RunEvidence {
  readonly assessed: boolean;
  readonly backed: number;
  readonly missing: number;
}

/** The evidence `record` carries, in the fields the gateway serves it in. */
export function evidenceOf(record: {
  readonly evidence_assessed?: unknown;
  readonly evidence_backed?: unknown;
  readonly evidence_missing?: unknown;
}): RunEvidence {
  const counted = (value: unknown): number =>
    typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.trunc(value) : 0;
  return {
    assessed: record.evidence_assessed === true,
    backed: counted(record.evidence_backed),
    missing: counted(record.evidence_missing),
  };
}

export interface EvidenceChipProps {
  readonly locale: Locale;
  readonly evidence: RunEvidence;
  readonly className?: string | undefined;
}

/** The chip a run wears wherever it is listed, and again where it is opened. */
export function EvidenceChip({
  locale,
  evidence,
  className,
}: EvidenceChipProps): ReactNode {
  const claims = evidence.backed + evidence.missing;

  if (!evidence.assessed || claims === 0) {
    return (
      <ResolvedChip
        role="neutral"
        shape="dash"
        label={message(locale, 'run.evidence.unassessed')}
        title={message(locale, 'run.evidence.unassessed.explain')}
        testId="run-evidence"
        className={className}
      />
    );
  }

  const label = message(locale, 'run.evidence.backed', {
    backed: String(evidence.backed),
    claims: String(claims),
  });

  // Sufficient is not "backed is high". It is "nothing is outstanding", which
  // is what the run itself said and the only thing the count can prove.
  return evidence.missing === 0 ? (
    <ResolvedChip
      role="success"
      shape="filled-circle"
      label={label}
      testId="run-evidence"
      className={className}
    />
  ) : (
    <ResolvedChip
      role="warning"
      shape="hollow-circle"
      label={label}
      title={message(locale, 'run.evidence.missing.explain', {
        missing: String(evidence.missing),
      })}
      testId="run-evidence"
      className={className}
    />
  );
}
