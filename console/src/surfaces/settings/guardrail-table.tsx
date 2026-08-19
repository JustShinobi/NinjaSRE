'use client';

import { useState } from 'react';
import type { ReactNode } from 'react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/action';
import type { EffectiveFieldRow } from '@/design/resolution-preview';
import {
  Control,
  EDITABLE_TYPES,
  SAVE_ENDPOINT,
  typed,
  type EditableField,
} from '../preview';

/**
 * The Guardrails tab's own table — read and write in the same row.
 *
 * `EffectiveFieldsTable` (`design/resolution-preview.tsx`) draws the same
 * Setting/Value/Set at shape everywhere else this product resolves a field,
 * and Posture's read-only summary still uses it unchanged. This is the one
 * place a value in that shape is also editable: the Guardrails tab is the
 * page the field-ownership map assigns these six scalars to, and the
 * mockup draws one table here, not a table with a second, separate form below
 * it repeating the same six rows.
 *
 * The guarantee `EffectiveFieldsTable` enforces — a Value or Set at cell is
 * never blank — is reproduced here rather than bypassed: the same throw, on
 * the same condition, against the same `rows`. Whatever a row's *edit* state
 * is, the closed (non-editing) rendering a fresh page load shows is always
 * the resolved text, never a bare control with nothing beside it — a
 * `<select>` or a switch carries no text a scan for an empty cell would find,
 * so the affordance to edit is a button next to the value, not a replacement
 * of it, until an operator explicitly asks to change something.
 *
 * The write itself reuses `ConfigEditor`'s own save route (`/api/config`) and
 * its own per-type `Control` — a `Select` for a closed set, a `Switch` for a
 * boolean, an `Input` otherwise — rather than a second implementation of
 * either. That route is a scoped patch (`{nodeId, patch, remove}`), not the
 * autonomy policy's full-document `PUT`: sending only the one path that
 * changed is what keeps every other guardrail, and everything outside this
 * group entirely, untouched by a save here — there is no sibling list this
 * write could silently clear, because it never carries siblings at all.
 */

export interface GuardrailTableLabels {
  readonly setting: string;
  readonly value: string;
  readonly origin: string;
  readonly edit: string;
  readonly cancel: string;
  readonly save: string;
  readonly saving: string;
  readonly saved: string;
  readonly failed: string;
  readonly unreachable: string;
}

export interface GuardrailTableProps {
  /** One row per guardrail, already resolved to the sentence it reads as. */
  readonly rows: readonly EffectiveFieldRow[];
  /** The same node's raw field catalogue, read once for the control each row needs. */
  readonly catalogue: readonly EditableField[];
  readonly writable: boolean;
  readonly nodeId: string;
  readonly labels: GuardrailTableLabels;
}

