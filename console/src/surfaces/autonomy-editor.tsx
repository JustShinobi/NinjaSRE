'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Input, Select } from '@/components/form';
import { Badge } from '@/components/status';

/**
 * Changing what this deployment may do on its own.
 *
 * This is the most consequential setting on the platform — what can happen
 * without a person — and the whole design of this panel is about the order
 * things are read in.
 *
 * **The two answers come before the save, never after.** `preview` replays the
 * deployment's own recorded actions under both policies and says how many would
 * have been decided differently and how many would have become *autonomous*;
 * `explain` resolves one hypothetical action and says which rule wins and why.
 * The save control sits below both, and does not exist until a preview of the
 * current change has come back. A confirmation dialogue would ask a question
 * with no evidence in front of it, which is how somebody approves a change they
 * have not understood.
 *
 * **Nothing here resolves anything.** The console holds no copy of rule
 * precedence, no idea of what a level means, and no opinion about what an
 * action would do. Every one of those is the deployment's answer, rendered.
 *
 * **Dry-run is the propose/act boundary and reads as one.** Its banner uses a
 * state colour rather than the accent, because the accent is what the console
 * uses for "the thing to press" and this is not that — it is a statement about
 * what the deployment is currently doing to the estate.
 */

/** Where every write goes. The console's own process, forwarding once. */
export const AUTONOMY_ENDPOINT = '/api/autonomy';

export interface EditableRule {
  readonly ruleId: string;
  readonly scope: string;
  readonly matcher: string;
  readonly level: string;
  readonly riskBound: string;
  /** The whole record as the deployment sent it, sent back unchanged but for the level. */
  readonly record: Readonly<Record<string, unknown>>;
}

export interface AutonomyLabels {
  readonly level: string;
  readonly preview: string;
  readonly previewing: string;
  readonly explain: string;
  readonly explaining: string;
  readonly explainCapability: string;
  readonly explainResource: string;
  readonly save: string;
  readonly saving: string;
  readonly saved: string;
  readonly failed: string;
  readonly unreachable: string;
  readonly previewFirst: string;
  readonly considered: string;
  readonly changed: string;
  readonly newlyAutonomous: string;
  readonly nothingChanges: string;
  readonly dryRunOn: string;
  readonly dryRunOff: string;
  readonly dryRunBanner: string;
  readonly decision: string;
  readonly winningRule: string;
}

export interface AutonomyEditorProps {
  readonly nodeId: string;
  readonly rules: readonly EditableRule[];
  /** The levels the deployment declares, in the order it declares them. */
  readonly levels: readonly string[];
  /**
   * What each level permits, in words, keyed by the deployment's own slug.
   *
   * Optional because the deployment declares the levels and this console only
   * has words for the ones it knows: a level with no entry renders as its slug,
   * which is what every control here did before and is still usable.
   */
  readonly levelLabels?: Readonly<Record<string, string>>;
  readonly dryRun: boolean;
  readonly labels: AutonomyLabels;
}

interface Previewed {
  readonly summary: string;
  readonly considered: number;
  readonly changed: number;
  readonly newlyAutonomous: number;
  readonly actions: readonly {
    readonly id: string;
    readonly capability: string;
    readonly before: string;
    readonly after: string;
    readonly reason: string;
  }[];
}

interface Explained {
  readonly decision: string;
  readonly level: string;
  readonly reason: string;
  readonly winningRule: string;
}

function number(record: unknown, name: string): number {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'number' && Number.isFinite(found) ? found : 0;
}

function text(record: unknown, name: string): string {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'string' ? found : '';
}

