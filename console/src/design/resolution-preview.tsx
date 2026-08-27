'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

/**
 * The one patch → preview → apply machinery every page in this group edits
 * through, instead of three copies of it.
 *
 * **Preview before save is structural, not advised.** `useConfigWrite` tells a
 * caller whether its answer is `current` — whether it was computed for exactly
 * the patch and the removals now pending — and a page never shows a save
 * control except when it is. A save that could run without a preview would
 * make the preview decoration: see `first-run/model.tsx`'s own save button,
 * which this hook generalises from one field to any number of them.
 *
 * **Nothing here resolves anything.** Both halves are the deployment's own
 * answer, read back verbatim from `/api/preview` and `/api/config` — the same
 * couriers the raw editor's `ConfigEditor` already uses, because the credential
 * these pages write with lives in an HTTP-only cookie a browser cannot present,
 * and a second courier would be a second opinion about what either returns.
 *
 * **A patch is grown from dotted paths, never sent flat.** `models.investigator
 * .provider` sent as a literal top-level key is a field the closed schema has
 * never heard of and the write is refused; `patchOf` nests it the way the
 * schema itself is nested, exactly as `first-run/model.tsx`'s own `patchOf`
 * already does for the one field the guided setup edits.
 */

/** Where every patch and removal go. Couriers in the console's own process. */
export const PREVIEW_ENDPOINT = '/api/preview';
export const SAVE_ENDPOINT = '/api/config';

/**
 * `entries` — dotted path, value — nested into the document the schema wants.
 *
 * Later entries win at a leaf; two entries sharing a prefix grow the same
 * nested object rather than overwriting each other's siblings, which is what
 * lets one patch carry every role a Models & providers save touches at once.
 */
export function patchOf(
  entries: readonly (readonly [path: string, value: unknown])[],
): Record<string, unknown> {
  const document: Record<string, unknown> = {};
  for (const [path, value] of entries) {
    const segments = path.split('.');
    const leaf = segments.pop() ?? path;
    let cursor = document;
    for (const segment of segments) {
      const held: unknown = cursor[segment];
      if (typeof held === 'object' && held !== null) {
        cursor = held as Record<string, unknown>;
      } else {
        const grown: Record<string, unknown> = {};
        cursor[segment] = grown;
        cursor = grown;
      }
    }
    cursor[leaf] = value;
  }
  return document;
}

function stringify(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

export interface ResolvedChange {
  readonly path: string;
  readonly before: string;
  readonly after: string;
}

/** What one `/api/preview` (or `/api/config`) answer said, read without an opinion. */
export interface Resolved {
  readonly changes: readonly ResolvedChange[];
  /** The whole document this patch would resolve to — every path, not only the changed ones. */
  readonly values: Readonly<Record<string, unknown>>;
  /** Dotted path to the node supplying it, for a value this patch would still be inheriting. */
  readonly provenance: Readonly<Record<string, string>>;
  readonly accepted: boolean;
  readonly errors: readonly string[];
  readonly requiresApproval: boolean;
}

function resolvedFrom(body: unknown): Resolved {
  const changes: unknown = Reflect.get(Object(body), 'changes');
  const errors: unknown = Reflect.get(Object(body), 'errors');
  const values: unknown = Reflect.get(Object(body), 'values');
  const provenance: unknown = Reflect.get(Object(body), 'provenance');
  return {
    changes: (Array.isArray(changes) ? changes : []).map((change) => ({
      path: stringify(Reflect.get(Object(change), 'path')),
      before: stringify(Reflect.get(Object(change), 'before')),
      after: stringify(Reflect.get(Object(change), 'after')),
    })),
    values:
      typeof values === 'object' && values !== null
        ? (values as Record<string, unknown>)
        : {},
    provenance:
      typeof provenance === 'object' && provenance !== null
        ? Object.fromEntries(
            Object.entries(provenance as Record<string, unknown>).map(
              ([path, node]) => [path, stringify(node)],
            ),
          )
        : {},
    accepted: Reflect.get(Object(body), 'accepted') !== false,
    errors: (Array.isArray(errors) ? errors : []).map(
      (error) => stringify(Reflect.get(Object(error), 'message')) || stringify(error),
    ),
    requiresApproval: Reflect.get(Object(body), 'requires_approval') === true,
  };
}

export type WriteStatus = '' | 'previewing' | 'saving';

export interface ConfigWrite {
  readonly status: WriteStatus;
  readonly resolved: Resolved | null;
  /** Whether `resolved` answers exactly the patch and removals pending right now. */
  readonly current: boolean;
  readonly saved: boolean;
  readonly failure: string;
  /** Runs the preview and returns the deployment's answer, or `null` on failure. */
  readonly preview: () => Promise<Resolved | null>;
  /** Runs the save and returns whether it succeeded. */
  readonly save: () => Promise<boolean>;
}

export interface ConfigWriteLabels {
  readonly unreachable: string;
  readonly failed: string;
}

/**
 * Edit configuration at `nodeId` through the closed patch/remove shape every
 * page in this group shares: preview it, then apply exactly what was
 * previewed.
 *
 * A fresh edit — a changed `patch` or `remove` — invalidates `current`
 * automatically, because the comparison is structural (the serialised request
 * body) rather than a flag a caller has to remember to clear.
 */
export function useConfigWrite(
  nodeId: string,
  patch: Readonly<Record<string, unknown>>,
  remove: readonly string[] = [],
  labels: ConfigWriteLabels,
): ConfigWrite {
  const [status, setStatus] = useState<WriteStatus>('');
  const [resolved, setResolved] = useState<Resolved | null>(null);
  const [resolvedFor, setResolvedFor] = useState('');
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState('');

  const serialised = JSON.stringify({ nodeId, patch, remove });
  const current = resolved !== null && serialised === resolvedFor;

  async function ask(endpoint: string): Promise<unknown> {
    setFailure('');
    let response: Response;
    try {
      response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: serialised,
      });
    } catch {
      setFailure(labels.unreachable);
      return null;
    }
    const body: unknown = await response.json().catch(() => ({}));
    if (!response.ok) {
      const reason: unknown = Reflect.get(Object(body), 'reason');
      setFailure(typeof reason === 'string' && reason !== '' ? reason : labels.failed);
      return null;
    }
    return body;
  }

  async function preview(): Promise<Resolved | null> {
    setStatus('previewing');
    setSaved(false);
    const body = await ask(PREVIEW_ENDPOINT);
    setStatus('');
    if (body === null) return null;
    const found = resolvedFrom(body);
    setResolved(found);
    setResolvedFor(serialised);
    return found;
  }

  async function save(): Promise<boolean> {
    setStatus('saving');
    const body = await ask(SAVE_ENDPOINT);
    setStatus('');
    if (body === null) return false;
    setSaved(true);
    setResolved(null);
    setResolvedFor('');
    return true;
  }

  return { status, resolved, current, saved, failure, preview, save };
}

