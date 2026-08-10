import type { EditableField } from './preview';
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
  }));
}