function previewedFrom(body: unknown): Previewed {
  const actions: unknown = Reflect.get(Object(body), 'actions');
  return {
    summary: text(body, 'summary'),
    considered: number(body, 'considered'),
    changed: number(body, 'changed'),
    newlyAutonomous: number(body, 'newly_autonomous'),
    actions: (Array.isArray(actions) ? actions : [])
      // Only the ones that became *more* autonomous. The rest of the diff is
      // reassurance; this is the half somebody has to have read.
      .filter((entry) => Reflect.get(Object(entry), 'more_autonomous') === true)
      .map((entry) => ({
        id: text(entry, 'action_id'),
        capability: text(entry, 'capability'),
        before: text(entry, 'before'),
        after: text(entry, 'after'),
        reason: text(entry, 'after_reason'),
      })),
  };
}

function explainedFrom(body: unknown): Explained {
  return {
    decision: text(body, 'decision'),
    level: text(body, 'level'),
    reason: text(body, 'reason'),
    winningRule: text(body, 'winning_rule'),
  };
}

/** Edit the posture, see what it would have decided differently, then save it. */
export function AutonomyEditor({
  nodeId,
  rules,
  levels,
  levelLabels,
  dryRun,
  labels,
}: AutonomyEditorProps): ReactNode {
  const [levelFor, setLevelFor] = useState<Readonly<Record<string, string>>>({});
  const [simulated, setSimulated] = useState(dryRun);
  const [answer, setAnswer] = useState<Previewed | null>(null);
  const [previewedDocument, setPreviewedDocument] = useState('');
  const [explanation, setExplanation] = useState<Explained | null>(null);
  const [capability, setCapability] = useState('');
  const [resource, setResource] = useState('');
  const [busy, setBusy] = useState('');
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState('');

  const document = {
    dry_run: simulated,
    rules: rules.map((rule) => ({
      ...rule.record,
      level: levelFor[rule.ruleId] ?? rule.level,
    })),
  };
  const serialised = JSON.stringify(document);
  const edited = rules.some(
    (rule) => (levelFor[rule.ruleId] ?? rule.level) !== rule.level,
  );
  const current = answer !== null && serialised === previewedDocument;

  async function ask(operation: string, payload: unknown): Promise<unknown> {
    setFailure('');
    let response: Response;
    try {
      response = await fetch(AUTONOMY_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ nodeId, operation, payload }),
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
    setBusy('preview');
    const found = await ask('preview', document);
    setBusy('');
    if (found === null) return;
    setAnswer(previewedFrom(found));
    setPreviewedDocument(serialised);
  }

  async function explain(): Promise<void> {
    setBusy('explain');
    const found = await ask('explain', {
      capability,
      subjects: [{ resource_id: resource }],
    });
    setBusy('');
    if (found !== null) setExplanation(explainedFrom(found));
  }

  async function save(): Promise<void> {
    setBusy('save');
    const found = await ask('save', JSON.parse(previewedDocument));
    setBusy('');
    if (found === null) return;
    setSaved(true);
    setAnswer(null);
    setPreviewedDocument('');
  }

  async function toggleDryRun(): Promise<void> {
    const next = !simulated;
    setBusy('dry-run');
    const found = await ask('dry-run', { enabled: next });
    setBusy('');
    if (found !== null) setSimulated(next);
  }

  return (
    <div data-testid="autonomy-editor" className="flex flex-col gap-4">
      {/* A state colour, never the accent. The accent means "press this"; this
          means "here is what the deployment is currently doing". */}
      {simulated ? (
        <p
          data-testid="dry-run-banner"
          role="status"
          className="rounded-2 bg-warning-bg px-3 py-1 text-small text-warning"
        >
          {labels.dryRunBanner}
        </p>
      ) : null}

      <div className="flex flex-col gap-3">
        {rules.map((rule) => (
          <div
            key={rule.ruleId}
            data-testid="rule-editor"
            data-rule={rule.ruleId}
            className="flex flex-wrap items-end gap-3"
          >
            <span className="text-meta text-muted font-mono min-w-0 truncate">
              {rule.scope} · {rule.matcher}
            </span>
            <Select
              label={labels.level}
              name={`level-${rule.ruleId}`}
              value={levelFor[rule.ruleId] ?? rule.level}
              // Labelled where the words are, falling back to the slug for a level
              // this console has no words for — see `surfaces/postures.ts`.
              options={levels.map((each) => ({
                value: each,
                label: levelLabels?.[each] ?? each,
              }))}
              onValueChange={(next) => {
                setSaved(false);
                setLevelFor((was) => ({ ...was, [rule.ruleId]: next }));
              }}
            />
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Input
          label={labels.explainCapability}
          name="explain-capability"
          value={capability}
          onValueChange={setCapability}
        />
        <Input
          label={labels.explainResource}
          name="explain-resource"
          value={resource}
          onValueChange={setResource}
        />
        <Button
          data-testid="ask-explain"
          state={
            busy === 'explain'
              ? 'loading'
              : capability === '' || resource === ''
                ? 'disabled'
                : 'default'
          }
          onClick={() => {
            void explain();
          }}
        >
          {busy === 'explain' ? labels.explaining : labels.explain}
        </Button>
        <Button
          data-testid="toggle-dry-run"
          state={busy === 'dry-run' ? 'loading' : 'default'}
          onClick={() => {
            void toggleDryRun();
          }}
        >
          {simulated ? labels.dryRunOff : labels.dryRunOn}
        </Button>
      </div>

      {explanation === null ? null : (
        <dl data-testid="explanation" className="flex flex-col gap-1 text-small">
          <div className="flex items-center gap-2">
            <dt className="text-meta text-muted">{labels.decision}</dt>
            <dd className="flex items-center gap-2">
              <Badge status={explanation.decision} />
              <Badge status={explanation.level} />
            </dd>
          </div>
          <div className="flex items-center gap-2">
            <dt className="text-meta text-muted">{labels.winningRule}</dt>
            <dd className="font-mono break-all">{explanation.winningRule}</dd>
          </div>
          <p className="text-meta text-muted">{explanation.reason}</p>
        </dl>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          data-testid="ask-autonomy-preview"
          state={
            busy === 'preview' ? 'loading' : edited || current ? 'default' : 'disabled'
          }
          onClick={() => {
            void preview();
          }}
        >
          {busy === 'preview' ? labels.previewing : labels.preview}
        </Button>
      </div>

      {answer === null || !current ? null : (
        <div data-testid="autonomy-preview" className="flex flex-col gap-2">
          <p className="text-small">{answer.summary}</p>
          <p className="text-meta text-muted tabular-nums">
            {labels.considered} {answer.considered} · {labels.changed} {answer.changed}{' '}
            · {labels.newlyAutonomous} {answer.newlyAutonomous}
          </p>
          {answer.actions.length === 0 ? (
            <p className="text-meta text-muted">{labels.nothingChanges}</p>
          ) : (
            <ul className="flex flex-col gap-1 text-meta">
              {answer.actions.map((action) => (
                <li
                  key={action.id}
                  data-testid="newly-autonomous"
                  data-capability={action.capability}
                  className="flex flex-wrap items-center gap-2"
                >
                  <span className="font-mono break-all">{action.capability}</span>
                  <Badge status={action.before} />
                  <Badge status={action.after} />
                  <span className="text-muted">{action.reason}</span>
                </li>
              ))}
            </ul>
          )}

          {/* Below the list, never beside the form. What somebody has to have
              read is what would newly happen without them. */}
          <span className="flex items-center gap-3">
            <Button
              data-testid="save-autonomy"
              state={busy === 'save' ? 'loading' : 'default'}
              onClick={() => {
                void save();
              }}
            >
              {busy === 'save' ? labels.saving : labels.save}
            </Button>
          </span>
        </div>
      )}

      {answer === null && edited ? (
        <span data-testid="autonomy-preview-first" className="text-meta text-muted">
          {labels.previewFirst}
        </span>
      ) : null}

      {saved ? (
        <span data-testid="autonomy-saved" className="text-meta text-success">
          {labels.saved}
        </span>
      ) : null}
      {failure === '' ? null : (
        <span data-testid="autonomy-failure" className="text-meta text-danger">
          {failure}
        </span>
      )}
    </div>
  );
}
