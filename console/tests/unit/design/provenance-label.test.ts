import { describe, expect, it } from 'vitest';

import { provenanceLabel } from '@/design/provenance-label';

/**
 * The vocabulary that tells "nothing overrides this" from "an override is
 * recorded here", without either sentence borrowing the other's word.
 *
 * The root node in this deployment happens to be named `default`, which is
 * exactly the trap: a provenance string built by naming the node would read
 * "Set at default" for an override at that node, indistinguishable from the
 * sentence this test asserts for the *other* case — no override at all. The
 * two phrases below never share the word "default" for that reason.
 */

describe('what a value’s provenance says, in a vocabulary with no ambiguous word', () => {
  it('never calls an override "the default", even at a node literally named default', () => {
    const provenance = new Map([['agents.tool_budget', 'default']]);

    expect(provenanceLabel('en', 'agents.tool_budget', provenance)).toBe(
      'Set at: default',
    );
  });

  it('says "deployment default" when no node in the chain sets it at all', () => {
    const provenance = new Map<string, string>();

    expect(provenanceLabel('en', 'agents.tool_budget', provenance)).toBe(
      'Deployment default',
    );
  });

  it('names the single node when every leaf beneath a compound setting agrees', () => {
    const provenance = new Map([
      ['policies.masking.level', 'org-northwind'],
      ['policies.masking.enabled', 'org-northwind'],
    ]);

    expect(provenanceLabel('en', 'policies.masking', provenance)).toBe(
      'Set at: org-northwind',
    );
  });

  it('says the sources differ rather than naming just one of them', () => {
    const provenance = new Map([
      ['policies.masking.level', 'org-northwind'],
      ['policies.masking.enabled', 'payments'],
    ]);

    expect(provenanceLabel('en', 'policies.masking', provenance)).toBe(
      'Set across more than one node',
    );
  });

  it('carries the same vocabulary in pt-BR, with the same two-way distinction', () => {
    const set = new Map([['agents.tool_budget', 'default']]);
    const unset = new Map<string, string>();

    expect(provenanceLabel('pt-BR', 'agents.tool_budget', set)).toBe(
      'Definido em: default',
    );
    expect(provenanceLabel('pt-BR', 'agents.tool_budget', unset)).toBe(
      'Padrão do deployment',
    );
  });
});
