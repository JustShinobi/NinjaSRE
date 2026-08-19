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
 * guardrails, what each is called, and — for the three that are a closed
 * set rather than a boolean or a free-form name — what each of their own
 * values means. `masking.level`, `guardrails.mode` and `approvals.threshold`
 * used to reach the Value cell as the bare schema slug (`write_reversible`,
 * in a monospace face, beside every other row's own sentence); `described`
 * below and the three dictionaries that call it exist to end that, the way
 * `sideEffectLabel` already did for a proposal card's own side effect.
 *
 * The three array-shaped guardrail fields (`custom_patterns`,
 * `disabled_rules`, `autonomous_capabilities`) are deliberately absent from
 * this list, matching the settings page's existing judgment: a list's
 * "effective value" would be its own JSON dump, which is not a sentence
 * anybody reads as a guardrail's state. `custom_patterns` stays reachable
 * through its own editable list control, not this summary; `disabled_rules`
 * and `autonomous_capabilities` are plain string lists with no control
 * anywhere in the console yet (`CONFIG_FIELDS_NO_CONTROL` in
 * `shell/config-ownership.ts`), so neither this summary nor a list control
 * is where either is reachable today.
 */

export interface GuardrailFieldSpec {
  readonly path: string;
  readonly label: MessageKey;
  /** Overrides the type-driven formatting for a field whose schema type
   * ('integer') does not say on its own that it is a duration. */
  readonly format?: ((value: unknown, locale: Locale) => string) | undefined;
}

/**
 * `value` in words, or the raw slug itself when `words` has none for it.
 *
 * The same fallback discipline `sideEffectLabel` (`surfaces/side-effects.ts`)
 * and `postureLabel` (`surfaces/postures.ts`) already apply for their own
 * vocabularies, reproduced here rather than imported because the three
 * dictionaries below are read nowhere but this table: a deployment sends
 * these three fields as a closed-set schema slug, and a slug this build does
 * not recognise still has to render as something a reader can act on, never
 * as an empty cell (`effectiveRows` turns the empty string this returns into
 * an explicit "not set" marker) or a crash.
 */
function described(
  value: unknown,
  words: Readonly<Record<string, MessageKey>>,
  locale: Locale,
): string {
  if (typeof value !== 'string' || value === '') return '';
  const key = words[value];
  return key === undefined ? value : message(locale, key);
}

/**
 * The masking levels this console has words for
 * (`MASKING_POLICY_LEVELS` in `config/constants/security.py`).
 * `off`/`standard`/`strict` already read fine as words on their own; only
 * `local_models_exempt` does not, so all four get an entry rather than three
 * plain values and one dressed-up one.
 */
const MASKING_LEVEL_WORDS: Readonly<Record<string, MessageKey>> = {
  off: 'guardrail.maskingLevel.off',
  standard: 'guardrail.maskingLevel.standard',
  strict: 'guardrail.maskingLevel.strict',
  local_models_exempt: 'guardrail.maskingLevel.local_models_exempt',
};

/**
 * The two guardrail modes (`GuardrailMode` in
 * `platform/config_service/schema/policies.py`), said as what each one does
 * to a match rather than as the schema's own word for it.
 */
const GUARDRAIL_MODE_WORDS: Readonly<Record<string, MessageKey>> = {
  enforcing: 'guardrail.mode.enforcing',
  observing: 'guardrail.mode.observing',
};

/**
 * The approval thresholds the schema allows (`ApprovalPolicySettings` in
 * `platform/config_service/schema/policies.py` refuses anything above
 * `write_reversible` — a write must always be able to reach a person).
 *
 * Said as what the threshold actually gates — the mockup's own "Every write
 * needs a person" is this dictionary's entry for `write_reversible`, the
 * schema's own default — rather than the side-effect card's sentence
 * (`sideEffectLabel`), which says what a *level* is, not what this
 * *threshold* does; the two questions read differently even where the slug
 * is spelled the same.
 */
const APPROVAL_THRESHOLD_WORDS: Readonly<Record<string, MessageKey>> = {
  read: 'guardrail.approvalThreshold.read',
  read_sensitive: 'guardrail.approvalThreshold.read_sensitive',
  write_reversible: 'guardrail.approvalThreshold.write_reversible',
};

/** The six guardrail scalars, in the order the table draws them. */
export const GUARDRAIL_FIELDS: readonly GuardrailFieldSpec[] = [
  {
    path: 'policies.masking.enabled',
    label: 'settings.autonomy.guardrails.masking.enabled',
  },
  {
    path: 'policies.masking.level',
    label: 'settings.autonomy.guardrails.masking.level',
    format: (value, locale) => described(value, MASKING_LEVEL_WORDS, locale),
  },
  {
    path: 'policies.guardrails.mode',
    label: 'settings.autonomy.guardrails.mode',
    format: (value, locale) => described(value, GUARDRAIL_MODE_WORDS, locale),
  },
  {
    path: 'policies.guardrails.ruleset',
    label: 'settings.autonomy.guardrails.ruleset',
  },
  {
    path: 'policies.approvals.threshold',
    label: 'settings.autonomy.guardrails.threshold',
    format: (value, locale) => described(value, APPROVAL_THRESHOLD_WORDS, locale),
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
