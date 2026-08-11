'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input, Select, Switch } from '@/components/form';
import { Badge } from '@/components/status';

/**
 * Editing configuration at a node, previewed against the deployment first.
 *
 * There is no merge in this component and there is nowhere in the console one
 * could be: the pending change is posted, and what comes back is rendered. That
 * is the requirement stated exactly — the preview MUST be the server's answer,
 * never a client-side merge — and it is worth restating why. A merge written
 * here would agree with the server for as long as nobody changes inheritance,
 * and the first time somebody does, an operator previews one result and saves
 * another.
 *
 * **Preview before save is structural rather than advised.** The save control
 * does not exist until a preview of the *current* change has come back, and any
 * further edit removes it again. It has to be a client guarantee: no API can
 * know whether a person read the diff, and a save that demanded a preview token
 * would only prove the browser had asked. What can be built is a document with
 * nothing in it to press.
 *
 * **Every control comes from the catalogue.** Type, range and closed set are
 * the deployment's answer to "what is this field", so an integer is a number
 * control and a closed set is a list. A console holding its own table would
 * offer values the write path refuses, which reads as the platform being
 * arbitrary.
 *
 * **Clearing an override is its own operation.** It is not "set it to the
 * parent's value": one keeps following the parent and the other freezes today's
 * answer into this node, and they diverge the moment somebody edits the parent.
 * So a clear travels as a removal beside the patch, and the diff says what the
 * field reverts to and from where.
 */

/** Where the two halves of a write go. Both are couriers in the console's process. */
const PREVIEW_ENDPOINT = '/api/preview';
const SAVE_ENDPOINT = '/api/config';

/** The types this surface offers a control for. Everything else is read-only here. */
const EDITABLE_TYPES: readonly string[] = ['string', 'integer', 'number', 'boolean'];

/**
 * One field inside an entry of an ordered list of objects.
 *
 * Half of `EditableField` is about a *node* — where the value came from,
 * whether this node overrides it, which ancestor locked it. None of that is
 * true one level down: a list replaces entirely, so an entry inherits the
 * list's answer to all of it and has none of its own.
 */
export interface ItemField {
  /** Relative to the entry, because an entry nobody has added yet has no index. */
  readonly path: string;
  readonly label: string;
  readonly type: string;
  readonly description: string;
  readonly allowedValues: readonly string[] | null;
  readonly minimum: number | null;
  readonly maximum: number | null;
  /** What a newly added entry starts this field at. */
  readonly default: unknown;
}

export interface EditableField {
  readonly path: string;
  readonly label: string;
  /** As the deployment's schema declares it: string, integer, number, boolean, array, object. */
  readonly type: string;
  readonly description: string;
  readonly section: string;
  readonly sectionSummary: string;
  readonly value: unknown;
  /** The node supplying the effective value, or empty when nothing sets it. */
  readonly provenance: string;
  /** Whether *this* node overrides it, which is when a clear is an operation at all. */
  readonly setHere: boolean;
  readonly lockedBy: string;
  readonly approvalGated: boolean;
  readonly allowedValues: readonly string[] | null;
  readonly minimum: number | null;
  readonly maximum: number | null;
  /**
   * An address the deployment already found for this field, and why.
   *
   * Offered rather than applied. A derived address is evidence, not a decision:
   * filling it in silently would make the form claim somebody had chosen it,
   * and a wrong guess would then be indistinguishable from a wrong choice.
   */
  readonly suggestedValue: string;
  readonly suggestedBecause: string;
  /**
   * For an array of objects: what one entry is made of.
   *
   * Empty everywhere else, including an array of strings — there is nothing
   * inside a string to draw, and a row of controls for one would be a shape
   * this console invented.
   */
  readonly itemFields: readonly ItemField[];
}

