'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Badge } from '@/components/status';
import { may, type Viewer } from '@/session/viewer';

/**
 * Turning a detector on or off, and the dry run the enable flow always offers
 * first.
 *
 * **Nothing is enabled blind.** Enabling a detector is deciding what starts
 * paging somebody, so the control never goes straight from "off" to "on": it
 * first asks the deployment what the detector would have concluded against
 * the signals already stored, and only once that answer is on the screen does
 * a control to actually enable it exist. That is the same ordering
 * `AutonomyEditor` uses for a policy change, for the same reason — a
 * confirmation with no evidence in front of it is not a confirmation.
 *
 * **Disabling needs no preview.** Turning a detector off narrows what can
 * happen, never widens it, so it is one control and one write.
 *
 * Nothing here decides whether a detector would fire. `would_fire` and every
 * observation beneath it are the deployment's own answer, rendered.
 */

/** Where every write goes. The console's own process, forwarding once. */
export const DETECTOR_CONTROL_ENDPOINT = '/api/detectors';

/** Who may change what a detector watches for. */
const MANAGE = 'incident.manage';

export interface DetectorControlLabels {
  readonly dryRun: string;
  readonly dryRunning: string;
  readonly wouldFire: string;
  readonly wouldNotFire: string;
  readonly observations: string;
  readonly noObservations: string;
  readonly enable: string;
  readonly enabling: string;
  readonly disable: string;
  readonly disabling: string;
  readonly cancel: string;
  readonly failed: string;
  readonly unreachable: string;
}

export interface DetectorControlsProps {
  readonly detectorId: string;
  readonly enabled: boolean;
  readonly viewer: Viewer;
  readonly labels: DetectorControlLabels;
}

interface Observation {
  readonly subject: string;
  readonly verdict: string;
  readonly detail: string;
}

interface DryRun {
  readonly wouldFire: boolean;
  readonly observations: readonly Observation[];
}

function text(record: unknown, name: string): string {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'string' ? found : '';
}

function dryRunFrom(body: unknown): DryRun {
  const observations: unknown = Reflect.get(Object(body), 'observations');
  return {
    wouldFire: Reflect.get(Object(body), 'would_fire') === true,
    observations: (Array.isArray(observations) ? observations : []).map(
      (entry): Observation => ({
        subject: text(entry, 'subject'),
        verdict: text(entry, 'verdict'),
        detail: text(entry, 'detail'),
      }),
    ),
  };
}

/** Preview, then enable — or disable outright. Absent for a viewer who may not. */
export function DetectorControls({
  detectorId,
  enabled,
  viewer,
  labels,
}: DetectorControlsProps): ReactNode {
  const [isEnabled, setIsEnabled] = useState(enabled);
  const [dryRun, setDryRun] = useState<DryRun | null>(null);
  const [busy, setBusy] = useState('');
  const [failure, setFailure] = useState('');

  async function ask(operation: string): Promise<unknown> {
    setFailure('');
    let response: Response;
    try {
      response = await fetch(DETECTOR_CONTROL_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ detectorId, operation }),
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
    return Reflect.get(Object(body), 'answer');
  }

  async function preview(): Promise<void> {
    setBusy('dry-run');
    const found = await ask('dry-run');
    setBusy('');
    if (found !== null) setDryRun(dryRunFrom(found));
  }

  async function confirmEnable(): Promise<void> {
    setBusy('enable');
    const found = await ask('enable');
    setBusy('');
    if (found === null) return;
    setIsEnabled(true);
    setDryRun(null);
  }

  async function disable(): Promise<void> {
    setBusy('disable');
    const found = await ask('disable');
    setBusy('');
    if (found === null) return;
    setIsEnabled(false);
    setDryRun(null);
  }

  if (!may(viewer, MANAGE)) return null;

  if (isEnabled) {
    return (
      <div
        data-testid="detector-controls"
        data-detector={detectorId}
        className="flex flex-wrap items-center gap-2"
      >
        <Button
          variant="destructive"
          data-testid="disable-detector"
          state={busy === 'disable' ? 'loading' : 'default'}
          onClick={() => {
            void disable();
          }}
        >
          {busy === 'disable' ? labels.disabling : labels.disable}
        </Button>
        {failure === '' ? null : (
          <span
            data-testid="detector-control-failure"
            className="text-meta text-danger"
          >
            {failure}
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      data-testid="detector-controls"
      data-detector={detectorId}
      className="flex flex-col items-start gap-2"
    >
      <Button
        data-testid="dry-run-detector"
        state={busy === 'dry-run' ? 'loading' : 'default'}
        onClick={() => {
          void preview();
        }}
      >
        {busy === 'dry-run' ? labels.dryRunning : labels.dryRun}
      </Button>

      {dryRun === null ? null : (
        <div data-testid="detector-dry-run" className="flex flex-col gap-2 text-meta">
          <span className="flex items-center gap-2">
            <Badge status={dryRun.wouldFire ? 'firing' : 'clear'} />
            <span>{dryRun.wouldFire ? labels.wouldFire : labels.wouldNotFire}</span>
          </span>
          <span className="text-muted">{labels.observations}</span>
          {dryRun.observations.length === 0 ? (
            <span className="text-muted">{labels.noObservations}</span>
          ) : (
            <ul className="flex flex-col gap-1">
              {dryRun.observations.map((observation, index) => (
                <li
                  key={`${observation.subject}-${String(index)}`}
                  data-testid="detector-dry-run-observation"
                  className="flex flex-wrap items-center gap-2"
                >
                  <span className="font-mono break-all">{observation.subject}</span>
                  <Badge status={observation.verdict} />
                  <span className="text-muted">{observation.detail}</span>
                </li>
              ))}
            </ul>
          )}
          <span className="flex items-center gap-2">
            <Button
              variant="primary"
              data-testid="enable-detector"
              state={busy === 'enable' ? 'loading' : 'default'}
              onClick={() => {
                void confirmEnable();
              }}
            >
              {busy === 'enable' ? labels.enabling : labels.enable}
            </Button>
            <Button
              data-testid="cancel-detector-preview"
              onClick={() => {
                setDryRun(null);
              }}
            >
              {labels.cancel}
            </Button>
          </span>
        </div>
      )}
      {failure === '' ? null : (
        <span data-testid="detector-control-failure" className="text-meta text-danger">
          {failure}
        </span>
      )}
    </div>
  );
}
