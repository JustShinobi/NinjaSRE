import { describe, expect, it } from 'vitest';

import { GUARDRAIL_FIELDS, guardrailRows } from '@/surfaces/settings/guardrail-values';
import type { EditableField } from '@/surfaces/preview';

/**
 * The one resolver both appearances of the guardrails table read from:
 * Posture's read-only summary and the Guardrails tab's own editable table.
 * One source for two appearances is the whole point of this module — two
 * separately-maintained field lists is exactly how the two would drift.
 */

function field(
  over: Partial<EditableField> & { readonly path: string },
): EditableField {
  return {
    label: '',
    type: 'string',
    help: '',
    section: '',
    sectionHelp: '',
    value: null,
    provenance: '',
    setHere: false,
    lockedBy: '',
    approvalGated: false,
    allowedValues: null,
    minimum: null,
    maximum: null,
    default: null,
    suggestedValue: '',
    suggestedBecause: '',
    itemFields: [],
    ...over,
  };
}

/** A catalogue carrying every field `GUARDRAIL_FIELDS` names, fully set. */
const FULL_CATALOGUE: readonly EditableField[] = [
  field({
    path: 'policies.masking.enabled',
    type: 'boolean',
    default: false,
    value: true,
    provenance: 'org-northwind',
    setHere: true,
  }),
  field({
    path: 'policies.masking.level',
    type: 'string',
    default: 'standard',
    value: 'strict',
    provenance: 'org-northwind',
    setHere: true,
  }),
  field({
    path: 'policies.guardrails.mode',
    type: 'string',
    default: 'enforcing',
    value: 'enforcing',
  }),
  field({
    path: 'policies.guardrails.ruleset',
    type: 'string',
    default: 'standard',
    value: 'standard',
  }),
  field({
    path: 'policies.approvals.threshold',
    type: 'string',
    default: 'write_reversible',
    value: 'write_reversible',
  }),
  field({
    path: 'policies.approvals.expiry_hours',
    type: 'integer',
    default: 2,
    value: 2,
  }),
];

describe('GUARDRAIL_FIELDS', () => {
  it('names exactly the six scalar guardrail settings, in the order the table draws them', () => {
    expect(GUARDRAIL_FIELDS.map((spec) => spec.path)).toEqual([
      'policies.masking.enabled',
      'policies.masking.level',
      'policies.guardrails.mode',
      'policies.guardrails.ruleset',
      'policies.approvals.threshold',
      'policies.approvals.expiry_hours',
    ]);
  });
});

describe('guardrailRows', () => {
  it('produces one row per declared guardrail, in the declared order', () => {
    const rows = guardrailRows(FULL_CATALOGUE, 'en');

    expect(rows.map((row) => row.path)).toEqual(
      GUARDRAIL_FIELDS.map((spec) => spec.path),
    );
  });

  it('resolves each field’s own effective value into the sentence its cell reads', () => {
    const rows = guardrailRows(FULL_CATALOGUE, 'en');
    const byPath = new Map(rows.map((row) => [row.path, row]));

    // A boolean reads as a state word, never the payload literal — the same
    // property `effectiveRows` guarantees, exercised here through this
    // module's own field list rather than a synthetic path.
    expect(byPath.get('policies.masking.enabled')?.value).toBe('On');
    // The three closed-set scalars each resolve to a described phrase, not
    // the bare schema slug the deployment sends — the same discipline
    // `sideEffectLabel` and `postureLabel` already apply elsewhere.
    // `ruleset` is a free-form name rather than a closed set, so it stays a
    // passthrough of whatever the deployment named.
    expect(byPath.get('policies.masking.level')?.value).toBe('Strict');
    expect(byPath.get('policies.guardrails.mode')?.value).toBe(
      'Enforcing — matches are blocked',
    );
    expect(byPath.get('policies.guardrails.ruleset')?.value).toBe('standard');
    expect(byPath.get('policies.approvals.threshold')?.value).toBe(
      'Every write needs a person',
    );
  });

  it('formats the approval expiry as a duration, through the field’s own formatter — never the bare number', () => {
    const rows = guardrailRows(FULL_CATALOGUE, 'en');
    const expiry = rows.find((row) => row.path === 'policies.approvals.expiry_hours');

    expect(expiry?.value).toBe('2 hours');
    expect(expiry?.value).not.toBe('2');
  });

  it('marks a guardrail the catalogue never sent as not set — never an empty string', () => {
    const rows = guardrailRows([], 'en');

    expect(rows).toHaveLength(GUARDRAIL_FIELDS.length);
    for (const row of rows) {
      expect(row.value).toBe('Not set');
      expect(row.value.trim()).not.toBe('');
    }
  });

  it('marks one missing guardrail as not set while the rest of the table still resolves', () => {
    const withoutRuleset = FULL_CATALOGUE.filter(
      (entry) => entry.path !== 'policies.guardrails.ruleset',
    );
    const rows = guardrailRows(withoutRuleset, 'en');
    const byPath = new Map(rows.map((row) => [row.path, row]));

    expect(byPath.get('policies.guardrails.ruleset')?.value).toBe('Not set');
    expect(byPath.get('policies.masking.enabled')?.value).toBe('On');
  });

  it('keeps the origin a separate sentence from the value, in both directions', () => {
    const rows = guardrailRows(FULL_CATALOGUE, 'en');
    const overridden = rows.find((row) => row.path === 'policies.masking.level');
    const inherited = rows.find((row) => row.path === 'policies.guardrails.mode');

    // Set on this node: Value carries the effective value, Set at names the node.
    expect(overridden?.value).toBe('Strict');
    expect(overridden?.origin).toBe('org-northwind');
    expect(overridden?.value).not.toBe(overridden?.origin);

    // Never overridden: Set at says so, in words distinct from the value itself.
    expect(inherited?.value).toBe('Enforcing — matches are blocked');
    expect(inherited?.origin).toBe('Deployment default');
    expect(inherited?.value).not.toBe(inherited?.origin);

    for (const row of rows) {
      expect(row.origin.trim()).not.toBe('');
    }
  });

  it('resolves labels for the locale asked, not always English', () => {
    const en = guardrailRows(FULL_CATALOGUE, 'en');
    const ptBr = guardrailRows(FULL_CATALOGUE, 'pt-BR');
    const enLabel = en.find((row) => row.path === 'policies.guardrails.ruleset')?.label;
    const ptLabel = ptBr.find(
      (row) => row.path === 'policies.guardrails.ruleset',
    )?.label;

    expect(enLabel).toBe('Ruleset');
    expect(ptLabel).not.toBe(enLabel);
  });
});

