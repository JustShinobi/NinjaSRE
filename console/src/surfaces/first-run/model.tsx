'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input, Select } from '@/components/form';
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

function changesOf(previewed: unknown): readonly string[] {
  const changes: unknown = Reflect.get(Object(previewed), 'changes');
  if (!Array.isArray(changes)) return [];
  return changes.map((change) => {
    const path: unknown = Reflect.get(Object(change), 'path');
    const after: unknown = Reflect.get(Object(change), 'after');
    return `${String(path)} → ${String(after)}`;
  });
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

  const patch = {
    [MODEL_PROVIDER_SETTING]: provider,
    [MODEL_SETTING]: model,
  };

  async function send(address: string): Promise<unknown> {
    try {
      const answer = await fetch(address, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ nodeId, patch }),
      });
      const body: unknown = await answer.json().catch(() => ({}));
      if (!answer.ok) {
        const reason: unknown = Reflect.get(Object(body), 'reason');
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
    setPreviewed(changesOf(body));
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
        <p
          role="status"
          data-testid="model-result"
          className={
            outcome.role === 'danger'
              ? 'text-meta text-danger'
              : 'text-meta text-success'
          }
        >
          {outcome.message}
        </p>
      )}
    </div>
  );
}
