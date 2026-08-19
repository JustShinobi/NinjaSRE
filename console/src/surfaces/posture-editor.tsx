'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';
import { Select } from '@/components/form';

import { AUTONOMY_ENDPOINT, type EditableBound } from './autonomy-editor';

/**
 * Changing the one rule that decides what this deployment may do on its own,
 * without the rest of the rule editor around it.
 *
 * Posture's own question — "what can this deployment do alone, right now" —
 * is answered by a single rule: the one scoped to the whole deployment
 * (`scope.kind === 'deployment'`). Rules & windows owns every other rule and
 * the form that creates one; this control only ever touches that one row,
 * and it writes through the same `/api/autonomy` courier `AutonomyEditor`
 * uses, with the same shape of document — because the write path treats a
 * missing `freezes`/`budgets` key as "clear every one this node holds", so a
 * save from here has to carry them through unchanged exactly as
 * `AutonomyEditor` already does, never merely the rule that changed.
 *
 * **No preview gate.** `AutonomyEditor`'s own save is gated behind having
 * previewed the exact document about to be sent — deliberate, for a form
 * that can narrow or widen any scope, including ones a person did not mean
 * to touch. This control only ever changes the level of one already-named
 * scope (the whole deployment), which is the same one-field change Posture's
 * subtitle already states in plain words before anyone opens the selector —
 * there is nothing a preview would tell somebody here that the selector's
 * own label and the level's own description do not already say.
 */

/** Every other rule this node holds, exactly as the deployment sent it. */
export type PostureRule = Readonly<Record<string, unknown>>;

export interface PostureEditorLabels {
  readonly level: string;
  readonly save: string;
  readonly saving: string;
  readonly saved: string;
  readonly failed: string;
  readonly unreachable: string;
}

export interface PostureEditorProps {
  readonly nodeId: string;
  /** The levels to offer, in the order to offer them. */
  readonly levels: readonly string[];
  /** What each level permits, in words, keyed by the deployment's own slug. */
  readonly levelLabels?: Readonly<Record<string, string>>;
  /** The deployment-scope rule's level today, or the safest level when no
   * rule names that scope yet. */
  readonly currentLevel: string;
  /**
   * Every rule this node holds, exactly as the deployment sent it — read as
   * `unknown[]`, the same shape `surfaces/read.ts`'s `list()` hands every
   * screen, and narrowed here rather than asking the server component to
   * cast first.
   */
  readonly rules: readonly unknown[];
  readonly dryRun: boolean;
  readonly freezes?: readonly EditableBound[];
  readonly budgets?: readonly EditableBound[];
  /** The risk bound a newly created deployment-scope rule is given — unused
   * once such a rule already exists, since only its `level` is ever changed. */
  readonly riskBound: string;
  readonly labels: PostureEditorLabels;
}

function scopeKindOf(rule: unknown): string {
  const scope: unknown = Reflect.get(Object(rule), 'scope');
  const kind: unknown = Reflect.get(Object(scope), 'kind');
  return typeof kind === 'string' ? kind : '';
}

/** `rules` with the deployment-scope row set to `level` — added, if none named that scope yet. */
function rulesWithPosture(
  rules: readonly unknown[],
  level: string,
  riskBound: string,
): readonly PostureRule[] {
  const asRecords = rules.map((rule) => rule as PostureRule);
  const hasDeploymentRule = asRecords.some(
    (rule) => scopeKindOf(rule) === 'deployment',
  );
  if (hasDeploymentRule) {
    return asRecords.map((rule) =>
      scopeKindOf(rule) === 'deployment' ? { ...rule, level } : rule,
    );
  }
  return [
    ...asRecords,
    { scope: { kind: 'deployment' }, level, risk_bound: riskBound },
  ];
}

/** The level selector for the deployment-scope rule, with a save beside it. */
export function PostureEditor({
  nodeId,
  levels,
  levelLabels,
  currentLevel,
  rules,
  dryRun,
  freezes = [],
  budgets = [],
  riskBound,
  labels,
}: PostureEditorProps): ReactNode {
  const [level, setLevel] = useState(currentLevel);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState('');

  async function save(): Promise<void> {
    setBusy(true);
    setFailure('');
    setSaved(false);
    const payload = {
      dry_run: dryRun,
      rules: rulesWithPosture(rules, level, riskBound),
      // Carried through unchanged, the same discipline `AutonomyEditor` uses:
      // a save that omitted these would `PUT` a document with no `freezes` or
      // `budgets` key, and the write path treats a missing key as an empty
      // list — this control must never be the reason one silently clears.
      freezes: freezes.map((each) => each.record),
      budgets: budgets.map((each) => each.record),
    };
    let response: Response;
    try {
      response = await fetch(AUTONOMY_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ nodeId, operation: 'save', payload }),
      });
    } catch {
      setBusy(false);
      setFailure(labels.unreachable);
      return;
    }
    const body: unknown = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      const reason: unknown = Reflect.get(Object(body), 'reason');
      setFailure(typeof reason === 'string' && reason !== '' ? reason : labels.failed);
      return;
    }
    setSaved(true);
  }

  return (
    <div data-testid="posture-editor" className="flex flex-wrap items-end gap-3">
      <Select
        label={labels.level}
        name="posture-level"
        value={level}
        options={levels.map((each) => ({
          value: each,
          label: levelLabels?.[each] ?? each,
        }))}
        onValueChange={(next) => {
          setLevel(next);
          setSaved(false);
        }}
      />
      <Button
        variant="primary"
        data-testid="save-posture"
        state={busy ? 'loading' : 'default'}
        onClick={() => {
          void save();
        }}
      >
        {busy ? labels.saving : labels.save}
      </Button>
      {saved ? (
        <span data-testid="posture-saved" className="text-meta text-success">
          {labels.saved}
        </span>
      ) : null}
      {failure === '' ? null : (
        <span data-testid="posture-failure" className="text-meta text-danger">
          {failure}
        </span>
      )}
    </div>
  );
}
