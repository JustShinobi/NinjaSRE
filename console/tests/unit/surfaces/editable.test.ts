import { describe, expect, it } from 'vitest';

import { editableFields } from '@/surfaces/editable';

/**
 * Reading the deployment's field catalogue, and reading nothing into it.
 *
 * The module's whole claim is that it is "a rename and nothing more — no
 * defaults invented, no types inferred, no field this console decided ought to
 * exist". That claim is worth a test of its own now that a field can carry the
 * description of an *entry*: a list of objects is where a reader is most
 * tempted to fill something in, because a missing entry description is the
 * difference between a control and a paragraph saying the field is edited
 * elsewhere.
 */

describe('the field catalogue as the editor reads it', () => {
  it('carries the entry description a list of objects arrives with', () => {
    const [rules] = editableFields({
      fields: [
        {
          path: 'transit.rules',
          label: 'Routing rules',
          type: 'array',
          item_fields: [
            { path: 'team', label: 'Team', type: 'string' },
            {
              path: 'action',
              label: 'Action',
              type: 'string',
              allowed_values: ['investigate', 'discard'],
              default: 'investigate',
            },
          ],
        },
      ],
    });

    expect(rules?.itemFields.map((each) => each.path)).toEqual(['team', 'action']);
    expect(rules?.itemFields[1]?.allowedValues).toEqual(['investigate', 'discard']);
    expect(rules?.itemFields[1]?.default).toBe('investigate');
  });

  it('carries an entry field’s own bounds, and nothing where there are none', () => {
    const [subagents] = editableFields({
      fields: [
        {
          path: 'agents.subagents',
          label: 'Specialists',
          type: 'array',
          item_fields: [
            { path: 'name', label: 'Name', type: 'string' },
            {
              path: 'max_iterations',
              label: 'Iterations',
              type: 'integer',
              minimum: 1,
              maximum: 20,
            },
          ],
        },
      ],
    });

    expect(subagents?.itemFields[0]?.minimum).toBeNull();
    expect(subagents?.itemFields[1]?.minimum).toBe(1);
    expect(subagents?.itemFields[1]?.maximum).toBe(20);
  });

  it('leaves a plain field with no entry description rather than an invented one', () => {
    const [budget] = editableFields({
      fields: [{ path: 'agents.tool_budget', label: 'Tool budget', type: 'integer' }],
    });

    expect(budget?.itemFields).toEqual([]);
  });

  it('reports a closed set the deployment spelled with numbers as the strings it drew', () => {
    /** The control renders text; a set of numbers has to survive the trip as text. */
    const [field] = editableFields({
      fields: [
        {
          path: 'policies.retries',
          label: 'Retries',
          type: 'integer',
          allowed_values: [1, 2, 3],
        },
      ],
    });

    expect(field?.allowedValues).toEqual(['1', '2', '3']);
  });
});
