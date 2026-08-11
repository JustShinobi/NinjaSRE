'use client';

import { useState, type ReactNode } from 'react';

/**
 * See what a rule would do before it decides anything.
 *
 * The same discipline the configuration editor's preview enforces, and the same
 * guarantee behind it: the answer comes from the deployment, not from a matcher
 * reimplemented here. What this component holds is a payload, a source, and
 * whatever the server last said about them.
 *
 * **Save is disabled until a simulation has been seen.** Not as a nag — as the
 * one thing that makes "nothing that decides behaviour is saved without seeing
 * its effect" true rather than encouraged. Editing the payload after simulating
 * clears the answer, so the button re-locks: an operator who changed the input
 * has not seen the effect of what they are about to save.
 */

/** Where the simulation is asked. The console's own process, forwarding once. */
export const SIMULATE_ENDPOINT = '/api/simulate';

export interface SimulationLabels {
  readonly source: string;
  readonly payload: string;
  readonly simulate: string;
  readonly simulating: string;
  readonly save: string;
  readonly needsSimulation: string;
  readonly rule: string;
  readonly team: string;
  readonly action: string;
  readonly failed: string;
  readonly unreachable: string;
  readonly malformed: string;
}

export interface RuleSimulatorProps {
  /** The receivers this deployment serves. A simulation names one of them. */
  readonly sources: readonly string[];
  readonly labels: SimulationLabels;
}

interface Answer {
  readonly rule: string;
  readonly team: string;
  readonly action: string;
  readonly reason: string;
}

/** A payload, a source, the deployment's answer, and a save that waits for it. */
export function RuleSimulator({ sources, labels }: RuleSimulatorProps): ReactNode {
  const [source, setSource] = useState(sources[0] ?? '');
  const [payload, setPayload] = useState('');
  const [answer, setAnswer] = useState<Answer | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');

  /** Any edit invalidates the answer: the effect shown is no longer this input's. */
  function change(next: () => void): void {
    setAnswer(undefined);
    setFailure('');
    next();
  }

  async function simulate(): Promise<void> {
    let parsed: unknown;
    try {
      parsed = JSON.parse(payload === '' ? '{}' : payload);
    } catch {
      setFailure(labels.malformed);
      return;
    }
    setBusy(true);
    setFailure('');
    let response: Response;
    try {
      response = await fetch(SIMULATE_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ source, payload: parsed }),
      });
    } catch {
      setBusy(false);
      setFailure(labels.unreachable);
      return;
    }
    const simulated: unknown = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setFailure(labels.failed);
      return;
    }
    setAnswer({
      rule: String(Reflect.get(Object(simulated), 'rule_id') ?? ''),
      team: String(Reflect.get(Object(simulated), 'team') ?? ''),
      action: String(Reflect.get(Object(simulated), 'action') ?? ''),
      reason: String(Reflect.get(Object(simulated), 'reason') ?? ''),
    });
  }

  return (
    <div className="flex flex-col gap-2" data-testid="rule-simulator">
      <label className="text-meta text-muted flex flex-col gap-1">
        {labels.source}
        <select
          className="text-small edge border-border rounded border px-2 py-1"
          data-testid="simulate-source"
          value={source}
          onChange={(event) => {
            change(() => {
              setSource(event.target.value);
            });
          }}
        >
          {sources.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>

      <label className="text-meta text-muted flex flex-col gap-1">
        {labels.payload}
        <textarea
          className="text-meta edge border-border rounded border px-2 py-1 font-mono"
          data-testid="simulate-payload"
          rows={4}
          value={payload}
          onChange={(event) => {
            change(() => {
              setPayload(event.target.value);
            });
          }}
        />
      </label>

      <div className="flex items-center gap-3">
        <button
          type="button"
          className="text-small text-strong self-start underline"
          data-testid="simulate"
          disabled={busy}
          onClick={() => {
            void simulate();
          }}
        >
          {busy ? labels.simulating : labels.simulate}
        </button>
        <button
          type="button"
          className="text-small self-start underline disabled:opacity-50"
          data-testid="simulate-save"
          disabled={answer === undefined}
          title={answer === undefined ? labels.needsSimulation : undefined}
        >
          {labels.save}
        </button>
      </div>

      {answer === undefined ? (
        <span className="text-meta text-muted" data-testid="simulate-pending">
          {labels.needsSimulation}
        </span>
      ) : (
        <dl className="text-meta flex flex-col gap-1" data-testid="simulate-answer">
          <div className="flex gap-2">
            <dt className="text-muted">{labels.rule}</dt>
            <dd className="text-strong" data-testid="simulate-rule">
              {answer.rule}
            </dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-muted">{labels.team}</dt>
            <dd data-testid="simulate-team">{answer.team}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-muted">{labels.action}</dt>
            <dd data-testid="simulate-action">{answer.action}</dd>
          </div>
          {answer.reason === '' ? null : (
            <span className="text-muted" data-testid="simulate-reason">
              {answer.reason}
            </span>
          )}
        </dl>
      )}

      {failure === '' ? null : (
        <span className="text-meta text-danger" data-testid="simulate-failure">
          {failure}
        </span>
      )}
    </div>
  );
}
