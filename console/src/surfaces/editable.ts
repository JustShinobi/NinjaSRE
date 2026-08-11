import type { EditableField, ItemField } from './preview';
import { field, flag, list, text } from './read';

/**
 * The deployment's field catalogue, read into the shape the editor draws from.
 *
 * A separate module from the editor itself for one mechanical reason: the
 * editor is a client component, and a screen resolved on the server cannot call
 * into one. It is a rename and nothing more — no defaults invented, no types
 * inferred, no field this console decided ought to exist. Everything here comes
 * from `GET /v1/config/{node_id}/fields`, which is where it is decided.
 */

/** A bound the deployment declared, or nothing when it declared none. */
function bound(record: unknown, name: string): number | null {
  const found: unknown = field(record, name);
  return typeof found === 'number' && Number.isFinite(found) ? found : null;
}

/** A closed set the deployment declared, or nothing when the field is open. */
function closedSet(record: unknown, name: string): readonly string[] | null {
  const found: unknown = field(record, name);
  if (!Array.isArray(found)) return null;
  return found.map((each) => (typeof each === 'string' ? each : JSON.stringify(each)));
}

/** What the estate already found running, by the integration it belongs to. */
export interface Suggestion {
  readonly address: string;
  readonly because: string;
}

/**
 * The addresses `GET /v1/integrations` says this deployment already found.
 *
 * Only the vendors the estate makes obvious carry one, which is the whole
 * design of that field: a suggestion that had to be guessed is one an operator
 * has to verify, and then typing it would have been cheaper.
 */
export function suggestedAddresses(
  body: unknown,
): Readonly<Record<string, Suggestion>> {
  const found: Record<string, Suggestion> = {};
  for (const entry of list(body, 'integrations')) {
    const suggested: unknown = field(entry, 'suggested');
    const address = text(suggested, 'address');
    if (address !== '') {
      found[text(entry, 'name')] = { address, because: text(suggested, 'because') };
    }
  }
  return found;
}

/**
 * Return `fields` with an address offered on every endpoint that has none.
 *
 * Which suggestion belongs to which endpoint is decided by the *sibling*
 * `integration` field in the same section — the deployment's own statement of
 * which vendor that source is. Matching on the field's name or on a path
 * fragment would attach an address to whatever happened to be spelled
 * similarly, which is exactly the guess this whole mechanism exists to avoid.
 */
export function withSuggestions(
  fields: readonly EditableField[],
  suggestions: Readonly<Record<string, Suggestion>>,
): readonly EditableField[] {
  const namedIntegration = new Map(
    fields
      .filter((each) => each.path.endsWith('.integration'))
      .map((each) => [each.section, typeof each.value === 'string' ? each.value : '']),
  );
  return fields.map((each) => {
    if (!each.path.endsWith('.endpoint')) return each;
    const vendor = namedIntegration.get(each.section) ?? '';
    const suggestion = suggestions[vendor];
    if (suggestion === undefined) return each;
    return {
      ...each,
      suggestedValue: suggestion.address,
      suggestedBecause: suggestion.because,
    };
  });
}

/** Every editable field in a `/v1/config/{node_id}/fields` body, in its own order. */
export function editableFields(body: unknown): readonly EditableField[] {
  return list(body, 'fields').map((entry) => ({
    path: text(entry, 'path'),
    label: text(entry, 'label'),
    type: text(entry, 'type'),
    description: text(entry, 'description'),
    section: text(entry, 'section'),
    sectionSummary: text(entry, 'section_summary'),
    value: field(entry, 'value'),
    provenance: text(entry, 'provenance'),
    setHere: flag(entry, 'set_here'),
    lockedBy: text(entry, 'locked_by'),
    approvalGated: flag(entry, 'approval_gated'),
    allowedValues: closedSet(entry, 'allowed_values'),
    minimum: bound(entry, 'minimum'),
    maximum: bound(entry, 'maximum'),
    // Filled in by `withSuggestions`, from a different endpoint. The catalogue
    // describes the field; what the estate found is a separate question.
    suggestedValue: '',
    suggestedBecause: '',
    itemFields: itemFields(entry),
  }));
}

/**
 * The fields one entry of an ordered list of objects has, as the deployment
 * describes them.
 *
 * Empty for everything else, which is how the editor tells a list it can draw
 * rows for from one it cannot. Read rather than inferred, for the reason this
 * whole module exists: what a routing rule is made of is the schema's answer,
 * and a copy of it here would be right until somebody added a field to a rule.
 */
function itemFields(entry: unknown): readonly ItemField[] {
  return list(entry, 'item_fields').map((item) => ({
    path: text(item, 'path'),
    label: text(item, 'label'),
    type: text(item, 'type'),
    description: text(item, 'description'),
    allowedValues: closedSet(item, 'allowed_values'),
    minimum: bound(item, 'minimum'),
    maximum: bound(item, 'maximum'),
    default: field(item, 'default'),
  }));
}
