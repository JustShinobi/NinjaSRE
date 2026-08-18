'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input, Select } from '@/components/form';
import { cx } from '@/design/cx';
import { AlertTriangleIcon } from '@/design/icons';
import { MODEL_PROVIDER_SETTING, MODEL_SETTING } from './plan';

/**
 * Which model this deployment thinks with, chosen and then saved through the
 * deployment's own preview.
 *
 * Two controls rather than one, because a configuration write here inherits
 * like every other: the value may be locked above this node, may be
 * approval-gated, and may resolve to something other than what was typed. The
 * preview is the deployment's answer to exactly the patch that is about to be
 * sent, and it is shown before the save rather than after it. A console that
 * merged locally would agree with the server today and disagree with it after
 * the next change to inheritance.
 *
 * A closed list when the provider declares the models it serves, and a free
 * field with its default when it does not. Offering a list to a provider that
 * has not published one would be inventing model names, which fails at the
 * first request and looks like the deployment's fault.
 */

export interface ModelStepLabels {
  readonly known: string;
  readonly free: string;
  readonly preview: string;
  readonly previewing: string;
  readonly save: string;
  readonly saving: string;
  readonly wouldChange: string;
  readonly nothingWouldChange: string;
  readonly saved: string;
  readonly refused: string;
  readonly unreachable: string;
  readonly needsPreview: string;
  /**
   * Every configuration path this step's own patch may name, mapped to the
   * display name a reader should see instead of it — `changesOf` falls back
   * to the raw path only for one this map does not cover, which never
   * happens for `patchOf`'s own two fields.
   */
  readonly fieldLabels: Readonly<Record<string, string>>;
}

export interface ModelStepProps {
  readonly provider: string;
  /** The models this provider is known to serve. Empty when it declares none. */
  readonly models: readonly string[];
  readonly defaultModel: string;
  /** The node this deployment writes configuration at. */
  readonly nodeId: string;
  readonly labels: ModelStepLabels;
}

export const PREVIEW_ENDPOINT = '/api/preview';
export const CONFIG_ENDPOINT = '/api/config';

interface Outcome {
  readonly role: 'success' | 'danger' | 'info';
  readonly message: string;
}

/**
 * `previewed`'s changes, each named by its display label rather than its raw
 * configuration path — `models.investigator.model` is a schema address, not
 * a sentence a person reads, and `fieldLabels` is where this step's own two
 * fields declare what a reader should see instead of it.
 */
function changesOf(
  previewed: unknown,
  fieldLabels: Readonly<Record<string, string>>,
): readonly string[] {
  const changes: unknown = Reflect.get(Object(previewed), 'changes');
  if (!Array.isArray(changes)) return [];
  return changes.map((change) => {
    const path = String(Reflect.get(Object(change), 'path'));
    const after: unknown = Reflect.get(Object(change), 'after');
    const label = fieldLabels[path] ?? path;
    return `${label} → ${String(after)}`;
  });
}

/** Every reason the preview says the write would be refused. */
function refusalsOf(previewed: unknown): readonly string[] {
  const errors: unknown = Reflect.get(Object(previewed), 'errors');
  if (!Array.isArray(errors)) return [];
  return errors.map((error) => String(Reflect.get(Object(error), 'message')));
}

/**
 * The chosen provider and model as the nested document the deployment
 * validates.
 *
 * Grown from the same dotted settings the checklist reads, so the write and
 * the read cannot name different fields. Sent as flat dotted keys instead,
 * each would be a field the closed schema has never heard of, and the write
 * would be refused.
 */
