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
    default: 'always',
    value: 'always',
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
    expect(byPath.get('policies.masking.level')?.value).toBe('strict');
    expect(byPath.get('policies.guardrails.mode')?.value).toBe('enforcing');
    expect(byPath.get('policies.guardrails.ruleset')?.value).toBe('standard');
    expect(byPath.get('policies.approvals.threshold')?.value).toBe('always');
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
    expect(overridden?.value).toBe('strict');
    expect(overridden?.origin).toBe('org-northwind');
    expect(overridden?.value).not.toBe(overridden?.origin);

    // Never overridden: Set at says so, in words distinct from the value itself.
    expect(inherited?.value).toBe('enforcing');
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