function asText(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

/** What a field's control opens on: its own override where one is recorded, its schema default otherwise. */
function initialDraft(field: EditableField): string {
  const defaultKnown = field.provenance === '' && asText(field.default) !== '';
  return defaultKnown ? asText(field.default) : asText(field.value);
}

/** `path`, nested into the object shape a patch to `/api/config` carries. */
function nestedPatch(path: string, value: unknown): Record<string, unknown> {
  const segments = path.split('.');
  const patch: Record<string, unknown> = {};
  let cursor = patch;
  for (const segment of segments.slice(0, -1)) {
    const next: Record<string, unknown> = {};
    cursor[segment] = next;
    cursor = next;
  }
  // Every guardrail path this table draws is a dotted schema path from
  // `GUARDRAIL_FIELDS` — never empty, never a single bare segment — so the
  // fallback below exists for the type checker's `noUncheckedIndexedAccess`,
  // not a state a real call reaches.
  const last = segments[segments.length - 1] ?? path;
  cursor[last] = value;
  return patch;
}

/** Whether the catalogue describes this field with a control this table can offer. */
function isEditable(field: EditableField | undefined): field is EditableField {
  return field !== undefined && EDITABLE_TYPES.includes(field.type);
}

export function GuardrailTable({
  rows,
  catalogue,
  writable,
  nodeId,
  labels,
}: GuardrailTableProps): ReactNode {
  const router = useRouter();
  const byPath = new Map(catalogue.map((field) => [field.path, field]));
  const [editingPath, setEditingPath] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState('');
  const [savedPath, setSavedPath] = useState<string | null>(null);

  // The same guarantee `EffectiveFieldsTable` enforces, reproduced rather
  // than bypassed: a blank Value or Set at cell is a render defect, not a
  // state this table is allowed to reach — whatever the edit state of any
  // row is, `rows` itself must still carry a real value and origin for
  // every one of them.
  for (const row of rows) {
    if (row.value.trim() === '') {
      throw new Error(
        `The guardrails table's row "${row.path}" has no renderable value. ` +
          'A blank Value cell is indistinguishable from a render defect — the row ' +
          'must carry the effective value or an explicit "not set" marker.',
      );
    }
    if (row.origin.trim() === '') {
      throw new Error(
        `The guardrails table's row "${row.path}" has no renderable origin. ` +
          'A blank Set at cell is indistinguishable from a render defect.',
      );
    }
  }

  function startEdit(field: EditableField): void {
    setFailure('');
    setSavedPath(null);
    setDraft(initialDraft(field));
    setEditingPath(field.path);
  }

  function cancelEdit(): void {
    setFailure('');
    setEditingPath(null);
  }

  async function save(field: EditableField): Promise<void> {
    setSaving(true);
    setFailure('');
    let response: Response;
    try {
      response = await fetch(SAVE_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          nodeId,
          patch: nestedPatch(field.path, typed(field, draft)),
          remove: [],
        }),
      });
    } catch {
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
    setSavedPath(field.path);
    setEditingPath(null);
    // Set at is a fact about what the deployment now holds, never a client
    // guess about it — the same discipline the preview panel already
    // applies. Refetching this route is how the row's own origin catches up
    // with what was just written, instead of continuing to show the value
    // this render started with.
    router.refresh();
  }

  return (
    <table data-testid="effective-fields" className="w-full text-small">
      <caption className="sr-only">{labels.setting}</caption>
      <thead>
        <tr>
          {[labels.setting, labels.value, labels.origin].map((header) => (
            <th
              key={header}
              scope="col"
              className="text-left text-micro uppercase text-muted px-3 pb-2 edge border-border border-t-0 border-x-0"
            >
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const field = byPath.get(row.path);
          const editable = writable && isEditable(field);
          const active = editingPath === row.path && field !== undefined;
          return (
            <tr key={row.path} data-testid="effective-field" data-path={row.path}>
              <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                {row.label}
              </td>
              <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                {active ? (
                  <div
                    data-testid="guardrail-field-editor"
                    data-path={field.path}
                    className="flex flex-col gap-2"
                  >
                    <Control
                      field={field}
                      value={draft}
                      disabled={saving}
                      onEdit={(_path, next) => {
                        setDraft(next);
                      }}
                    />
                    <div className="flex flex-wrap items-center gap-3">
                      <Button
                        data-testid="guardrail-save"
                        state={saving ? 'loading' : 'default'}
                        onClick={() => {
                          void save(field);
                        }}
                      >
                        {saving ? labels.saving : labels.save}
                      </Button>
                      <button
                        type="button"
                        data-testid="guardrail-cancel"
                        className="text-meta text-strong underline"
                        onClick={cancelEdit}
                      >
                        {labels.cancel}
                      </button>
                      {failure === '' ? null : (
                        <span
                          data-testid="guardrail-save-failure"
                          className="text-meta text-danger"
                        >
                          {failure}
                        </span>
                      )}
                    </div>
                  </div>
                ) : (
                  <span className="flex flex-wrap items-center gap-3">
                    <span className="font-mono break-all">{row.value}</span>
                    {editable ? (
                      <button
                        type="button"
                        data-testid="guardrail-edit"
                        data-path={row.path}
                        className="text-meta text-strong underline"
                        onClick={() => {
                          startEdit(field);
                        }}
                      >
                        {labels.edit}
                      </button>
                    ) : null}
                    {savedPath === row.path ? (
                      <span
                        data-testid="guardrail-save-result"
                        className="text-meta text-success"
                      >
                        {labels.saved}
                      </span>
                    ) : null}
                  </span>
                )}
              </td>
              <td
                data-testid="effective-field-origin"
                data-path={row.path}
                className="px-3 py-2 edge border-border border-t-0 border-x-0 text-muted"
              >
                {row.origin}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