describe('the three fields whose slug does not already read as a sentence', () => {
  // `masking.level`, `guardrails.mode` and `approvals.threshold` are closed
  // sets the deployment sends as a schema slug — the same shape
  // `sideEffectLabel` (`surfaces/side-effects.ts`) and `postureLabel`
  // (`surfaces/postures.ts`) already exist to translate elsewhere. Proven
  // here through `guardrailRows` itself, the one function both appearances
  // of this table call, rather than through a helper exported for the
  // purpose — there is no such export; the words live only in this module.

  function catalogueWith(path: string, value: unknown): readonly EditableField[] {
    // Both `value` and `default` carry the same raw slug, so the row
    // resolves to it whichever branch `effectiveRows` takes.
    return [field({ path, value, default: value })];
  }

  function valueFor(
    path: string,
    value: unknown,
    locale: 'en' | 'pt-BR' = 'en',
  ): string {
    const rows = guardrailRows(catalogueWith(path, value), locale);
    return rows.find((row) => row.path === path)?.value ?? '';
  }

  it('says what each masking level does, for every level the deployment may send', () => {
    expect(valueFor('policies.masking.level', 'off')).toBe('Off');
    expect(valueFor('policies.masking.level', 'standard')).toBe('Standard');
    expect(valueFor('policies.masking.level', 'strict')).toBe('Strict');
    expect(valueFor('policies.masking.level', 'local_models_exempt')).toBe(
      'Exempt for local models',
    );
  });

  it('says what each guardrail mode does to a match, not the schema’s own word for it', () => {
    expect(valueFor('policies.guardrails.mode', 'enforcing')).toBe(
      'Enforcing — matches are blocked',
    );
    expect(valueFor('policies.guardrails.mode', 'observing')).toBe(
      'Observing — matches are recorded, not blocked',
    );
  });

  it('says what each approval threshold actually gates, not the side-effect level it is spelled as', () => {
    // The schema refuses a threshold above `write_reversible` — a write must
    // always be able to reach a person — so these three are every legal
    // value, not a sample of a larger set.
    expect(valueFor('policies.approvals.threshold', 'read')).toBe(
      'Every action needs a person',
    );
    expect(valueFor('policies.approvals.threshold', 'read_sensitive')).toBe(
      'Every sensitive read and write needs a person',
    );
    expect(valueFor('policies.approvals.threshold', 'write_reversible')).toBe(
      'Every write needs a person',
    );
  });

  it('falls back to the slug itself for a value none of the three dictionaries has words for', () => {
    // The values come from the deployment, not from this console. A level,
    // mode or threshold this build predates still has to render as
    // something a reader can act on, rather than an empty cell or a crash —
    // the same fallback discipline `sideEffectLabel` and `postureLabel`
    // apply for the levels they already know about.
    expect(valueFor('policies.masking.level', 'quantum')).toBe('quantum');
    expect(valueFor('policies.guardrails.mode', 'chaotic')).toBe('chaotic');
    expect(valueFor('policies.approvals.threshold', 'always')).toBe('always');
  });

  it('still marks a null value as not set, rather than rendering an empty cell', () => {
    const rows = guardrailRows(
      [field({ path: 'policies.masking.level', value: null, default: null })],
      'en',
    );

    expect(rows[0]?.value).toBe('Not set');
  });

  it('translates rather than carrying English into another locale', () => {
    expect(valueFor('policies.guardrails.mode', 'observing', 'pt-BR')).not.toBe(
      valueFor('policies.guardrails.mode', 'observing', 'en'),
    );
    expect(
      valueFor('policies.approvals.threshold', 'write_reversible', 'pt-BR'),
    ).not.toBe(valueFor('policies.approvals.threshold', 'write_reversible', 'en'));
    expect(valueFor('policies.masking.level', 'strict', 'pt-BR')).not.toBe(
      valueFor('policies.masking.level', 'strict', 'en'),
    );
  });
});
