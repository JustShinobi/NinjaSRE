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

/**
 * A freeze window or a budget, exactly as the deployment sent it.
 *
 * Neither is edited in place here — only carried through unchanged on every
 * save, and added to. Sending only `rules` and `dry_run` on a save that also
 * has freezes or budgets recorded would `PUT` a document with no `freezes` or
 * `budgets` key, and the write path treats a missing key as an empty list:
 * the level of one rule would silently clear every freeze and every budget
 * this node holds.
 */
export interface EditableBound {
  readonly name: string;
  readonly record: Readonly<Record<string, unknown>>;
}

/** The scope kinds a rule, a freeze or a budget may be given, least specific first. */
export const SCOPE_KINDS = [
  'deployment',
  'team',
  'resource_kind',
  'labels',
  'capability',
  'resource',
  'capability_resource',
] as const;

export interface AutonomyLabels {
  readonly level: string;
  /** The simulation section's own heading, read before any of its controls. */
  readonly simulationTitle: string;
  /** One line saying what the section answers, read before its CTA. */
  readonly simulationDescription: string;
  readonly preview: string;
  readonly previewing: string;
  readonly explain: string;
  readonly explaining: string;
  /** Frames "explain one action" as the narrower question, subordinate to the section's primary CTA. */
  readonly explainIntro: string;
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
  readonly newRuleTitle: string;
  readonly newRuleScope: string;
  readonly newRuleLevel: string;
  readonly newRuleTeam: string;
  readonly newRuleResourceKind: string;
  readonly newRuleResourceId: string;
  readonly newRuleCapability: string;
  readonly newRuleLabelName: string;
  readonly newRuleLabelValue: string;
  readonly addRule: string;
  readonly freezesTitle: string;
  readonly freezeName: string;
  readonly freezeStart: string;
  readonly freezeEnd: string;
  readonly freezeReason: string;
  readonly addFreeze: string;
  readonly budgetsTitle: string;
  readonly budgetName: string;
  readonly budgetLimit: string;
  readonly budgetCountedBy: string;
  readonly addBudget: string;
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
  /** What each scope kind is, in words, keyed by the deployment's own slug. */
  readonly scopeKindLabels?: Readonly<Record<string, string>>;
  readonly dryRun: boolean;
  /** This node's own freezes and budgets, carried through unchanged on every save. */
  readonly freezes?: readonly EditableBound[];
  readonly budgets?: readonly EditableBound[];
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

/** A rule scope built from the "create a rule" form's own fields. */
function scopeRecordOf(
  kind: string,
  team: string,
  resourceKind: string,
  resourceId: string,
  capability: string,
  labelName: string,
  labelValue: string,
): Record<string, unknown> {
  switch (kind) {
    case 'team':
      return { kind, team_node_id: team };
    case 'resource_kind':
      return { kind, resource_kind: resourceKind };
    case 'labels':
      return labelName === ''
        ? { kind, labels: [] }
        : { kind, labels: [{ name: labelName, value: labelValue }] };
    case 'capability':
      return { kind, capability };
    case 'resource':
      return { kind, resource_id: resourceId };
    case 'capability_resource':
      return { kind, capability, resource_id: resourceId };
    default:
      return { kind: 'deployment' };
  }
}

/** The phrase a new rule's own scope reads as, for the same row the read-only table would show. */
function matcherFor(
  kind: string,
  team: string,
  resourceKind: string,
  resourceId: string,
  capability: string,
): string {
  switch (kind) {
    case 'team':
      return team;
    case 'resource_kind':
      return resourceKind;
    case 'capability':
      return capability;
    case 'resource':
      return resourceId;
    case 'capability_resource':
      return `${capability} on ${resourceId}`;
    default:
      return '—';
  }
}

/** Edit the posture, see what it would have decided differently, then save it. */
export function AutonomyEditor({
  nodeId,
  rules,
  levels,
  levelLabels,
  scopeKindLabels,
  dryRun,
  freezes = [],
  budgets = [],
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

  // Rows added this session — appended to the deployment's own rows rather
  // than replacing them, and rendered through the identical per-row editor so
  // a newly created rule's level is changed the same way an existing one's is.
  const [addedRules, setAddedRules] = useState<readonly EditableRule[]>([]);
  const [addedFreezes, setAddedFreezes] = useState<readonly Record<string, unknown>[]>(
    [],
  );
  const [addedBudgets, setAddedBudgets] = useState<readonly Record<string, unknown>[]>(
    [],
  );

  // The "create a rule" form's own fields. Reset after each add, because the
  // row it just created is now edited through the ordinary per-row control.
  const [newScopeKind, setNewScopeKind] = useState('deployment');
  const [newLevel, setNewLevel] = useState(levels[0] ?? '');
  const [newTeam, setNewTeam] = useState('');
  const [newResourceKind, setNewResourceKind] = useState('');
  const [newResourceId, setNewResourceId] = useState('');
  const [newCapability, setNewCapability] = useState('');
  const [newLabelName, setNewLabelName] = useState('');
  const [newLabelValue, setNewLabelValue] = useState('');

  const [freezeName, setFreezeName] = useState('');
  const [freezeStart, setFreezeStart] = useState('');
  const [freezeEnd, setFreezeEnd] = useState('');
  const [freezeReason, setFreezeReason] = useState('');

  const [budgetName, setBudgetName] = useState('');
  const [budgetLimit, setBudgetLimit] = useState('');
  const [budgetCountedBy, setBudgetCountedBy] = useState('');

  const allRules = [...rules, ...addedRules];

  function addRule(): void {
    const scope = scopeRecordOf(
      newScopeKind,
      newTeam,
      newResourceKind,
      newResourceId,
      newCapability,
      newLabelName,
      newLabelValue,
    );
    const ruleId = `new-rule-${String(addedRules.length)}`;
    setAddedRules((was) => [
      ...was,
      {
        ruleId,
        scope: newScopeKind,
        matcher: matcherFor(
          newScopeKind,
          newTeam,
          newResourceKind,
          newResourceId,
          newCapability,
        ),
        level: newLevel,
        riskBound: 'low',
        record: { scope, level: newLevel, risk_bound: 'low' },
      },
    ]);
    setSaved(false);
    setNewScopeKind('deployment');
    setNewTeam('');
    setNewResourceKind('');
    setNewResourceId('');
    setNewCapability('');
    setNewLabelName('');
    setNewLabelValue('');
  }

  function addFreezeRow(): void {
    if (freezeName === '' || freezeStart === '' || freezeEnd === '') return;
    setAddedFreezes((was) => [
      ...was,
      {
        name: freezeName,
        start: freezeStart,
        end: freezeEnd,
        scope: { kind: 'deployment' },
        ...(freezeReason === '' ? {} : { reason: freezeReason }),
      },
    ]);
    setSaved(false);
    setFreezeName('');
    setFreezeStart('');
    setFreezeEnd('');
    setFreezeReason('');
  }

  function addBudgetRow(): void {
    if (budgetName === '' || budgetLimit === '') return;
    setAddedBudgets((was) => [
      ...was,
      {
        name: budgetName,
        limit: Number.parseInt(budgetLimit, 10),
        ...(budgetCountedBy === '' ? {} : { counted_by: budgetCountedBy }),
      },
    ]);
    setSaved(false);
    setBudgetName('');
    setBudgetLimit('');
    setBudgetCountedBy('');
  }

  const document = {
    dry_run: simulated,
    rules: allRules.map((rule) => ({
      ...rule.record,
      level: levelFor[rule.ruleId] ?? rule.level,
    })),
    // Carried through unchanged: a save here must never be the reason a
    // freeze or a budget this node already holds stops existing.
    freezes: [...freezes.map((each) => each.record), ...addedFreezes],
    budgets: [...budgets.map((each) => each.record), ...addedBudgets],
  };
  const serialised = JSON.stringify(document);
  const edited =
    rules.some((rule) => (levelFor[rule.ruleId] ?? rule.level) !== rule.level) ||
    addedRules.length > 0 ||
    addedFreezes.length > 0 ||
    addedBudgets.length > 0;
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
      {/* The rules list is the region that scrolls when a node accumulates
          many of them — bounded on its own, so the tab's budget is never
          the rule count times a row's height. The creation controls and the
          simulation section below stay outside this box, at their own
          height, reachable without scrolling past every row first. */}
      <div
        data-testid="rule-editor-list"
        className="flex flex-col gap-3 max-h-96 overflow-y-auto"
      >
        {allRules.map((rule) => (
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

      {/* Creating a rule is choosing its scope and its level, here — never a
          trip to the raw editor to work out what a scope object looks like.
          Least-specific field first, matching the resolution order the table
          above already reads in. */}
      <details
        id="new-rule"
        data-testid="new-rule"
        className="edge border-border rounded-2 px-3 py-3"
      >
        <summary className="text-strong motion-hover hover:opacity-80">
          {labels.newRuleTitle}
        </summary>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Select
            label={labels.newRuleScope}
            name="new-rule-scope"
            value={newScopeKind}
            options={SCOPE_KINDS.map((kind) => ({
              value: kind,
              label: scopeKindLabels?.[kind] ?? kind,
            }))}
            onValueChange={setNewScopeKind}
          />
          {newScopeKind === 'team' ? (
            <Input
              label={labels.newRuleTeam}
              name="new-rule-team"
              value={newTeam}
              onValueChange={setNewTeam}
            />
          ) : null}
          {newScopeKind === 'resource_kind' ? (
            <Input
              label={labels.newRuleResourceKind}
              name="new-rule-resource-kind"
              value={newResourceKind}
              onValueChange={setNewResourceKind}
            />
          ) : null}
          {newScopeKind === 'capability' || newScopeKind === 'capability_resource' ? (
            <Input
              label={labels.newRuleCapability}
              name="new-rule-capability"
              value={newCapability}
              onValueChange={setNewCapability}
            />
          ) : null}
          {newScopeKind === 'resource' || newScopeKind === 'capability_resource' ? (
            <Input
              label={labels.newRuleResourceId}
              name="new-rule-resource"
              value={newResourceId}
              onValueChange={setNewResourceId}
            />
          ) : null}
          {newScopeKind === 'labels' ? (
            <>
              <Input
                label={labels.newRuleLabelName}
                name="new-rule-label-name"
                value={newLabelName}
                onValueChange={setNewLabelName}
              />
              <Input
                label={labels.newRuleLabelValue}
                name="new-rule-label-value"
                value={newLabelValue}
                onValueChange={setNewLabelValue}
              />
            </>
          ) : null}
          <Select
            label={labels.newRuleLevel}
            name="new-rule-level"
            value={newLevel}
            options={levels.map((each) => ({
              value: each,
              label: levelLabels?.[each] ?? each,
            }))}
            onValueChange={setNewLevel}
          />
          <Button
            data-testid="add-rule"
            onClick={() => {
              addRule();
            }}
          >
            {labels.addRule}
          </Button>
        </div>
      </details>

      <details
        id="new-freeze"
        data-testid="new-freeze"
        className="edge border-border rounded-2 px-3 py-3"
      >
        <summary className="text-strong motion-hover hover:opacity-80">
          {labels.freezesTitle}
        </summary>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Input
            label={labels.freezeName}
            name="freeze-name"
            value={freezeName}
            onValueChange={setFreezeName}
          />
          <Input
            label={labels.freezeStart}
            name="freeze-start"
            value={freezeStart}
            onValueChange={setFreezeStart}
          />
          <Input
            label={labels.freezeEnd}
            name="freeze-end"
            value={freezeEnd}
            onValueChange={setFreezeEnd}
          />
          <Input
            label={labels.freezeReason}
            name="freeze-reason"
            value={freezeReason}
            onValueChange={setFreezeReason}
          />
          <Button
            data-testid="add-freeze"
            state={
              freezeName === '' || freezeStart === '' || freezeEnd === ''
                ? 'disabled'
                : 'default'
            }
            onClick={() => {
              addFreezeRow();
            }}
          >
            {labels.addFreeze}
          </Button>
        </div>
      </details>

      <details
        data-testid="new-budget"
        className="edge border-border rounded-2 px-3 py-3"
      >
        <summary className="text-strong motion-hover hover:opacity-80">
          {labels.budgetsTitle}
        </summary>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Input
            label={labels.budgetName}
            name="budget-name"
            value={budgetName}
            onValueChange={setBudgetName}
          />
          <Input
            label={labels.budgetLimit}
            name="budget-limit"
            type="number"
            value={budgetLimit}
            onValueChange={setBudgetLimit}
          />
          <Input
            label={labels.budgetCountedBy}
            name="budget-counted-by"
            value={budgetCountedBy}
            onValueChange={setBudgetCountedBy}
          />
          <Button
            data-testid="add-budget"
            state={budgetName === '' || budgetLimit === '' ? 'disabled' : 'default'}
            onClick={() => {
              addBudgetRow();
            }}
          >
            {labels.addBudget}
          </Button>
        </div>
      </details>

      {/* One question, one path: replay this node's own history under the
          change above, then decide whether to also flip the whole
          deployment into simulate-only mode. Exactly one primary control —
          the toggle stays beside it as a plain secondary action (it takes no
          extra input), and the narrower "one hypothetical action" question
          moves to the foot of the section, behind its own line, because it
          needs two fields before it means anything and never gates the save
          below. */}
      <div data-testid="autonomy-simulation" className="flex flex-col gap-3">
        <h3 className="text-strong">{labels.simulationTitle}</h3>
        <p className="text-meta text-muted max-w-prose">
          {labels.simulationDescription}
        </p>

        {simulated ? (
          <p
            data-testid="dry-run-banner"
            role="status"
            className="rounded-2 bg-warning-bg px-3 py-1 text-small text-warning"
          >
            {labels.dryRunBanner}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            data-testid="ask-autonomy-preview"
            state={
              busy === 'preview'
                ? 'loading'
                : edited || current
                  ? 'default'
                  : 'disabled'
            }
            onClick={() => {
              void preview();
            }}
          >
            {busy === 'preview' ? labels.previewing : labels.preview}
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

        {answer === null || !current ? null : (
          <div data-testid="autonomy-preview" className="flex flex-col gap-2">
            <p className="text-small">{answer.summary}</p>
            <p className="text-meta text-muted tabular-nums">
              {labels.considered} {answer.considered} · {labels.changed}{' '}
              {answer.changed} · {labels.newlyAutonomous} {answer.newlyAutonomous}
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

        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <p className="text-meta text-muted">{labels.explainIntro}</p>
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
        </div>
      </div>
    </div>
  );
}
