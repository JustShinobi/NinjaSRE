import { describe, expect, it } from 'vitest';

import {
  effectiveRows,
  formatHours,
  formatSeconds,
  type EffectiveFieldSpec,
} from '@/surfaces/effective-fields';
import type { EditableField } from '@/surfaces/preview';

/**
 * A configuration table's row, derived from the deployment's own field
 * catalogue rather than from a value read one way and an origin read
 * another — the split that let a field with no override in the effective-
 * configuration document draw an empty Value cell even though its schema
 * default was known all along.
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

describe('effectiveRows', () => {
  it('uses the schema default when nothing overrides the field', () => {
    const rows = effectiveRows(
      [{ path: 'policies.guardrails.ruleset', label: 'Ruleset' }],
      [
        field({
          path: 'policies.guardrails.ruleset',
          type: 'string',
          default: 'standard',
          value: 'standard',
          provenance: '',
        }),
      ],
      'en',
    );

    expect(rows).toHaveLength(1);
    expect(rows[0]?.value).toBe('standard');
    expect(rows[0]?.origin).toBe('Deployment default');
  });

  it('uses the override and names the node when the field carries provenance', () => {
    const rows = effectiveRows(
      [{ path: 'policies.guardrails.ruleset', label: 'Ruleset' }],
      [
        field({
          path: 'policies.guardrails.ruleset',
          type: 'string',
          default: 'standard',
          value: 'strict',
          provenance: 'org-northwind',
          setHere: true,
        }),
      ],
      'en',
    );

    expect(rows[0]?.value).toBe('strict');
    // The bare node — the column is already headed "Set at", so the cell
    // does not repeat the label.
    expect(rows[0]?.origin).toBe('org-northwind');
  });

  it('formats a boolean as a state, never the payload literal', () => {
    const on = effectiveRows(
      [{ path: 'policies.masking.enabled', label: 'Masking' }],
      [
        field({
          path: 'policies.masking.enabled',
          type: 'boolean',
          default: true,
          value: true,
        }),
      ],
      'en',
    );
    const off = effectiveRows(
      [
        {
          path: 'surfaces.notification_policy.quiet_hours_enabled',
          label: 'Quiet hours',
        },
      ],
      [
        field({
          path: 'surfaces.notification_policy.quiet_hours_enabled',
          type: 'boolean',
          default: false,
          value: false,
        }),
      ],
      'en',
    );

    expect(on[0]?.value).toBe('On');
    expect(on[0]?.value).not.toBe('true');
    expect(off[0]?.value).toBe('Off');
    expect(off[0]?.value).not.toBe('false');
  });

  it('formats a number as a number', () => {
    const rows = effectiveRows(
      [
        {
          path: 'surfaces.notification_policy.notifications_per_hour',
          label: 'Per hour',
        },
      ],
      [
        field({
          path: 'surfaces.notification_policy.notifications_per_hour',
          type: 'integer',
          default: 20,
          value: 20,
        }),
      ],
      'en',
    );

    expect(rows[0]?.value).toBe('20');
  });

  it('formats a duration in hours through the field’s own formatter, never the bare number', () => {
    const rows = effectiveRows(
      [
        {
          path: 'policies.approvals.expiry_hours',
          label: 'Approval expiry',
          format: formatHours,
        },
      ],
      [
        field({
          path: 'policies.approvals.expiry_hours',
          type: 'integer',
          default: 2,
          value: 2,
        }),
      ],
      'en',
    );

    expect(rows[0]?.value).toBe('2 hours');
  });

  it('formats one hour in the singular', () => {
    const rows = effectiveRows(
      [
        {
          path: 'policies.approvals.expiry_hours',
          label: 'Approval expiry',
          format: formatHours,
        },
      ],
      [
        field({
          path: 'policies.approvals.expiry_hours',
          type: 'integer',
          default: 1,
          value: 1,
        }),
      ],
      'en',
    );

    expect(rows[0]?.value).toBe('1 hour');
  });

  it('formats a duration in seconds through the field’s own formatter', () => {
    const rows = effectiveRows(
      [
        {
          path: 'surfaces.notification_policy.cooldown_seconds',
          label: 'Cooldown',
          format: formatSeconds,
        },
      ],
      [
        field({
          path: 'surfaces.notification_policy.cooldown_seconds',
          type: 'integer',
          default: 300,
          value: 300,
        }),
      ],
      'en',
    );

    expect(rows[0]?.value).toBe('300 seconds');
  });

  it('marks a field the catalogue does not declare as not set, rather than throwing or drawing a blank', () => {
    const rows = effectiveRows(
      [{ path: 'policies.masking.enabled', label: 'Masking' }],
      [],
      'en',
    );

    expect(rows[0]?.value).toBe('Not set');
  });

  it('marks a field with no value and no default as not set, rather than an empty cell', () => {
    const rows = effectiveRows(
      [{ path: 'policies.guardrails.ruleset', label: 'Ruleset' }],
      [
        field({
          path: 'policies.guardrails.ruleset',
          type: 'string',
          default: null,
          value: null,
        }),
      ],
      'en',
    );

    expect(rows[0]?.value).toBe('Not set');
  });

  it('formats a value that is a bare boolean under a schema type other than "boolean"', () => {
    // A field can be declared under a type the schema does not call
    // "boolean" (a migration in flight, a schema this deployment has not
    // upgraded to) while the value the deployment actually stored is a
    // JS boolean. The cell still owes a literal rather than an empty
    // string — this is the defensive arm below the string/number checks,
    // not the type === 'boolean' path above them, which a schema-declared
    // boolean field always takes instead.
    const truthy = effectiveRows(
      [{ path: 'policies.guardrails.ruleset', label: 'Ruleset' }],
      [
        field({
          path: 'policies.guardrails.ruleset',
          type: 'string',
          default: null,
          value: true,
          provenance: 'org-northwind',
        }),
      ],
      'en',
    );
    const falsy = effectiveRows(
      [{ path: 'policies.guardrails.ruleset', label: 'Ruleset' }],
      [
        field({
          path: 'policies.guardrails.ruleset',
          type: 'string',
          default: null,
          value: false,
          provenance: 'org-northwind',
        }),
      ],
      'en',
    );

    expect(truthy[0]?.value).toBe('true');
    expect(falsy[0]?.value).toBe('false');
  });

  it('formats an object value it has no more specific rule for as its own JSON', () => {
    const rows = effectiveRows(
      [{ path: 'policies.guardrails.allowlist', label: 'Allowlist' }],
      [
        field({
          path: 'policies.guardrails.allowlist',
          type: 'array',
          default: null,
          value: ['prometheus', 'loki'],
          provenance: 'org-northwind',
        }),
      ],
      'en',
    );

    expect(rows[0]?.value).toBe(JSON.stringify(['prometheus', 'loki']));
  });

  it('never returns an empty string for value or origin, whatever the input', () => {
    const specs: readonly EffectiveFieldSpec[] = [
      { path: 'a.b', label: 'A' },
      { path: 'c.d', label: 'C' },
    ];
    const rows = effectiveRows(
      specs,
      [field({ path: 'a.b', type: 'string', default: '', value: '' })],
      'en',
    );

    for (const row of rows) {
      expect(row.value.trim()).not.toBe('');
      expect(row.origin.trim()).not.toBe('');
    }
  });
});

describe('formatHours', () => {
  it('coerces a numeric string, the shape a field carried as text arrives in', () => {
    expect(formatHours('2', 'en')).toBe('2 hours');
  });

  it('says nothing rather than a broken sentence when the value is not a number at all', () => {
    expect(formatHours('not-a-number', 'en')).toBe('');
    expect(formatHours(undefined, 'en')).toBe('');
  });
});

describe('formatSeconds', () => {
  it('coerces a numeric string, the shape a field carried as text arrives in', () => {
    expect(formatSeconds('45', 'en')).toBe('45 seconds');
  });

  it('says nothing rather than a broken sentence when the value is not a number at all', () => {
    expect(formatSeconds('not-a-number', 'en')).toBe('');
    expect(formatSeconds(undefined, 'en')).toBe('');
  });

  it('formats one second in the singular', () => {
    expect(formatSeconds(1, 'en')).toBe('1 second');
  });
});