function patchOf(provider: string, model: string): Record<string, unknown> {
  const document: Record<string, unknown> = {};
  for (const [path, value] of [
    [MODEL_PROVIDER_SETTING, provider],
    [MODEL_SETTING, model],
  ] as const) {
    const segments = path.split('.');
    const leaf = segments.pop() ?? path;
    let cursor = document;
    for (const segment of segments) {
      const held = cursor[segment];
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

/** Choose a model, see what saving it would resolve to, then save it. */
export function ModelStep({
  provider,
  models,
  defaultModel,
  nodeId,
  labels,
}: ModelStepProps): ReactNode {
  const [model, setModel] = useState(defaultModel);
  const [busy, setBusy] = useState<'' | 'preview' | 'save'>('');
  const [previewed, setPreviewed] = useState<readonly string[] | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  const patch = patchOf(provider, model);

  async function send(address: string): Promise<unknown> {
    try {
      const answer = await fetch(address, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ nodeId, patch }),
      });
      const body: unknown = await answer.json().catch(() => ({}));
      if (!answer.ok) {
        // `reason` is the courier's own word; `detail` is the gateway's,
        // forwarded verbatim by the preview. Either is a sentence somebody
        // wrote for a person, and dropping both left "refused:" with
        // nothing after the colon.
        const reason: unknown =
          Reflect.get(Object(body), 'reason') ?? Reflect.get(Object(body), 'detail');
        setOutcome({
          role: 'danger',
          message:
            `${labels.refused} ${typeof reason === 'string' ? reason : ''}`.trim(),
        });
        return null;
      }
      return body;
    } catch {
      setOutcome({ role: 'danger', message: labels.unreachable });
      return null;
    }
  }

  async function preview(): Promise<void> {
    setBusy('preview');
    setOutcome(null);
    const body = await send(PREVIEW_ENDPOINT);
    setBusy('');
    if (body === null) return;
    const refusals = refusalsOf(body);
    if (refusals.length > 0) {
      // The preview answered 200 and predicted a refusal. Showing "would
      // change" beside a save that is going to fail would make the preview
      // decoration, so the refusal is the outcome and the save stays shut.
      setPreviewed(null);
      setOutcome({
        role: 'danger',
        message: `${labels.refused} ${refusals.join('; ')}`.trim(),
      });
      return;
    }
    setPreviewed(changesOf(body, labels.fieldLabels));
  }

  async function save(): Promise<void> {
    setBusy('save');
    setOutcome(null);
    const body = await send(CONFIG_ENDPOINT);
    setBusy('');
    if (body === null) return;
    setOutcome({ role: 'success', message: labels.saved });
  }

  return (
    <div data-testid="model-step" className="flex flex-col gap-3">
      {models.length === 0 ? (
        <Input
          label={labels.free}
          name="model"
          value={model}
          onValueChange={setModel}
        />
      ) : (
        <Select
          label={labels.known}
          name="model"
          value={model}
          options={models.map((known) => ({ value: known, label: known }))}
          onValueChange={setModel}
        />
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          data-testid="preview-model"
          state={busy === 'preview' ? 'loading' : 'default'}
          onClick={() => {
            void preview();
          }}
        >
          {busy === 'preview' ? labels.previewing : labels.preview}
        </Button>
        <Button
          variant="primary"
          data-testid="save-model"
          // The order is the point: the deployment answers what this patch
          // would do, and only then is the same patch sent. A save that could
          // run without a preview would make the preview decoration.
          state={
            busy === 'save' ? 'loading' : previewed === null ? 'disabled' : 'default'
          }
          onClick={() => {
            void save();
          }}
        >
          {busy === 'save' ? labels.saving : labels.save}
        </Button>
        {previewed === null ? (
          <span className="text-meta text-muted">{labels.needsPreview}</span>
        ) : null}
      </div>

      {previewed === null ? null : (
        <div data-testid="model-preview" className="flex flex-col gap-1">
          <p className="text-meta text-muted">
            {previewed.length === 0 ? labels.nothingWouldChange : labels.wouldChange}
          </p>
          <ul className="flex flex-col gap-1 text-small">
            {previewed.map((change) => (
              <li key={change} className="font-mono">
                {change}
              </li>
            ))}
          </ul>
        </div>
      )}

      {outcome === null ? null : (
        // Boxed and iconed rather than a bare coloured line, and `alert`
        // rather than `status` for a refusal: colour was the only thing
        // telling a refusal apart from a save that worked, which is nothing
        // to somebody who cannot see it and easy to miss for somebody who can.
        <p
          role={outcome.role === 'danger' ? 'alert' : 'status'}
          data-testid="model-result"
          className={cx(
            'flex items-center gap-2 rounded-2 edge px-3 py-2 text-meta',
            outcome.role === 'danger'
              ? 'bg-danger-bg text-danger border-danger'
              : 'bg-success-bg text-success border-success',
          )}
        >
          {outcome.role === 'danger' ? (
            <span aria-hidden="true">
              <AlertTriangleIcon />
            </span>
          ) : null}
          {outcome.message}
        </p>
      )}
    </div>
  );
}