export interface ResolutionPreviewLabels {
  readonly before: string;
  readonly after: string;
  readonly nothingChanges: string;
}

export interface ResolutionPreviewProps {
  readonly changes: readonly ResolvedChange[];
  readonly labels: ResolutionPreviewLabels;
}

/**
 * What saving the pending patch would resolve to, read from the deployment's
 * own preview and never recomputed here.
 */
export function ResolutionPreview({
  changes,
  labels,
}: ResolutionPreviewProps): ReactNode {
  if (changes.length === 0) {
    return (
      <p data-testid="resolution-preview-empty" className="text-meta text-muted">
        {labels.nothingChanges}
      </p>
    );
  }
  return (
    <table data-testid="resolution-preview" className="w-full text-meta">
      <caption className="sr-only">{labels.after}</caption>
      <tbody>
        {changes.map((change) => (
          <tr key={change.path} data-testid="resolution-change" data-path={change.path}>
            <td className="py-1 font-mono break-all">{change.path}</td>
            <td className="py-1 text-danger break-all">{change.before}</td>
            <td className="py-1 text-success break-all">{change.after}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** One field's effective value, with where it came from — read, never edited. */
export interface EffectiveFieldRow {
  readonly path: string;
  readonly label: string;
  readonly value: string;
  readonly origin: string;
}

export interface EffectiveFieldsLabels {
  readonly setting: string;
  readonly value: string;
  readonly origin: string;
}

export interface EffectiveFieldsTableProps {
  readonly rows: readonly EffectiveFieldRow[];
  readonly labels: EffectiveFieldsLabels;
}

/**
 * The effective value and origin of every field a page covers, for a viewer
 * who may only read configuration — origin display holds regardless of
 * `config.write`, shown here whether or not the editor beneath it is.
 *
 * **A row with nothing renderable in its Value or its origin is refused,
 * not drawn blank.** A blank cell in a table like this one is indistinguishable
 * from a rendering defect — the whole reason this component exists is that a
 * reader cannot tell "nothing here" from "something failed to draw" by
 * looking at an empty cell, so this makes the absence a defect in whoever
 * built the row rather than a gap the screen ships with. A field that
 * genuinely has no value still owes an explicit marker (an "unset" phrase),
 * which is a non-empty string — the empty string itself is never legitimate.
 */
export function EffectiveFieldsTable({
  rows,
  labels,
}: EffectiveFieldsTableProps): ReactNode {
  for (const row of rows) {
    if (row.value.trim() === '') {
      throw new Error(
        `The configuration table's row "${row.path}" has no renderable value. ` +
          'A blank Value cell is indistinguishable from a render defect — the row ' +
          'must carry the effective value or an explicit "not set" marker.',
      );
    }
    if (row.origin.trim() === '') {
      throw new Error(
        `The configuration table's row "${row.path}" has no renderable origin. ` +
          'A blank Set at cell is indistinguishable from a render defect.',
      );
    }
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
              className="text-left text-micro text-muted px-3 pb-2 edge border-border border-t-0 border-x-0"
            >
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.path} data-testid="effective-field" data-path={row.path}>
            <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
              {row.label}
            </td>
            <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-all">
              {row.value}
            </td>
            <td
              data-testid="effective-field-origin"
              data-path={row.path}
              className="px-3 py-2 edge border-border border-t-0 border-x-0 text-muted"
            >
              {row.origin}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
