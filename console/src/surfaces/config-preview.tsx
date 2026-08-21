'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input, Select } from '@/components/form';
import { Badge } from '@/components/status';

/**
 * A change, previewed against the deployment before it is saved.
 *
 * There is no merge in this component and there is nowhere in the console one
 * could be: the setting and the value are posted, and what comes back is
 * rendered. That is the requirement stated exactly — the preview MUST be the
 * server's answer, never a client-side merge — and it is worth restating why. A
 * merge written here would agree with the server for as long as nobody changes
 * inheritance, and the first time somebody does, an operator previews one result
 * and saves another.
 *
 * The three field markings are rendered from the server's answer too. A field
 * the server calls approval-gated says the change will be *queued*, in words,
 * beside the control that queues it.
 */

export interface PreviewLabels {
  readonly setting: string;
  readonly value: string;
  readonly submit: string;
  readonly before: string;
  readonly after: string;
  readonly locked: string;
  readonly lockedDetail: string;
  readonly gated: string;
  readonly gatedDetail: string;
  readonly provenance: string;
  readonly empty: string;
}

export interface ConfigPreviewProps {
  readonly nodeId: string;
  /** The settings this node carries, from the effective configuration. */
  readonly settings: readonly { readonly name: string; readonly value: string }[];
  readonly labels: PreviewLabels;
}

interface Change {
  readonly path: string;
  readonly before: string;
  readonly after: string;
}

interface Previewed {
  readonly changes: readonly Change[];
  readonly locked: readonly string[];
  readonly gated: readonly string[];
  readonly requiresApproval: boolean;
}

function stringify(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value ?? '');
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
  };
}

/** Change one setting, and see what the deployment says it would resolve to. */
export function ConfigPreview({
  nodeId,
  settings,
  labels,
}: ConfigPreviewProps): ReactNode {
  const [setting, setSetting] = useState(settings[0]?.name ?? '');
  const [value, setValue] = useState('');
  const [answer, setAnswer] = useState<Previewed | null>(null);
  const [asking, setAsking] = useState(false);

  function ask(): void {
    setAsking(true);
    void fetch('/api/preview', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ nodeId, patch: { [setting]: value } }),
    })
      .then(async (response) => {
        const body: unknown = await response.json();
        setAnswer(previewedFrom(body));
      })
      .finally(() => {
        setAsking(false);
      });
  }

  return (
    <div data-testid="config-preview" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <Select
          label={labels.setting}
          name="setting"
          value={setting}
          options={settings.map((each) => ({ value: each.name, label: each.name }))}
          onValueChange={setSetting}
        />
        <Input
          label={labels.value}
          name="value"
          value={value}
          onValueChange={setValue}
        />
        <Button
          variant="primary"
          data-testid="ask-preview"
          state={asking ? 'loading' : 'default'}
          onClick={ask}
        >
          {labels.submit}
        </Button>
      </div>

      {answer === null ? null : answer.changes.length === 0 ? (
        <p className="text-muted text-small">{labels.empty}</p>
      ) : (
        <table className="w-full text-meta" data-testid="preview-changes">
          <thead>
            <tr>
              <th
                scope="col"
                className="text-left text-micro uppercase text-muted pb-1"
              >
                {labels.setting}
              </th>
              <th
                scope="col"
                className="text-left text-micro uppercase text-muted pb-1"
              >
                {labels.before}
              </th>
              <th
                scope="col"
                className="text-left text-micro uppercase text-muted pb-1"
              >
                {labels.after}
              </th>
            </tr>
          </thead>
          <tbody>
            {answer.changes.map((change) => (
              <tr
                key={change.path}
                data-testid="preview-change"
                data-path={change.path}
              >
                <td className="py-1 font-mono break-all">{change.path}</td>
                <td className="py-1 text-danger break-all">{change.before}</td>
                <td className="py-1 text-success break-all">{change.after}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {answer === null ? null : (
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
      )}
    </div>
  );
}