export interface EditorLabels {
  readonly setting: string;
  readonly value: string;
  readonly submit: string;
  readonly save: string;
  readonly saving: string;
  readonly saved: string;
  readonly failed: string;
  readonly unreachable: string;
  readonly before: string;
  readonly after: string;
  readonly locked: string;
  readonly lockedDetail: string;
  readonly gated: string;
  readonly gatedDetail: string;
  readonly provenance: string;
  readonly empty: string;
  readonly previewFirst: string;
  readonly clear: string;
  readonly cleared: string;
  readonly redundant: string;
  readonly reverts: string;
  readonly notEditable: string;
  readonly inherited: string;
  readonly useSuggested: string;
  readonly addEntry: string;
  readonly removeEntry: string;
  readonly moveUp: string;
  readonly moveDown: string;
  /** Prefixes an entry's position, which is what an ordered list *means*. */
  readonly entryPosition: string;
  readonly emptyList: string;
}

export interface ConfigEditorProps {
  readonly nodeId: string;
  /** Every field this node can be edited by, as the deployment describes them. */
  readonly fields: readonly EditableField[];
  readonly labels: EditorLabels;
}

interface Change {
  readonly path: string;
  readonly before: string;
  readonly after: string;
}

interface Inherited {
  readonly path: string;
  readonly value: string;
  readonly from: string;
}

interface Previewed {
  readonly changes: readonly Change[];
  readonly locked: readonly string[];
  readonly gated: readonly string[];
  readonly requiresApproval: boolean;
  readonly redundant: readonly Inherited[];
  readonly reverts: readonly Inherited[];
}

/** What a change is: the values that were keyed, and the overrides being dropped. */
interface Pending {
  readonly edits: Readonly<Record<string, string>>;
  readonly cleared: readonly string[];
}

