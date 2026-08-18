import { message, type Locale } from '@/i18n/messages';
import type { MessageKey } from '@/i18n/en';
import type { EffectiveFieldRow } from '@/design/resolution-preview';
import { effectiveRows, formatHours } from '../effective-fields';
import type { EditableField } from '../preview';

/**
 * What a guardrail's cell says, resolved once and read from two places.
 *
 * Posture's read-only summary and the Guardrails tab's own editable table
 * both draw the same six settings — masking, secret detection, and the
 * approval gate — and both owe the same property: the Value cell is never
 * blank, and Set at names where the value came from in words distinct from
 * the value itself. A single field list and a single resolver is what keeps
 * that property true in both places at once; two field lists maintained
 * separately is exactly how the two appearances would drift apart.
 *
 * Delegates to `effectiveRows` (`surfaces/effective-fields.ts`) rather than
 * re-deriving its rules: that function already owns "the override when one
 * is recorded, the schema default otherwise" and "an explicit 'not set'
 * marker rather than an empty cell", and `EffectiveFieldsTable`
 * (`design/resolution-preview.tsx`) already throws if either promise is
 * broken. This module's job is narrower — naming which six fields are
 * guardrails, and what each is called.
 *
 * The three array-shaped guardrail fields (`custom_patterns`,
 * `disabled_rules`, `autonomous_capabilities`) are deliberately absent from
 * this list, matching the settings page's existing judgment: a list's
 * "effective value" would be its own JSON dump, which is not a sentence
 * anybody reads as a guardrail's state. Those three stay reachable through
 * their own editable list controls, not this summary.
 */

export interface GuardrailFieldSpec {
  readonly path: string;
  readonly label: MessageKey;
  /** Overrides the type-driven formatting for a field whose schema type
   * ('integer') does not say on its own that it is a duration. */
  readonly format?: ((value: unknown, locale: Locale) => string) | undefined;
}

/** The six guardrail scalars, in the order the table draws them. */
export const GUARDRAIL_FIELDS: readonly GuardrailFieldSpec[] = [
  {
    path: 'policies.masking.enabled',
    label: 'settings.autonomy.guardrails.masking.enabled',
  },
  {
    path: 'policies.masking.level',
    label: 'settings.autonomy.guardrails.masking.level',
  },
  { path: 'policies.guardrails.mode', label: 'settings.autonomy.guardrails.mode' },
  {
    path: 'policies.guardrails.ruleset',
    label: 'settings.autonomy.guardrails.ruleset',
  },
  {
    path: 'policies.approvals.threshold',
    label: 'settings.autonomy.guardrails.threshold',
  },
  {
    path: 'policies.approvals.expiry_hours',
    label: 'settings.autonomy.guardrails.expiryHours',
    format: formatHours,
  },
];

/**
 * `catalogue`'s six guardrail fields, resolved into the rows
 * `EffectiveFieldsTable` draws — the single call both Posture's summary and
 * the Guardrails tab's own table make, so there is exactly one place this
 * table's text can go wrong.
 */
export function guardrailRows(
  catalogue: readonly EditableField[],
  locale: Locale,
): readonly EffectiveFieldRow[] {
  return effectiveRows(
    GUARDRAIL_FIELDS.map(({ path, label, format }) => ({
      path,
      label: message(locale, label),
      format,
    })),
    catalogue,
    locale,
  );
}
