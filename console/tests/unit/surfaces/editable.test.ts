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
  it('reads the short help, and never the schema’s own long description', () => {
    // The two arrive side by side and only one of them is addressed to the
    // person filling the form in. Asserted against a `description` that carries
    // exactly what used to reach the screen — a requirement identifier, a
    // source path, unrendered reST — so this fails loudly if the reading ever
    // falls back to it.
    const [field] = editableFields({
      fields: [
        {
          path: 'policies.sso.enabled',
          label: 'Single sign-on',
          type: 'boolean',
          help: 'Turn this on to let people sign in with your identity provider.',
          section: 'policies.sso',
          section_help: 'How people sign in, and who is allowed to.',
          description:
            'Off by default, which is FR-008. See ``platform/config_service/merge.py``.',
          section_summary: 'Article III says an identity provider is optional.',
        },
      ],
    });

    expect(field?.help).toBe(
      'Turn this on to let people sign in with your identity provider.',
    );
    expect(field?.sectionHelp).toBe('How people sign in, and who is allowed to.');
    expect(JSON.stringify(field)).not.toContain('FR-008');
    expect(JSON.stringify(field)).not.toContain('merge.py');
    expect(JSON.stringify(field)).not.toContain('Article III');
  });

  it('reads an entry field’s help too, since a list of objects is its own form', () => {
    const [rules] = editableFields({
      fields: [
        {
          path: 'transit.rules',
          label: 'Routing rules',
          type: 'array',
          item_fields: [
            {
              path: 'team',
              label: 'Team',
              type: 'string',
              help: 'Who this alert is handed to.',
              description: 'The team, per ``transit/routing.py``.',
            },
          ],
        },
      ],
    });

    expect(rules?.itemFields[0]?.help).toBe('Who this alert is handed to.');
    expect(JSON.stringify(rules?.itemFields)).not.toContain('routing.py');
  });

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

  it('carries the schema default, which is what actually applies when nothing overrides it', () => {
    const [budget] = editableFields({
      fields: [
        {
          path: 'agents.tool_budget',
          label: 'Tool budget',
          type: 'integer',
          default: 8,
        },
      ],
    });

    expect(budget?.default).toBe(8);
  });
});