function stringify(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

/** Read the deployment's answer without holding an opinion about it. */
function previewedFrom(body: unknown): Previewed {
  const changes: unknown = Reflect.get(Object(body), 'changes');
  const locked: unknown = Reflect.get(Object(body), 'locked');
  const gated: unknown = Reflect.get(Object(body), 'approval_gated');
  return {
    changes: (Array.isArray(changes) ? changes : []).map((change) => ({
      path: stringify(Reflect.get(Object(change), 'path')),
      before: stringify(Reflect.get(Object(change), 'before')),
      after: stringify(Reflect.get(Object(change), 'after')),
    })),
    locked: typeof locked === 'object' && locked !== null ? Object.keys(locked) : [],
    gated: Array.isArray(gated) ? gated.map(String) : [],
    requiresApproval: Reflect.get(Object(body), 'requires_approval') === true,
    redundant: inheritedFrom(body, 'redundant'),
    reverts: inheritedFrom(body, 'reverts'),
  };
}

function inheritedFrom(body: unknown, key: string): readonly Inherited[] {
  const found: unknown = Reflect.get(Object(body), key);
  return (Array.isArray(found) ? found : []).map((entry) => ({
    path: stringify(Reflect.get(Object(entry), 'path')),
    value: stringify(Reflect.get(Object(entry), 'value')),
    from: stringify(Reflect.get(Object(entry), 'inherited_from')),
  }));
}

/** Whether this field is an ordered list of objects rather than a plain leaf. */
function isObjectList(field: EditableField): boolean {
  return field.type === 'array' && field.itemFields.length > 0;
}

/** The entries a list field currently holds, from the pending edit or the value. */
function entriesOf(field: EditableField, keyed: string | undefined): readonly Entry[] {
  const source: unknown = keyed === undefined ? field.value : safeParse(keyed);
  if (!Array.isArray(source)) return [];
  const found: unknown[] = source;
  return found.map((each) =>
    typeof each === 'object' && each !== null ? { ...(each as Entry) } : {},
  );
}

function safeParse(keyed: string): unknown {
  try {
    return JSON.parse(keyed);
  } catch {
    return [];
  }
}

/**
 * Return the value a typed control produced, as the deployment's schema wants it.
 *
 * A list of objects rides in the pending map as JSON, because that map is keyed
 * by path and holds strings. It is parsed back here rather than kept as a
 * second kind of pending state: one shape of pending change means one
 * invalidates-the-preview comparison, and two would eventually disagree.
 */
function typed(field: EditableField, keyed: string): unknown {
  if (isObjectList(field)) return safeParse(keyed);
  if (field.type === 'boolean') return keyed === 'true';
  if (field.type === 'integer') return Number.parseInt(keyed, 10);
  if (field.type === 'number') return Number.parseFloat(keyed);
  return keyed;
}

/** One entry of an ordered list, as the editor holds it while it is being edited. */
type Entry = Record<string, unknown>;

/** Return the entry a newly added row starts as, from the catalogue's defaults. */
function blankEntry(items: readonly ItemField[]): Entry {
  const fresh: Entry = {};
  for (const item of items) {
    fresh[item.path] = item.default ?? (item.type === 'boolean' ? false : '');
  }
  return fresh;
}

/** Return one item's current value as a control's string. */
function itemValue(entry: Entry, item: ItemField): string {
  return stringify(entry[item.path]);
}

/** Return the value an item control produced, in the type the schema declares. */
function itemTyped(item: ItemField, keyed: string): unknown {
  if (item.type === 'boolean') return keyed === 'true';
  if (item.type === 'integer') return Number.parseInt(keyed, 10);
  if (item.type === 'number') return Number.parseFloat(keyed);
  return keyed;
}

/** Return `patch` with `value` set at the dotted `path`, nesting as it goes. */
function placed(
  patch: Record<string, unknown>,
  path: string,
  value: unknown,
): Record<string, unknown> {
  const segments = path.split('.');
  let cursor = patch;
  for (const segment of segments.slice(0, -1)) {
    const existing: unknown = cursor[segment];
    const next: Record<string, unknown> =
      typeof existing === 'object' && existing !== null
        ? (existing as Record<string, unknown>)
        : {};
    cursor[segment] = next;
    cursor = next;
  }
  cursor[segments[segments.length - 1] ?? path] = value;
  return patch;
}

/**
 * Return the request body a change makes, built from a sorted path list.
 *
 * Sorted so the body is a stable function of the change rather than of the
 * order somebody happened to type in — which is what lets it double as the
 * identity of the thing that was previewed.
 */
function bodyOf(
  nodeId: string,
  fields: readonly EditableField[],
  pending: Pending,
): Record<string, unknown> {
  const byPath = new Map(fields.map((field) => [field.path, field]));
  const patch: Record<string, unknown> = {};
  for (const path of Object.keys(pending.edits).sort()) {
    const field = byPath.get(path);
    const keyed = pending.edits[path];
    if (field === undefined || keyed === undefined || keyed === '') continue;
    placed(patch, path, typed(field, keyed));
  }
  return { nodeId, patch, remove: [...pending.cleared].sort() };
}

/** Whether anything is pending at all. An empty change is not previewable. */
function isEmpty(body: Record<string, unknown>): boolean {
  const patch = body.patch as Record<string, unknown>;
  const remove = body.remove as string[];
  return Object.keys(patch).length === 0 && remove.length === 0;
}

/** Change one or more settings, see what the deployment says, then save that. */
export function ConfigEditor({ nodeId, fields, labels }: ConfigEditorProps): ReactNode {
  const [pending, setPending] = useState<Pending>({ edits: {}, cleared: [] });
  const [answer, setAnswer] = useState<Previewed | null>(null);
  // The change the answer above was produced for. Compared against the current
  // one on every render, so an edit invalidates the preview without anything
  // having to remember to clear it.
  const [previewedBody, setPreviewedBody] = useState('');
  const [asking, setAsking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState('');

  const body = bodyOf(nodeId, fields, pending);
  const serialised = JSON.stringify(body);
  const empty = isEmpty(body);
  const current = answer !== null && serialised === previewedBody;

  function edit(path: string, keyed: string): void {
    setSaved(false);
    setFailure('');
    setPending((was) => ({ ...was, edits: { ...was.edits, [path]: keyed } }));
  }

  function toggleClear(path: string): void {
    setSaved(false);
    setFailure('');
    setPending((was) => ({
      ...was,
      cleared: was.cleared.includes(path)
        ? was.cleared.filter((each) => each !== path)
        : [...was.cleared, path],
    }));
  }

  function ask(): void {
    setAsking(true);
    setFailure('');
    void fetch(PREVIEW_ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: serialised,
    })
      .then(async (response) => {
        const answered: unknown = await response.json();
        setAnswer(previewedFrom(answered));
        setPreviewedBody(serialised);
      })
      .catch(() => {
        setFailure(labels.unreachable);
      })
      .finally(() => {
        setAsking(false);
      });
  }

  async function save(): Promise<void> {
    setSaving(true);
    setFailure('');
    let response: Response;
    try {
      response = await fetch(SAVE_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: previewedBody,
      });
    } catch {
      // The deployment, not this process. Saying "refused" would send somebody
      // to look at the wrong machine and find nothing wrong with it.
      setSaving(false);
      setFailure(labels.unreachable);
      return;
    }
    const written: unknown = await response.json().catch(() => ({}));
    setSaving(false);
    if (!response.ok) {
      const reason: unknown = Reflect.get(Object(written), 'reason');
      setFailure(typeof reason === 'string' && reason !== '' ? reason : labels.failed);
      return;
    }
    setSaved(true);
    setAnswer(null);
    setPreviewedBody('');
    setPending({ edits: {}, cleared: [] });
  }

  return (
    <div data-testid="config-editor" className="flex flex-col gap-3">
      <div className="flex flex-col gap-3">
        {fields.map((field) => (
          <FieldRow
            key={field.path}
            field={field}
            keyed={pending.edits[field.path]}
            cleared={pending.cleared.includes(field.path)}
            labels={labels}
            onEdit={edit}
            onToggleClear={toggleClear}
          />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          data-testid="ask-preview"
          state={asking ? 'loading' : empty ? 'disabled' : 'default'}
          onClick={ask}
        >
          {labels.submit}
        </Button>

        {/* Absent rather than disabled. A save that exists and refuses is a save
            somebody presses twice and then reports as broken. */}
        {current ? (
          <Button
            data-testid="save-config"
            state={saving ? 'loading' : 'default'}
            onClick={() => {
              void save();
            }}
          >
            {saving ? labels.saving : labels.save}
          </Button>
        ) : empty ? null : (
          <span data-testid="preview-first" className="text-meta text-muted">
            {labels.previewFirst}
          </span>
        )}

        {saved ? (
          <span data-testid="save-result" className="text-meta text-success">
            {labels.saved}
          </span>
        ) : null}
        {failure === '' ? null : (
          <span data-testid="save-failure" className="text-meta text-danger">
            {failure}
          </span>
        )}
      </div>

      {answer === null || !current ? null : <Diff answer={answer} labels={labels} />}
    </div>
  );
}

interface FieldRowProps {
  readonly field: EditableField;
  readonly keyed: string | undefined;
  readonly cleared: boolean;
  readonly labels: EditorLabels;
  readonly onEdit: (path: string, value: string) => void;
  readonly onToggleClear: (path: string) => void;
}

/** One field: its control, where its value came from, and what constrains it. */
function FieldRow({
  field,
  keyed,
  cleared,
  labels,
  onEdit,
  onToggleClear,
}: FieldRowProps): ReactNode {
  const current = keyed ?? stringify(field.value);
  return (
    <div
      data-testid="config-field"
      data-path={field.path}
      className="flex flex-col gap-1"
    >
      {field.lockedBy !== '' ? (
        <span data-testid="field-locked" className="flex items-center gap-2">
          <Badge status="locked" />
          <span className="text-meta text-muted">
            {field.label} — {labels.lockedDetail} {field.lockedBy}
          </span>
        </span>
      ) : isObjectList(field) ? (
        <ObjectList
          field={field}
          entries={entriesOf(field, keyed)}
          disabled={cleared}
          labels={labels}
          onEdit={onEdit}
        />
      ) : EDITABLE_TYPES.includes(field.type) ? (
        <Control field={field} value={current} disabled={cleared} onEdit={onEdit} />
      ) : (
        <span data-testid="field-not-editable" className="flex items-center gap-2">
          <span className="text-meta font-mono">{field.path}</span>
          <span className="text-meta text-muted">{labels.notEditable}</span>
        </span>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span
          data-testid="field-provenance"
          data-path={field.path}
          className="text-meta text-muted"
        >
          {labels.provenance}{' '}
          {field.provenance === '' ? labels.inherited : field.provenance}
        </span>
        {field.approvalGated ? (
          <span data-testid="field-gated" className="text-meta text-muted">
            {labels.gatedDetail}
          </span>
        ) : null}
        {/* Only where there is an override to remove. Offering it on an
            inherited field would be offering an operation with no subject. */}
        {field.setHere && field.lockedBy === '' ? (
          <button
            type="button"
            data-testid="clear-override"
            data-path={field.path}
            aria-pressed={cleared}
            className="text-meta text-strong underline"
            onClick={() => {
              onToggleClear(field.path);
            }}
          >
            {cleared ? labels.cleared : labels.clear}
          </button>
        ) : null}
        {/* Only where the field is empty. An address somebody typed is a
            decision, and offering to replace it with a derived one puts a guess
            above a choice. */}
        {field.suggestedValue !== '' && current === '' && field.lockedBy === '' ? (
          <>
            <button
              type="button"
              data-testid="use-suggested"
              data-path={field.path}
              className="text-meta text-strong underline"
              onClick={() => {
                onEdit(field.path, field.suggestedValue);
              }}
            >
              {labels.useSuggested} {field.suggestedValue}
            </button>
            <span data-testid="suggested-because" className="text-meta text-muted">
              {field.suggestedBecause}
            </span>
          </>
        ) : null}
      </div>
    </div>
  );
}

interface ControlProps {
  readonly field: EditableField;
  readonly value: string;
  readonly disabled: boolean;
  readonly onEdit: (path: string, value: string) => void;
}

/** The control the catalogue asks for, and never one this console chose. */
function Control({ field, value, disabled, onEdit }: ControlProps): ReactNode {
  if (field.allowedValues !== null && field.allowedValues.length > 0) {
    return (
      <Select
        label={field.label}
        name={field.path}
        description={field.description}
        disabled={disabled}
        value={value}
        options={field.allowedValues.map((each) => ({ value: each, label: each }))}
        onValueChange={(next) => {
          onEdit(field.path, next);
        }}
      />
    );
  }

  if (field.type === 'boolean') {
    return (
      <Switch
        label={field.label}
        name={field.path}
        description={field.description}
        disabled={disabled}
        checked={value === 'true'}
        onCheckedChange={(next) => {
          onEdit(field.path, next ? 'true' : 'false');
        }}
      />
    );
  }

  const numeric = field.type === 'integer' || field.type === 'number';
  return (
    <Input
      label={field.label}
      name={field.path}
      description={field.description}
      disabled={disabled}
      type={numeric ? 'number' : 'text'}
      min={field.minimum ?? undefined}
      max={field.maximum ?? undefined}
      value={value}
      onValueChange={(next) => {
        onEdit(field.path, next);
      }}
    />
  );
}

interface ObjectListProps {
  readonly field: EditableField;
  readonly entries: readonly Entry[];
  readonly disabled: boolean;
  readonly labels: EditorLabels;
  readonly onEdit: (path: string, value: string) => void;
}

/**
 * An ordered list of objects: rows that can be edited, added, removed and moved.
 *
 * The whole list is posted on every change, because that is what the merge
 * does with a list — it replaces it entirely. A control that sent only the
 * touched entry would silently delete every other one, which is the failure
 * this shape of editor exists to make impossible rather than merely unlikely.
 *
 * **Position is drawn, because for these fields it is the value.** Routing
 * rules are first-match-wins with an explicit last word; specialists are
 * dispatched down the list. A row that could be moved but did not say where it
 * sat would be an editor for a set, offered for something that is not one.
 *
 * Moving is two buttons rather than a drag. A drag is unusable from a keyboard
 * without building a second interaction anyway, and the second interaction is
 * this one.
 */
function ObjectList({
  field,
  entries,
  disabled,
  labels,
  onEdit,
}: ObjectListProps): ReactNode {
  function write(next: readonly Entry[]): void {
    onEdit(field.path, JSON.stringify(next));
  }

  function change(index: number, item: ItemField, keyed: string): void {
    write(
      entries.map((entry, at) =>
        at === index ? { ...entry, [item.path]: itemTyped(item, keyed) } : entry,
      ),
    );
  }

  function move(index: number, by: number): void {
    const target = index + by;
    if (target < 0 || target >= entries.length) return;
    const next = [...entries];
    const [lifted] = next.splice(index, 1);
    if (lifted !== undefined) next.splice(target, 0, lifted);
    write(next);
  }

  return (
    <fieldset
      data-testid="object-list"
      data-path={field.path}
      className="flex flex-col gap-3 border-l border-subtle pl-3"
    >
      <legend className="text-meta text-strong">{field.label}</legend>
      {field.description === '' ? null : (
        <p className="text-meta text-muted">{field.description}</p>
      )}

      {entries.length === 0 ? (
        <p className="text-meta text-muted">{labels.emptyList}</p>
      ) : (
        entries.map((entry, index) => (
          <div
            // The index is the identity here, and deliberately: an entry has no
            // stable key of its own until somebody names one, and keying on a
            // field the operator is in the middle of typing would remount the
            // control under their cursor.
            key={index}
            data-testid="list-entry"
            data-index={String(index)}
            className="flex flex-col gap-2"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span
                data-testid="entry-position"
                className="text-micro uppercase text-muted"
              >
                {labels.entryPosition} {index + 1}
              </span>
              <button
                type="button"
                data-testid="move-entry-up"
                disabled={disabled || index === 0}
                className="text-meta text-strong underline"
                onClick={() => {
                  move(index, -1);
                }}
              >
                {labels.moveUp}
              </button>
              <button
                type="button"
                data-testid="move-entry-down"
                disabled={disabled || index === entries.length - 1}
                className="text-meta text-strong underline"
                onClick={() => {
                  move(index, 1);
                }}
              >
                {labels.moveDown}
              </button>
              <button
                type="button"
                data-testid="remove-entry"
                disabled={disabled}
                className="text-meta text-danger underline"
                onClick={() => {
                  write(entries.filter((_, at) => at !== index));
                }}
              >
                {labels.removeEntry}
              </button>
            </div>

            <div className="flex flex-col gap-2">
              {field.itemFields.map((item) => (
                <div key={item.path} data-item-path={item.path}>
                  <ItemControl
                    item={item}
                    name={`${field.path}.${String(index)}.${item.path}`}
                    value={itemValue(entry, item)}
                    disabled={disabled}
                    onEdit={(keyed) => {
                      change(index, item, keyed);
                    }}
                  />
                </div>
              ))}
            </div>
          </div>
        ))
      )}

      <div>
        <button
          type="button"
          data-testid="add-entry"
          disabled={disabled}
          className="text-meta text-strong underline"
          onClick={() => {
            write([...entries, blankEntry(field.itemFields)]);
          }}
        >
          {labels.addEntry}
        </button>
      </div>
    </fieldset>
  );
}

interface ItemControlProps {
  readonly item: ItemField;
  readonly name: string;
  readonly value: string;
  readonly disabled: boolean;
  readonly onEdit: (value: string) => void;
}

/** One control inside a list entry, from the item schema and nothing else. */
function ItemControl({
  item,
  name,
  value,
  disabled,
  onEdit,
}: ItemControlProps): ReactNode {
  if (item.allowedValues !== null && item.allowedValues.length > 0) {
    return (
      <Select
        label={item.label}
        name={name}
        description={item.description}
        disabled={disabled}
        value={value}
        options={item.allowedValues.map((each) => ({ value: each, label: each }))}
        onValueChange={onEdit}
      />
    );
  }

  if (item.type === 'boolean') {
    return (
      <Switch
        label={item.label}
        name={name}
        description={item.description}
        disabled={disabled}
        checked={value === 'true'}
        onCheckedChange={(next) => {
          onEdit(next ? 'true' : 'false');
        }}
      />
    );
  }

  const numeric = item.type === 'integer' || item.type === 'number';
  return (
    <Input
      label={item.label}
      name={name}
      description={item.description}
      disabled={disabled}
      type={numeric ? 'number' : 'text'}
      min={item.minimum ?? undefined}
      max={item.maximum ?? undefined}
      value={value}
      onValueChange={onEdit}
    />
  );
}

interface DiffProps {
  readonly answer: Previewed;
  readonly labels: EditorLabels;
}

/** What the deployment says would happen, and the two things it says about inheritance. */
function Diff({ answer, labels }: DiffProps): ReactNode {
  const redundant = new Map(answer.redundant.map((each) => [each.path, each]));
  const reverts = new Map(answer.reverts.map((each) => [each.path, each]));

  return (
    <div className="flex flex-col gap-2">
      {answer.changes.length === 0 ? (
        <p className="text-muted text-small">{labels.empty}</p>
      ) : (
        <table className="w-full text-meta" data-testid="preview-changes">
          <thead>
            <tr>
              {[labels.setting, labels.before, labels.after].map((header) => (
                <th
                  key={header}
                  scope="col"
                  className="text-left text-micro uppercase text-muted pb-1"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {answer.changes.map((change) => (
              <tr
                key={change.path}
                data-testid="preview-change"
                data-path={change.path}
              >
                <td className="py-1 font-mono break-all">
                  {change.path}
                  {/* Inside the diff rather than beside it: the row is where
                      somebody is looking when they decide the change is worth
                      making. */}
                  {redundant.has(change.path) ? (
                    <span
                      data-testid="preview-redundant"
                      data-path={change.path}
                      className="block text-micro text-warning"
                    >
                      {labels.redundant} — {redundant.get(change.path)?.from}
                    </span>
                  ) : null}
                  {reverts.has(change.path) ? (
                    <span
                      data-testid="preview-revert"
                      data-path={change.path}
                      className="block text-micro text-muted"
                    >
                      {labels.reverts} {reverts.get(change.path)?.value} —{' '}
                      {reverts.get(change.path)?.from}
                    </span>
                  ) : null}
                </td>
                <td className="py-1 text-danger break-all">{change.before}</td>
                <td className="py-1 text-success break-all">{change.after}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {answer.locked.map((path) => (
          <span key={path} data-testid="locked" className="flex items-center gap-1">
            <Badge status="locked" />
            <span className="text-meta text-muted">
              {path} — {labels.lockedDetail}
            </span>
          </span>
        ))}
        {answer.requiresApproval || answer.gated.length > 0 ? (
          <span data-testid="gated" className="flex items-center gap-1">
            <Badge status="pending" />
            <span className="text-meta text-muted">{labels.gatedDetail}</span>
          </span>
        ) : null}
      </div>
    </div>
  );
}
