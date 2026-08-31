import type { ReactNode } from 'react';

import { Badge, Link, TabLinks } from '@/components';
import {
  BridgedServerStateChip,
  ResolvedChip,
  SpecialistStateChip,
} from '@/components/status';
import { cx } from '@/design/cx';
import {
  ActivityIcon,
  AlertCircleIcon,
  CheckIcon,
  ClipboardIcon,
  SearchIcon,
  SettingsIcon,
} from '@/design/icons';
import { statusPresentation } from '@/design/status';
import { humaniseIdentifier } from '@/i18n/format';
import { message, type Locale, type MessageKey } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import {
  AdvancedConfigSection,
  advancedConfigSectionId,
} from '../advanced-config-section';
import {
  CapabilityBrowser,
  type BrowsableSkill,
  type BrowsableTool,
} from '../capability-browser';
import { bridgedServers, capabilityRows, type CapabilityRow } from '../capability-rows';
import type { SurfaceContext } from '../context';
import { HierarchyGraph, type HierarchyRank } from '../graph';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import { postureName } from '../postures';
import {
  ask,
  authorised,
  dataOf,
  dependencyOf,
  field,
  flag,
  list,
  number,
  optionalRead,
  panelRead,
  read,
  stateOf,
  text,
  type PanelData,
} from '../read';
import {
  STAGE_TREATMENT_CLASSES,
  stageRegime,
  stageTreatment,
  toolSummary,
} from './agent-pipeline-metro';
import { RiskLadder } from '../risk-ladder';
import { placedTree } from '../tree';
import { readViewState, resolveNode, type FilterName } from '../url-state';
import { TeamTab } from './team-context';

/**
 * What the agent is, what it can do, and what it will do on its own.
 *
 * Three questions and one subject, which is why it is one area with three
 * sections rather than three areas: an operator deciding whether to trust this
 * with a cluster asks all three in one sitting, and a navigation that split them
 * would make the third one — the one that actually decides it — the one nobody
 * finds.
 *
 * **No provider and no model identifier appears beside a stage.** Eight model
 * roles exist and a deployment binds each one; a screen printing a vendor's
 * model next to "diagnose" would be presenting one deployment's choice as the
 * shape of the software. What a stage shows is its *role*. What a role resolves
 * to is a configuration value, on the panel that carries provenance — a role a
 * node bound names the node, and a role nobody bound names the deployment
 * default and says so, but a provider is never named without saying which of
 * the two it is (`roleBinding`, below).
 *
 * **The tools are grouped by the one distinction that changes the risk.** Reads
 * and writes, from the deployment's own side-effect level — not by domain, not
 * by integration. A tool whose integration is missing is dimmed *with the
 * integration named*, because that is the answer to "why did the investigation
 * not try that", and today it is an answer nothing gives.
 *
 * **The autonomy section is a reading and never an editor.** The deployment
 * answers what each class of action would meet; this renders the sentences and
 * links to the editor. The emergency stop is not here — it is in the frame,
 * reachable from every screen, because the ten seconds it exists for are not ten
 * seconds anybody spends looking for a tab.
 */

/**
 * The four sections, in the order the questions are asked. `team` is the
 * newest: what the team's own operating context says, absorbed whole from
 * the screen that used to carry it on its own address — see `team-context.tsx`'s
 * own note on why it moved rather than staying linked from here.
 *
 * `'topology'` is a stable internal slug, not what the first tab is called —
 * it names the URL (`?tab=topology`), `data-tab`, and the branches below,
 * and stays put so an existing deep link keeps landing on the same content.
 * What a viewer reads is `agent.tab.topology`'s own translated value, which
 * says "Pipeline" — the word the board uses for what this tab draws now
 * that its hero is the six-stage metro line rather than the hierarchy graph
 * the slug is named for.
 */
export const AGENT_TABS = ['topology', 'tools', 'autonomy', 'team'] as const;

export type AgentTab = (typeof AGENT_TABS)[number];

export const AGENT_FILTERS: readonly FilterName[] = ['node', 'tab'];

/** The tab the address names, and the first one when it names nothing known. */
export function tabFrom(value: string): AgentTab {
  return AGENT_TABS.find((tab) => tab === value) ?? AGENT_TABS[0];
}

/** Where a rank of the hierarchy sits, and what it is called. */
const ORCHESTRATOR = 'orchestrator';
const STAGES = 'stages';
const SPECIALISTS = 'specialists';

/** The permission the policy editor needs, so the link is absent without it. */
const WRITE = 'config.write';

/**
 * The agent's own configuration group, and the nine fields in it that no
 * control on this screen reaches.
 *
 * Four are the budgets the panel below already *shows*: it reads them from the
 * same catalogue and prints what one investigation may spend, but printing is
 * not editing, and its own empty state used to send the reader to the raw
 * editor to change one. The other five — the three per-role prompt overrides
 * and the operating-context switch — had no surface here at all.
 *
 * The labels are the ones this screen already uses for the budgets it prints,
 * so the same number is not called two different things a scroll apart.
 */
const AGENT_ADVANCED_PREFIX = 'agents.';

/**
 * The capabilities group: the allow-list, the deny-list, the per-capability
 * parameters, and the bridged protocol servers a team has registered.
 *
 * `protocol_servers` is the only field here of a type this console draws a
 * control for — the rest are open-ended mappings or plain string lists the
 * raw editor never offered a form for either, so they are on this page's
 * `capabilities.` prefix too (read-only, correctly, rather than absent), but
 * this is the only one that flips a page from "sem dona" to a real control.
 */
const CAPABILITIES_ADVANCED_PREFIX = 'capabilities.';

/**
 * Where an empty state whose field already lives on this same page sends the
 * operator, instead of the retired editor: down to the section that draws it.
 */
const AGENT_ADVANCED_HREF = `#${advancedConfigSectionId(AGENT_ADVANCED_PREFIX)}`;
const CAPABILITIES_ADVANCED_HREF = `#${advancedConfigSectionId(CAPABILITIES_ADVANCED_PREFIX)}`;

const AGENT_ADVANCED_FIELD_LIST: readonly {
  readonly path: string;
  readonly label: MessageKey;
}[] = [
  { path: 'agents.max_iterations', label: 'agent.budgets.maxIterations' },
  {
    path: 'agents.max_parallel_subagents',
    label: 'agent.budgets.maxParallelSubagents',
  },
  { path: 'agents.max_subagent_depth', label: 'agent.budgets.maxSubagentDepth' },
  {
    path: 'agents.max_subagent_iterations',
    label: 'agent.advanced.field.maxSubagentIterations',
  },
  {
    path: 'agents.operating_context.enabled',
    label: 'agent.advanced.field.operatingContextEnabled',
  },
  { path: 'agents.prompts.diagnose', label: 'agent.advanced.field.promptDiagnose' },
  { path: 'agents.prompts.intake', label: 'agent.advanced.field.promptIntake' },
  {
    path: 'agents.prompts.investigator',
    label: 'agent.advanced.field.promptInvestigator',
  },
  { path: 'agents.tool_budget', label: 'agent.budgets.toolBudget' },
];

function nothing(): PanelData<unknown> {
  return { status: 'ready', data: {} };
}

/**
 * What the posture that is stored decided about the actions that were recorded.
 *
 * The preview route takes a *proposed* document and replays history against it.
 * Posting the current one back is how a reader asks the narrower question — "and
 * what did this policy actually do" — with the deployment answering, which is
 * the whole reason the console does not compute it: a client that replayed the
 * history itself would be a second resolver, and the day it drifted somebody
 * would raise autonomy on the strength of a sentence this process wrote.
 */
async function currentPolicyReplay(node: string, init: RequestInit): Promise<unknown> {
  const stored = await read('/v1/autonomy/policy/{node_id}', {
    ...init,
    params: { node_id: node },
  });
  const document = {
    dry_run: flag(stored, 'dry_run'),
    rules: list(stored, 'rules'),
    freezes: list(stored, 'freezes'),
    budgets: list(stored, 'budgets'),
    overrides: list(stored, 'overrides'),
  };
  return ask('/v1/autonomy/policy/{node_id}/preview', document, {
    ...init,
    params: { node_id: node },
  });
}

export async function AgentScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, search } = context;
  const state = readViewState(search, AGENT_FILTERS);
  const tab = tabFrom(state.filters.tab ?? '');
  const init = authorised(credential);

  const tree = await panelRead('/v1/config', () => read('/v1/config', init));
  const placed = placedTree(dataOf(tree));
  const node = resolveNode(state, viewer, placed);
  const address = (wanted: AgentTab): string =>
    node === '' ? `?tab=${wanted}` : `?node=${encodeURIComponent(node)}&tab=${wanted}`;

  // The Pipeline tab's own summary cards read what Tools, Autonomy and Team
  // Context already read -- the same routes, one more time only on the tab
  // that shows all three at once, never a new source of any of the three
  // numbers.
  const needsSummary = tab === 'topology';

  const [
    pipeline,
    effective,
    fields,
    capabilities,
    entries,
    outlook,
    runs,
    summaryCapabilities,
    summaryEntries,
    summaryOutlook,
    summaryContext,
  ] = await Promise.all([
    tab === 'topology'
      ? panelRead<unknown>('/v1/agent/pipeline', () => read('/v1/agent/pipeline', init))
      : nothing(),
    node === '' || tab === 'autonomy' || tab === 'team'
      ? nothing()
      : optionalRead<unknown>('/v1/config/{node_id}', () =>
          read('/v1/config/{node_id}', { ...init, params: { node_id: node } }),
        ),
    node === '' || (tab !== 'topology' && tab !== 'tools')
      ? nothing()
      : optionalRead<unknown>('/v1/config/{node_id}/fields', () =>
          read('/v1/config/{node_id}/fields', { ...init, params: { node_id: node } }),
        ),
    tab === 'tools'
      ? panelRead<unknown>('/v1/capabilities', () => read('/v1/capabilities', init))
      : nothing(),
    node === '' || tab !== 'tools'
      ? nothing()
      : optionalRead<unknown>('/v1/config/{node_id}/catalogue', () =>
          read('/v1/config/{node_id}/catalogue', {
            ...init,
            params: { node_id: node },
          }),
        ),
    node === '' || tab !== 'autonomy'
      ? nothing()
      : optionalRead<unknown>('/v1/autonomy/policy/{node_id}/outlook', () =>
          read('/v1/autonomy/policy/{node_id}/outlook', {
            ...init,
            params: { node_id: node },
          }),
        ),
    needsSummary
      ? panelRead<unknown>('/v1/runs', () => read('/v1/runs', init))
      : nothing(),
    needsSummary
      ? panelRead<unknown>('/v1/capabilities', () => read('/v1/capabilities', init))
      : nothing(),
    node === '' || !needsSummary
      ? nothing()
      : optionalRead<unknown>('/v1/config/{node_id}/catalogue', () =>
          read('/v1/config/{node_id}/catalogue', {
            ...init,
            params: { node_id: node },
          }),
        ),
    node === '' || !needsSummary
      ? nothing()
      : optionalRead<unknown>('/v1/autonomy/policy/{node_id}/outlook', () =>
          read('/v1/autonomy/policy/{node_id}/outlook', {
            ...init,
            params: { node_id: node },
          }),
        ),
    node === '' || !needsSummary
      ? nothing()
      : optionalRead<unknown>('/v1/config/{node_id}/operating-context', () =>
          read('/v1/config/{node_id}/operating-context', {
            ...init,
            params: { node_id: node },
          }),
        ),
  ]);

  // What the posture as it stands decided about what has actually happened.
  // Complements the representative set rather than replacing it: a deployment
  // on its first day has no history, and the first day is when somebody decides
  // whether to let this act. Asked only where there is both a node and the
  // permission — the route takes `config.write`, because it reads the
  // deployment's own decision history to answer.
  const replay =
    node === '' || tab !== 'autonomy' || !may(viewer, WRITE)
      ? nothing()
      : await optionalRead<unknown>('/v1/autonomy/policy/{node_id}/preview', () =>
          currentPolicyReplay(node, init),
        );

  // Self-contained rather than pre-fetched into a prop, like every other
  // tab this reorganisation folded in from its own former screen: `TeamTab`
  // reads the same address this function already parsed and does its own
  // requests, so it stays independently testable and this function does not
  // have to know the shape of what it fetches.
  const team = tab === 'team' ? await TeamTab(context) : null;

  return (
    <>
      <AreaHeader
        area={areaFor('agent')}
        locale={locale}
        // The crumb names the node, never its identifier. It read "The agent ›
        // default" — the last step of a trail spelled as a database key, under
        // a heading that already says where the reader is. The tree carries a
        // name for every node it places; this is the one place that was not
        // asking it for one. With one node there is no choice to describe, so
        // there is no crumb either.
        nested={
          node === '' || placed.length < 2
            ? []
            : [{ label: placed.find((each) => each.id === node)?.name ?? node }]
        }
      />

      <TabLinks
        label={message(locale, 'agent.tabs')}
        selected={tab}
        tabs={AGENT_TABS.map((each) => ({
          id: each,
          label: message(locale, `agent.tab.${each}`),
          href: address(each),
        }))}
      />

      <div className="flex flex-col gap-5 mt-4">
        {tab === 'topology' ? (
          <TopologyTab
            locale={locale}
            pipeline={pipeline}
            effective={effective}
            fields={fields}
            nodeId={node}
            writable={may(viewer, WRITE)}
            runs={runs}
            summaryCapabilities={summaryCapabilities}
            summaryEntries={summaryEntries}
            summaryOutlook={summaryOutlook}
            summaryContext={summaryContext}
            address={address}
          />
        ) : null}
        {tab === 'tools' ? (
          <ToolsTab
            locale={locale}
            capabilities={capabilities}
            entries={entries}
            effective={effective}
            fields={fields}
            node={node}
            writable={may(viewer, WRITE)}
          />
        ) : null}
        {tab === 'autonomy' ? (
          <AutonomyTab
            locale={locale}
            outlook={outlook}
            replay={replay}
            node={node}
            viewer={viewer}
          />
        ) : null}
        {tab === 'team' ? team : null}
      </div>
    </>
  );
}

// --- What it is ------------------------------------------------------------------

/** One specialist a team declares. */
interface SubAgent {
  readonly name: string;
  readonly description: string;
  readonly enabled: boolean;
  readonly capabilities: readonly string[];
  readonly modelRole: string;
}

function subAgentsOf(values: unknown): readonly SubAgent[] {
  return list(field(values, 'agents'), 'subagents').map((entry) => ({
    name: text(entry, 'name'),
    description: text(entry, 'description'),
    // The schema's default is on, so an entry that says nothing is enabled. A
    // console that read a missing key as off would draw a team's whole topology
    // switched off the day somebody wrote it by hand.
    enabled: field(entry, 'enabled') !== false,
    capabilities: list(entry, 'capabilities').map(String),
    modelRole: text(entry, 'model_role'),
  }));
}

/** One icon per stage, in the order the pipeline serves them. */
const STAGE_ICON: Readonly<
  Record<string, (props: { className?: string }) => ReactNode>
> = {
  resolve_integrations: SettingsIcon,
  intake: AlertCircleIcon,
  plan_evidence: ClipboardIcon,
  gather_evidence: SearchIcon,
  diagnose: ActivityIcon,
  deliver: CheckIcon,
};

/** The six-node line the Pipeline tab opens with, one look at what a run does. */
function PipelineMetro({
  locale,
  stages,
  runs,
}: {
  readonly locale: Locale;
  readonly stages: readonly unknown[];
  readonly runs: PanelData<unknown>;
}): ReactNode {
  if (stages.length === 0) return null;
  const inFlight =
    runs.status === 'ready'
      ? list(dataOf(runs), 'runs').filter((run) => text(run, 'status') === 'running')
          .length
      : 0;
  const stageNames = stages.map((stage) => text(stage, 'name'));
  // A run's own summary says whether it is running at all (`inFlight`,
  // above) but nothing on it yet names which of the six stages it is
  // running -- so there is no honest way to light one station up over the
  // rest. Every station draws not-reached until a field exists to read
  // instead of guess; `stageTreatment` already carries the other two
  // treatments, so wiring a real value in here is the only change a future
  // reader needs to make.
  const currentStageName: string | undefined = undefined;
  return (
    <div className="flex flex-col gap-5 rounded-3 edge border-border bg-raised p-5">
      <div className="flex items-baseline gap-3">
        <span className="text-strong">{message(locale, 'agent.metro.title')}</span>
        <span className="text-meta text-muted">
          {message(locale, 'agent.metro.subtitle')}
        </span>
        {inFlight === 0 ? null : (
          <span
            data-testid="pipeline-in-flight"
            className="ml-auto flex items-center gap-2 rounded-full bg-accent-bg px-3 py-1 text-small text-accent"
          >
            <span aria-hidden="true" className="icon-inline rotate-45 bg-accent" />
            {message(locale, 'agent.metro.inFlight', { count: inFlight })}
          </span>
        )}
      </div>
      <div className="relative grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {/*
         * The rail: what makes six stages read as the one sequence every run
         * walks, rather than six unrelated cards. Drawn only once the grid is
         * a single row (`lg`) -- at the narrower two/three-column layouts the
         * stages wrap onto more than one line, and one line spanning the
         * full width would cut across rows that are not actually adjacent.
         *
         * Insets are computed from the stage count rather than a literal
         * "6", landing on the horizontal centre of the first and the last
         * icon: half a column's own width, where a column's width already
         * subtracts the gaps `gap-4` puts between columns (`--space-4`, the
         * same token `gap-4` itself draws from) -- not an approximation.
         * Positioned behind the row in DOM order, so each icon's own opaque
         * fill paints over the segment directly behind it, and the rail only
         * shows in the space between stages, the way the board draws it.
         */}
        <div
          aria-hidden="true"
          data-testid="pipeline-metro-rail"
          className="absolute top-0 hidden h-6 items-center lg:flex"
          style={{
            insetInlineStart: `calc((100% - ${String(stages.length - 1)} * var(--space-4)) / ${String(stages.length * 2)})`,
            insetInlineEnd: `calc((100% - ${String(stages.length - 1)} * var(--space-4)) / ${String(stages.length * 2)})`,
          }}
        >
          <span className="h-0 w-full edge border-border" />
        </div>
        {stages.map((stage) => {
          const name = text(stage, 'name');
          const Icon = STAGE_ICON[name] ?? SettingsIcon;
          const regime = stageRegime(name, text(stage, 'model_role'));
          const treatment = stageTreatment(stageNames, name, currentStageName);
          return (
            <div
              key={name}
              data-testid="pipeline-metro-node"
              data-stage={name}
              className="flex flex-col items-center gap-2 text-center"
            >
              <span
                data-testid="pipeline-metro-station"
                data-treatment={treatment}
                className={cx(
                  'flex size-7 items-center justify-center rounded-full edge-emphasis',
                  STAGE_TREATMENT_CLASSES[treatment],
                  treatment === 'running' && 'pulse-live',
                )}
              >
                {treatment === 'running' ? (
                  <span aria-hidden="true" className="pulse-live-ring text-accent" />
                ) : null}
                <Icon className="icon-head" />
              </span>
              <span
                data-testid="pipeline-metro-regime"
                className="font-mono text-micro text-muted"
              >
                {regime}
              </span>
              <span
                data-testid="pipeline-metro-name"
                className="text-small font-medium"
              >
                {humaniseIdentifier(name)}
              </span>
              <span data-testid="pipeline-metro-copy" className="text-micro text-muted">
                {message(locale, `agent.metro.copy.${name}` as MessageKey)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** The Tools card: enabled ratio, top domains, and the three side-effect buckets. */
function ToolsSummaryCard({
  locale,
  capabilities,
  entries,
  address,
}: {
  readonly locale: Locale;
  readonly capabilities: PanelData<unknown>;
  readonly entries: PanelData<unknown>;
  readonly address: (wanted: AgentTab) => string;
}): ReactNode {
  const rows = capabilityRows(dataOf(capabilities), dataOf(entries));
  const tools = rows.filter((row) => row.kind === 'tool');
  const total = tools.length;
  const summary = toolSummary(tools);
  const byDomain = new Map<string, number>();
  for (const row of tools) {
    if (row.domain === '') continue;
    byDomain.set(row.domain, (byDomain.get(row.domain) ?? 0) + 1);
  }
  const topDomains = [...byDomain.entries()]
    .sort(([, left], [, right]) => right - left)
    .slice(0, 6);
  const max = topDomains[0]?.[1] ?? 1;
  return (
    <div
      data-testid="pipeline-summary-tools"
      className="flex flex-col gap-3 rounded-3 edge border-border bg-raised p-4"
    >
      <Link href={address('tools')}>{message(locale, 'agent.tab.tools')}</Link>
      <p className="text-small text-muted">
        {message(locale, 'agent.metro.tools.ratio', {
          enabled: summary.enabled,
          total,
        })}
      </p>
      <div className="flex flex-col gap-2">
        {topDomains.map(([domain, count]) => (
          <div
            key={domain}
            data-testid="domain-bar"
            className="flex items-center gap-2 text-micro"
          >
            <span className="w-1/4 min-w-0 shrink-0 truncate text-muted">
              {humaniseIdentifier(domain)}
            </span>
            <span className="h-1 flex-1 overflow-hidden rounded-full bg-sunken">
              <span
                className="block h-full bg-accent"
                style={{ width: `${String((count / max) * 100)}%` }}
              />
            </span>
            <span className="font-mono text-muted">{count}</span>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <span
          data-testid="side-effect-chip"
          data-role="success"
          className="rounded-full bg-success-bg px-2 py-1 text-micro text-success"
        >
          {message(locale, 'agent.metro.tools.read', { count: summary.read })}
        </span>
        <span
          data-testid="side-effect-chip"
          data-role="warning"
          className="rounded-full bg-warning-bg px-2 py-1 text-micro text-warning"
        >
          {message(locale, 'agent.metro.tools.writeReversible', {
            count: summary.writeReversible,
          })}
        </span>
        <span
          data-testid="side-effect-chip"
          data-role="danger"
          className="rounded-full bg-danger-bg px-2 py-1 text-micro text-danger"
        >
          {message(locale, 'agent.metro.tools.destructive', {
            count: summary.destructive,
          })}
        </span>
      </div>
    </div>
  );
}

/** The Autonomy card: the five-class ladder, no full "Why:" reasoning. */
function AutonomySummaryCard({
  locale,
  outlook,
  address,
}: {
  readonly locale: Locale;
  readonly outlook: PanelData<unknown>;
  readonly address: (wanted: AgentTab) => string;
}): ReactNode {
  const classes = list(dataOf(outlook), 'classes');
  return (
    <div
      data-testid="pipeline-summary-autonomy"
      className="flex flex-col gap-3 rounded-3 edge border-border bg-raised p-4"
    >
      <Link href={address('autonomy')}>{message(locale, 'agent.tab.autonomy')}</Link>
      <ul className="flex flex-col gap-2">
        {classes.map((entry) => (
          <li
            key={text(entry, 'risk_class')}
            data-testid="autonomy-summary-row"
            className="flex items-center gap-2 text-small"
          >
            <span className="min-w-0 flex-1 truncate">
              {humaniseIdentifier(text(entry, 'risk_class'))}
            </span>
            <span data-testid="autonomy-summary-decision" className="ml-auto">
              <Badge status={text(entry, 'decision')} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The Team Context card: prompt budget, or an honest empty state. */
function TeamSummaryCard({
  locale,
  context,
  address,
}: {
  readonly locale: Locale;
  readonly context: PanelData<unknown>;
  readonly address: (wanted: AgentTab) => string;
}): ReactNode {
  const tokensUsed = number(dataOf(context), 'tokens_used');
  const tokenBudget = number(dataOf(context), 'token_budget');
  const hasBudget = tokenBudget > 0;
  return (
    <div
      data-testid="pipeline-summary-team"
      className="flex flex-col gap-3 rounded-3 edge border-border bg-raised p-4"
    >
      <Link href={address('team')}>{message(locale, 'agent.tab.team')}</Link>
      {hasBudget ? (
        <p data-testid="team-budget" className="text-small">
          {message(locale, 'agent.metro.team.budget', {
            used: tokensUsed,
            budget: tokenBudget,
          })}
        </p>
      ) : (
        <div data-testid="team-empty" className="flex flex-col gap-2">
          <p className="text-small text-muted">
            {message(locale, 'agent.metro.team.empty')}
          </p>
        </div>
      )}
    </div>
  );
}

function PipelineSummaryCards({
  locale,
  capabilities,
  entries,
  outlook,
  context,
  address,
}: {
  readonly locale: Locale;
  readonly capabilities: PanelData<unknown>;
  readonly entries: PanelData<unknown>;
  readonly outlook: PanelData<unknown>;
  readonly context: PanelData<unknown>;
  readonly address: (wanted: AgentTab) => string;
}): ReactNode {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <ToolsSummaryCard
        locale={locale}
        capabilities={capabilities}
        entries={entries}
        address={address}
      />
      <AutonomySummaryCard locale={locale} outlook={outlook} address={address} />
      <TeamSummaryCard locale={locale} context={context} address={address} />
    </div>
  );
}

function TopologyTab({
  locale,
  pipeline,
  effective,
  fields,
  nodeId,
  writable,
  runs,
  summaryCapabilities,
  summaryEntries,
  summaryOutlook,
  summaryContext,
  address,
}: {
  readonly locale: Locale;
  readonly pipeline: PanelData<unknown>;
  readonly effective: PanelData<unknown>;
  readonly fields: PanelData<unknown>;
  readonly nodeId: string;
  readonly writable: boolean;
  readonly runs: PanelData<unknown>;
  readonly summaryCapabilities: PanelData<unknown>;
  readonly summaryEntries: PanelData<unknown>;
  readonly summaryOutlook: PanelData<unknown>;
  readonly summaryContext: PanelData<unknown>;
  readonly address: (wanted: AgentTab) => string;
}): ReactNode {
  const stages = list(dataOf(pipeline), 'stages');
  const roles = list(dataOf(pipeline), 'model_roles').map(String);
  const values = field(dataOf(effective), 'values');
  const specialists = subAgentsOf(values);
  const declared = list(dataOf(fields), 'fields');

  const ranks: readonly HierarchyRank[] = [
    {
      id: ORCHESTRATOR,
      label: message(locale, 'agent.rank.orchestrator'),
      nodes: [
        {
          id: ORCHESTRATOR,
          name: message(locale, 'agent.rank.orchestrator'),
          kind: ORCHESTRATOR,
          href: '#agent-stages',
          entryPoint: true,
        },
      ],
    },
    {
      id: STAGES,
      label: message(locale, 'agent.rank.stages'),
      // They run one after another — resolve, intake, plan, gather, diagnose,
      // deliver — and drawn as a plain row fanning out of the orchestrator,
      // nothing said which came first.
      sequence: true,
      nodes: stages.map((stage) => ({
        id: text(stage, 'name'),
        // The readable form in the box; the identifier keeps its place in the
        // list below, where a reader matching a log line will look for it.
        name: humaniseIdentifier(text(stage, 'name')),
        kind: STAGES,
        href: '#agent-stages',
      })),
    },
    {
      id: SPECIALISTS,
      label: message(locale, 'agent.rank.specialists'),
      nodes: specialists.map((specialist) => ({
        id: specialist.name,
        name: humaniseIdentifier(specialist.name),
        kind: SPECIALISTS,
        href: AGENT_ADVANCED_HREF,
        disabled: !specialist.enabled,
      })),
    },
  ];

  return (
    <>
      <PipelineMetro locale={locale} stages={stages} runs={runs} />
      <PipelineSummaryCards
        locale={locale}
        capabilities={summaryCapabilities}
        entries={summaryEntries}
        outlook={summaryOutlook}
        context={summaryContext}
        address={address}
      />
      <Panel
        title={message(locale, 'agent.stages.title')}
        state={stateOf(pipeline, stages.length === 0)}
        dependency={dependencyOf(pipeline)}
        labels={panelLabels(locale, message(locale, 'agent.stages.title'))}
        empty={{
          heading: message(locale, 'agent.empty.heading'),
          body: message(locale, 'agent.empty.body'),
          actionLabel: message(locale, 'agent.empty.action'),
          // The body says outright that nothing here is configuration, so
          // there is no owning page to send anyone to; the area's own
          // address is the only honest destination left.
          href: '/agent',
        }}
      >
        <div className="flex flex-col gap-4" id="agent-stages">
          <HierarchyGraph
            ranks={ranks}
            labels={{ title: message(locale, 'agent.graph.title') }}
          />
          <ol className="flex flex-col gap-3">
            {stages.map((stage) => (
              <li
                key={text(stage, 'name')}
                data-testid="agent-stage"
                data-stage={text(stage, 'name')}
                data-role={text(stage, 'model_role')}
                className="flex flex-col gap-1"
              >
                <span className="flex flex-wrap items-baseline gap-2">
                  <span className="text-strong">
                    {humaniseIdentifier(text(stage, 'name'))}
                  </span>
                  <span className="font-mono text-meta text-muted">
                    {text(stage, 'name')}
                  </span>
                  {text(stage, 'model_role') === '' ? (
                    <span className="text-meta text-muted">
                      {message(locale, 'agent.stage.noModel')}
                    </span>
                  ) : (
                    <span className="text-meta text-muted" data-testid="stage-role">
                      {message(locale, 'agent.stage.role', {
                        role: text(stage, 'model_role'),
                      })}
                    </span>
                  )}
                  {flag(stage, 'dispatches_subagents') ? (
                    <Badge status="active" />
                  ) : null}
                </span>
                {/* Capped at a reading measure. The page cap stops a screen at
                    1360px, which is right for a table and still half again too
                    wide for prose — the longest of these consults lines runs to
                    two hundred characters, and a reader loses the start of the
                    next line looking for it. */}
                <span className="text-meta text-muted max-w-prose">
                  {text(stage, 'summary')}
                </span>
                <span className="text-meta text-muted max-w-prose">
                  {message(locale, 'agent.stage.consults')}{' '}
                  {list(stage, 'consults').map(String).join('; ')}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </Panel>

      <Panel
        title={message(locale, 'agent.specialists.title')}
        state={stateOf(effective, specialists.length === 0)}
        dependency={dependencyOf(effective)}
        labels={panelLabels(locale, message(locale, 'agent.specialists.title'))}
        empty={{
          heading: message(locale, 'agent.specialists.empty.heading'),
          body: message(locale, 'agent.specialists.empty.body'),
          actionLabel: message(locale, 'agent.specialists.empty.action'),
          href: AGENT_ADVANCED_HREF,
        }}
      >
        <ul className="flex flex-col gap-3">
          {specialists.map((specialist) => (
            <li
              key={specialist.name}
              data-testid="agent-specialist"
              data-specialist={specialist.name}
              data-enabled={specialist.enabled ? 'true' : 'false'}
              className="flex flex-col gap-1"
            >
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-small text-strong">
                  {specialist.name}
                </span>
                <SpecialistStateChip locale={locale} enabled={specialist.enabled} />
                <span className="text-meta text-muted">
                  {message(locale, 'agent.stage.role', { role: specialist.modelRole })}
                </span>
              </span>
              <span className="text-meta text-muted">{specialist.description}</span>
              {specialist.capabilities.length === 0 ? null : (
                <span className="text-meta text-muted font-mono break-all">
                  {specialist.capabilities.join(', ')}
                </span>
              )}
            </li>
          ))}
        </ul>
        <p className="text-meta text-muted pt-3">
          {message(locale, 'agent.specialists.edit')}{' '}
          <Link href={AGENT_ADVANCED_HREF}>
            {message(locale, 'agent.specialists.editLink')}
          </Link>
        </p>
      </Panel>

      <ModelRolePanel
        locale={locale}
        roles={roles}
        fields={fields}
        declared={declared}
      />
      <BudgetPanel locale={locale} fields={fields} declared={declared} />
      <DocumentPanel locale={locale} effective={effective} values={values} />

      <AdvancedConfigSection
        title={message(locale, 'agent.advanced.title')}
        prefix={AGENT_ADVANCED_PREFIX}
        nodeId={nodeId}
        locale={locale}
        writable={writable}
        fields={AGENT_ADVANCED_FIELD_LIST.map(({ path, label }) => ({
          path,
          label: message(locale, label),
        }))}
        rawFields={dataOf(fields)}
      />
    </>
  );
}

/** One field of the configuration, as the fields catalogue describes it. */
function fieldAt(declared: readonly unknown[], path: string): unknown {
  return declared.find((entry) => text(entry, 'path') === path);
}

/** What a role resolves to, apart from anybody's choice. */
export interface RoleBinding {
  /** Whether some node actually chose this, as opposed to it falling through. */
  readonly bound: boolean;
  /** The provider running this role — bound, or the schema's own default. */
  readonly provider: string;
  readonly model: string;
  /** The node that bound it, empty when nothing did. */
  readonly provenance: string;
  /** Whether this row is running on the investigator's choice rather than its own. */
  readonly inherited: boolean;
}

/**
 * The role every other one follows when nobody bound it.
 *
 * Named here rather than passed in, because the rule is the deployment's and
 * not this screen's: `resolve_binding` gives an unnamed role the investigator's
 * provider, and this row has to say the same thing or stop being worth reading.
 */
const INVESTIGATOR_ROLE = 'investigator';

/**
 * What role `role` resolves to, and whether anybody chose it.
 *
 * A bound role reads its provider and model from the value a node set. An
 * unbound one follows the investigator, because that is what the deployment
 * does: `resolve_binding` (`core/llm/factory.py`) gives a role nobody named
 * the investigator's provider and model, and reaches the shipped default only
 * where nothing at all is configured.
 *
 * This row used to print the *schema's* default instead — `ConfigField.default`,
 * the value in a Pydantic field — and the difference was not cosmetic. A
 * deployment whose investigator was on Gemini, with the other seven roles left
 * alone as the console invites, had every one of those calls going to Gemini
 * while this panel said `anthropic / claude-sonnet-5`. Somebody read that
 * during an incident and spent an afternoon looking for a missing Anthropic
 * credential. A row that names a model no call will ever reach is worse than
 * a row that says nothing.
 *
 * The derivation is here rather than served because no endpoint answers "what
 * does this role actually resolve to" yet; the durable fix is the gateway
 * publishing its own resolution, and this mirrors the one rule that resolution
 * follows until it does. Still the only place on this screen a provider or a
 * model may be named, and still for the same reason: every row says where its
 * value came from — a node, the investigator, or the shipped default, never a
 * guess.
 */
export function roleBinding(declared: readonly unknown[], role: string): RoleBinding {
  const providerField = fieldAt(declared, `models.${role}.provider`);
  const modelField = fieldAt(declared, `models.${role}.model`);
  const bound = providerField !== undefined && text(providerField, 'provenance') !== '';
  if (bound) {
    return {
      bound: true,
      inherited: false,
      provider: text(providerField, 'value'),
      model: text(modelField, 'value'),
      provenance: text(providerField, 'provenance'),
    };
  }

  const leadProvider = fieldAt(declared, `models.${INVESTIGATOR_ROLE}.provider`);
  const leadBound =
    role !== INVESTIGATOR_ROLE &&
    leadProvider !== undefined &&
    text(leadProvider, 'provenance') !== '';
  if (leadBound) {
    return {
      bound: false,
      inherited: true,
      provider: text(leadProvider, 'value'),
      model: text(fieldAt(declared, `models.${INVESTIGATOR_ROLE}.model`), 'value'),
      provenance: '',
    };
  }

  return {
    bound: false,
    inherited: false,
    provider: text(providerField, 'default'),
    model: text(modelField, 'default'),
    provenance: '',
  };
}

function ModelRolePanel({
  locale,
  roles,
  fields,
  declared,
}: {
  readonly locale: Locale;
  readonly roles: readonly string[];
  readonly fields: PanelData<unknown>;
  readonly declared: readonly unknown[];
}): ReactNode {
  return (
    <Panel
      title={message(locale, 'agent.models.title')}
      state={stateOf(fields, roles.length === 0)}
      dependency={dependencyOf(fields)}
      labels={panelLabels(locale, message(locale, 'agent.models.title'))}
      empty={{
        heading: message(locale, 'agent.models.empty.heading'),
        body: message(locale, 'agent.models.empty.body'),
        actionLabel: message(locale, 'agent.models.empty.action'),
        href: '/settings/models-providers',
      }}
    >
      <p className="text-meta text-muted pb-3">
        {message(locale, 'agent.models.body')}
      </p>
      <ul className="flex flex-col gap-2">
        {roles.map((role) => {
          const binding = roleBinding(declared, role);
          return (
            <li
              key={role}
              data-testid="model-role"
              data-role={role}
              data-bound={binding.bound ? 'true' : 'false'}
              className="flex flex-wrap items-center gap-3 text-small"
            >
              <span className="font-mono min-w-0 truncate">{role}</span>
              {binding.provider === '' ? null : (
                <span className="text-meta" data-testid="model-role-binding">
                  {binding.provider} / {binding.model}
                </span>
              )}
              {binding.bound ? (
                <span
                  className="text-meta text-muted"
                  data-testid="model-role-provenance"
                >
                  {message(locale, 'agent.models.from', { node: binding.provenance })}
                </span>
              ) : (
                <span className="text-meta text-muted" data-testid="model-role-default">
                  {message(
                    locale,
                    binding.inherited
                      ? 'agent.models.inherited'
                      : 'agent.models.default',
                  )}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

/** The four budgets one run may spend, each with the ceiling the schema sets. */
const BUDGET_PATHS = [
  'agents.max_iterations',
  'agents.max_parallel_subagents',
  'agents.max_subagent_depth',
  'agents.tool_budget',
] as const;

/**
 * `record.name` as a finite number, or absent when it is not one.
 *
 * Distinct from `number()` in `../read`, which reads absence as zero — right
 * for a count, wrong here. A budget nobody customised carries `null` for its
 * value, a budget the schema does not bound carries `null` for its ceiling,
 * and `max_subagent_depth` may be customised *to* zero on purpose. Collapsing
 * all three into the digit `0` is exactly the defect this file exists to fix.
 */
function numeric(record: unknown, name: string): number | undefined {
  const found = field(record, name);
  return typeof found === 'number' && Number.isFinite(found) ? found : undefined;
}

/** What one budget is actually worth right now, apart from anybody's choice. */
export interface EffectiveBudget {
  /** Whether some node actually set this, as opposed to the default applying. */
  readonly customised: boolean;
  /** What a run may spend: the value a node set, or the schema's own default. */
  readonly value: number;
  /** The schema's ceiling, absent when the schema does not declare one. */
  readonly ceiling?: number;
}

/**
 * `budget` as it actually stands, never the placeholder zero.
 *
 * A field nobody customised carries `value: null`, and reading that as zero is
 * "zero iterations permitted" where the truth is "the shipped default applies,
 * whatever it is". The default is on the same field
 * (`ConfigField.default`, `platform/config_service/fields.py`), so the
 * effective number is always real: the value where a node bound one, the
 * default otherwise — the same `provenance` test `roleBinding` above uses for
 * a model role, because it is the same question asked of a different field.
 *
 * The ceiling is separate and may genuinely be absent: `agents.tool_budget`
 * declares a floor (`ge=1`) and no roof, so `ceiling` here is `undefined`
 * rather than `0` — a schema fact, not a missing one.
 */
export function effectiveBudget(budget: unknown): EffectiveBudget {
  const customised = text(budget, 'provenance') !== '';
  const value = customised ? number(budget, 'value') : number(budget, 'default');
  const ceiling = numeric(budget, 'maximum');
  return ceiling === undefined ? { customised, value } : { customised, value, ceiling };
}

/**
 * A budget path's own words, when this console has them yet.
 *
 * The shape `postures.ts` uses for a posture level this console may not have a
 * word for: a closed set of paths, filled in as the words arrive, falling back
 * to data rather than to the raw key in the meantime. The fallback here is the
 * schema's own label (`ConfigField.label`, served with the field already) —
 * "Max iterations" rather than "agents.max_iterations" — because that is real
 * data this screen already has, and a better fallback than the dotted path a
 * config author typed.
 *
 * The schema's own label is never a translation — it is Pydantic's field name
 * with the underscores turned to spaces, in English however this console is
 * being read. `BUDGET_PATHS` is a closed set of four, and every one of them
 * has words now, so the schema fallback below is reached only by a path a
 * future schema change adds before this map is updated to match it.
 */
const BUDGET_LABELS: Readonly<Record<string, MessageKey>> = {
  'agents.max_iterations': 'agent.budgets.maxIterations',
  'agents.max_parallel_subagents': 'agent.budgets.maxParallelSubagents',
  'agents.max_subagent_depth': 'agent.budgets.maxSubagentDepth',
  'agents.tool_budget': 'agent.budgets.toolBudget',
};

export function budgetLabel(locale: Locale, path: string, schemaLabel: string): string {
  const key = BUDGET_LABELS[path];
  if (key !== undefined) return message(locale, key);
  return schemaLabel === '' ? path : schemaLabel;
}

function BudgetPanel({
  locale,
  fields,
  declared,
}: {
  readonly locale: Locale;
  readonly fields: PanelData<unknown>;
  readonly declared: readonly unknown[];
}): ReactNode {
  const budgets = BUDGET_PATHS.map((path) => fieldAt(declared, path)).filter(
    (entry) => entry !== undefined,
  );
  return (
    <Panel
      title={message(locale, 'agent.budgets.title')}
      state={stateOf(fields, budgets.length === 0)}
      dependency={dependencyOf(fields)}
      labels={panelLabels(locale, message(locale, 'agent.budgets.title'))}
      empty={{
        heading: message(locale, 'agent.budgets.empty.heading'),
        body: message(locale, 'agent.budgets.empty.body'),
        actionLabel: message(locale, 'agent.budgets.empty.action'),
        href: AGENT_ADVANCED_HREF,
      }}
    >
      <ul className="flex flex-col gap-2">
        {budgets.map((budget) => {
          const path = text(budget, 'path');
          const { customised, value, ceiling } = effectiveBudget(budget);
          return (
            <li
              key={path}
              data-testid="agent-budget"
              data-path={path}
              data-customised={customised ? 'true' : 'false'}
              className="flex flex-wrap items-center gap-3 text-small"
            >
              <span className="min-w-0 truncate">
                {budgetLabel(locale, path, text(budget, 'label'))}
              </span>
              <span
                className="font-mono text-meta text-muted"
                data-testid="agent-budget-path"
              >
                {path}
              </span>
              <span className="tabular-nums" data-testid="agent-budget-value">
                {value}
              </span>
              {/* Absent, not zero: the schema genuinely does not bound every
                  budget, and a row with no ceiling states nothing rather than
                  a digit that would read as one. */}
              {ceiling === undefined ? null : (
                <span
                  className="text-meta text-muted"
                  data-testid="agent-budget-ceiling"
                >
                  {message(locale, 'agent.budgets.ceiling', {
                    ceiling: String(ceiling),
                  })}
                </span>
              )}
              {customised ? (
                <span
                  className="text-meta text-muted"
                  data-testid="agent-budget-provenance"
                >
                  {message(locale, 'agent.models.from', {
                    node: text(budget, 'provenance'),
                  })}
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
      <p className="text-meta text-muted pt-3">
        {message(locale, 'agent.budgets.body')}
      </p>
    </Panel>
  );
}

/**
 * The same topology as a document, beside the picture.
 *
 * One source, two views: this is the `agents` section of the very configuration
 * the graph above is drawn from, serialised here rather than re-fetched, so the
 * two cannot show different things. It is the only place on this screen where
 * a document is shown at all — everything else is rendered — and it is here
 * because some operators read a tree faster than they read a picture.
 *
 * **Never its own empty state.** A node with no `agents` section of its own is
 * the same condition the specialists panel above already explained, heading,
 * body and a way out included — showing that whole explanation a second time
 * in the same tab is the duplication a second view must not repeat. So this
 * panel is only ever `ready` or `error`: with nothing to show it renders the
 * document truthfully empty (`{"agents": {}}`), which is real content rather
 * than a claim about why there is none. The `empty` prop below is required by
 * `Panel`'s own type and is never reached.
 */
function DocumentPanel({
  locale,
  effective,
  values,
}: {
  readonly locale: Locale;
  readonly effective: PanelData<unknown>;
  readonly values: unknown;
}): ReactNode {
  const section = field(values, 'agents');
  const document = JSON.stringify({ agents: section ?? {} }, null, 2);
  // `{ "agents": {} }` is three lines of punctuation standing where a fact
  // belongs. The fact is that nothing on this screen has been overridden for
  // this node, which the panel can say in a sentence — and which the tables
  // above already say per row.
  const overridden =
    typeof section === 'object' && section !== null && Object.keys(section).length > 0;
  return (
    <Panel
      title={message(locale, 'agent.document.title')}
      state={stateOf(effective, false)}
      dependency={dependencyOf(effective)}
      labels={panelLabels(locale, message(locale, 'agent.document.title'))}
      empty={{
        heading: message(locale, 'agent.specialists.empty.heading'),
        body: message(locale, 'agent.specialists.empty.body'),
        actionLabel: message(locale, 'agent.specialists.empty.action'),
        href: AGENT_ADVANCED_HREF,
      }}
    >
      <div className="flex flex-col gap-2">
        {/* An empty object is three lines of punctuation standing where a fact
            belongs. The fact — that nothing has been overridden for this node —
            is said in words above it, and the document stays underneath for
            anyone who came to read the document. Not the panel's empty state:
            the specialists panel beside this one already carries that, and two
            empty states in a row explain the same nothing twice. */}
        {overridden ? null : (
          <p data-testid="agent-document-untouched" className="text-small text-muted">
            {message(locale, 'agent.document.untouched')}
          </p>
        )}
        <pre
          data-testid="agent-document"
          className="text-meta font-mono overflow-x-auto whitespace-pre"
        >
          {document}
        </pre>
      </div>
    </Panel>
  );
}

// --- What it can do --------------------------------------------------------------

/** `rows`, restricted to the tools this node has an opinion about and blocking, rendered once. */
function browsableTools(
  rows: readonly CapabilityRow[],
  locale: Locale,
  none: string,
): readonly BrowsableTool[] {
  return rows
    .filter((row) => row.kind === 'tool')
    .map((row) => {
      if (!row.known || row.available) {
        return {
          name: row.name,
          domain: row.domain,
          sideEffect: row.sideEffect,
          known: row.known,
          available: row.available,
          blockedText: '',
          blockedLinked: false,
        };
      }
      // Structured data leads: what the node actually declares this tool
      // needs, not a parse of the deployment's own free-text reason.
      const linked = row.requiredIntegrations.length > 0;
      const blockedText = linked
        ? message(locale, 'catalogue.blocked', {
            integration: row.requiredIntegrations.join(', '),
          })
        : row.reason === ''
          ? none
          : row.reason;
      return {
        name: row.name,
        domain: row.domain,
        sideEffect: row.sideEffect,
        known: row.known,
        available: row.available,
        blockedText,
        blockedLinked: linked,
      };
    });
}

function ToolsTab({
  locale,
  capabilities,
  entries,
  effective,
  fields,
  node,
  writable,
}: {
  readonly locale: Locale;
  readonly capabilities: PanelData<unknown>;
  readonly entries: PanelData<unknown>;
  readonly effective: PanelData<unknown>;
  readonly fields: PanelData<unknown>;
  readonly node: string;
  readonly writable: boolean;
}): ReactNode {
  const rows = capabilityRows(dataOf(capabilities), dataOf(entries));
  const tools = rows.filter((row) => row.kind === 'tool');
  const reads = tools.filter((row) => !row.writes);
  const writes = tools.filter((row) => row.writes);
  const servers = bridgedServers(field(dataOf(effective), 'values'));
  // One panel, two reads: a failed capability read must not render as "no tool
  // is blocked" beside a list that is itself empty for another reason.
  const source = capabilities.status === 'error' ? capabilities : entries;

  // The catalogue's own read half, absorbed whole: every tool and skill this
  // deployment declares, searchable, grouped by domain — beside the risk
  // grouping above rather than instead of it. The two answer different
  // questions ("what exists, and where do I find it" versus "what could
  // this actually do, and at what risk") and this screen is where both of
  // them now live.
  const none = message(locale, 'surface.none');
  const skills: readonly BrowsableSkill[] = rows
    .filter((row) => row.kind === 'skill')
    .map((row) => ({ name: row.name, summary: row.summary }));
  const enabledCount = tools.filter((row) => row.known && row.available).length;
  const count = message(locale, 'catalogue.count', {
    enabled: enabledCount,
    total: tools.length,
  });
  // Named for what it actually does: a blocked tool's own reason names the
  // integration that would unblock it, and connecting one has always been
  // the catalogue's job, never the retired editor's.
  const blockedIntegrationHref = '/integrations';

  return (
    <>
      <Panel
        title={message(locale, 'agent.tools.browse')}
        state={stateOf(source, tools.length === 0 && skills.length === 0)}
        dependency={dependencyOf(source)}
        labels={panelLabels(locale, message(locale, 'agent.tools.browse'))}
        empty={{
          heading: message(locale, 'agent.tools.empty.heading'),
          body: message(locale, 'agent.tools.empty.body'),
          actionLabel: message(locale, 'agent.tools.empty.action'),
          href: CAPABILITIES_ADVANCED_HREF,
        }}
      >
        <CapabilityBrowser
          tools={browsableTools(rows, locale, none)}
          skills={skills}
          count={count}
          configurationHref={blockedIntegrationHref}
          locale={locale}
          labels={{
            tableCaption: message(locale, 'agent.tools.browse'),
            search: message(locale, 'catalogue.search'),
            searchEmpty: message(locale, 'catalogue.search.empty'),
            domainsNav: message(locale, 'catalogue.domains.nav'),
            skillsHeading: message(locale, 'catalogue.skills'),
            columnName: message(locale, 'catalogue.column.name'),
            columnEffect: message(locale, 'catalogue.column.effect'),
            columnEnabled: message(locale, 'catalogue.column.enabled'),
            none,
            blockedAction: message(locale, 'catalogue.blocked.action'),
          }}
        />
      </Panel>

      <ToolGroup
        locale={locale}
        source={source}
        title={message(locale, 'agent.tools.reads')}
        body={message(locale, 'agent.tools.reads.body')}
        group="read"
        rows={reads}
      />
      <ToolGroup
        locale={locale}
        source={source}
        title={message(locale, 'agent.tools.writes')}
        body={message(locale, 'agent.tools.writes.body')}
        group="write"
        rows={writes}
      />

      <Panel
        title={message(locale, 'agent.bridged.title')}
        state={stateOf(effective, servers.length === 0)}
        dependency={dependencyOf(effective)}
        labels={panelLabels(locale, message(locale, 'agent.bridged.title'))}
        empty={{
          heading: message(locale, 'agent.bridged.empty.heading'),
          body: message(locale, 'agent.bridged.empty.body'),
          actionLabel: message(locale, 'agent.bridged.empty.action'),
          href: CAPABILITIES_ADVANCED_HREF,
        }}
      >
        <p className="text-meta text-muted pb-3">
          {message(locale, 'agent.bridged.body')}
        </p>
        <ul className="flex flex-col gap-2">
          {servers.map((server) => (
            <li
              key={server.name}
              data-testid="bridged-server"
              data-server={server.name}
              data-enabled={server.enabled ? 'true' : 'false'}
              className="flex flex-wrap items-center gap-3 text-small"
            >
              <span className="font-mono min-w-0 truncate">{server.name}</span>
              <BridgedServerStateChip locale={locale} enabled={server.enabled} />
              <span className="text-meta text-muted">{server.protocol}</span>
              <span className="text-meta text-muted break-all">{server.address}</span>
            </li>
          ))}
        </ul>
      </Panel>

      <div className="mt-5">
        <AdvancedConfigSection
          title={message(locale, 'agent.tools.advanced.title')}
          prefix={CAPABILITIES_ADVANCED_PREFIX}
          nodeId={node}
          locale={locale}
          writable={writable}
          fields={[]}
          rawFields={dataOf(fields)}
        />
      </div>
    </>
  );
}

function ToolGroup({
  locale,
  source,
  title,
  body,
  group,
  rows,
}: {
  readonly locale: Locale;
  readonly source: PanelData<unknown>;
  readonly title: string;
  readonly body: string;
  readonly group: 'read' | 'write';
  readonly rows: readonly CapabilityRow[];
}): ReactNode {
  const none = message(locale, 'surface.none');
  return (
    <Panel
      title={title}
      state={stateOf(source, rows.length === 0)}
      dependency={dependencyOf(source)}
      labels={panelLabels(locale, title)}
      empty={{
        heading: message(locale, 'agent.tools.empty.heading'),
        body: message(locale, 'agent.tools.empty.body'),
        actionLabel: message(locale, 'agent.tools.empty.action'),
        href: CAPABILITIES_ADVANCED_HREF,
      }}
    >
      <p className="text-meta text-muted pb-3">{body}</p>
      <ul className="flex flex-col gap-3" data-testid="tool-group" data-group={group}>
        {rows.map((row) => (
          <li
            key={row.name}
            data-testid="agent-tool"
            data-tool={row.name}
            data-group={group}
            data-available={!row.known ? 'unknown' : row.available ? 'true' : 'false'}
            data-origin={row.origin}
            className={
              row.known && !row.available
                ? 'flex flex-col gap-1 opacity-60'
                : 'flex flex-col gap-1'
            }
          >
            <span className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-small text-strong break-all">
                {row.name}
              </span>
              <Badge status={row.sideEffect} />
              {row.origin === '' ? null : (
                <span className="text-meta text-muted" data-testid="tool-origin">
                  {message(locale, 'agent.tools.origin', { server: row.origin })}
                </span>
              )}
            </span>
            <span className="text-meta text-muted">{row.summary}</span>
            {!row.known ? (
              <span className="text-meta text-muted">
                {message(locale, 'agent.tools.unknown')}
              </span>
            ) : row.available ? null : (
              <span className="text-meta text-muted" data-testid="tool-blocked">
                {message(locale, 'agent.tools.blocked', {
                  integration:
                    row.requiredIntegrations.join(', ') ||
                    (row.reason === '' ? none : row.reason),
                })}
              </span>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

// --- What it will do alone -------------------------------------------------------

function AutonomyTab({
  locale,
  outlook,
  replay,
  node,
  viewer,
}: {
  readonly locale: Locale;
  readonly outlook: PanelData<unknown>;
  readonly replay: PanelData<unknown>;
  readonly node: string;
  readonly viewer: SurfaceContext['viewer'];
}): ReactNode {
  const classes = list(dataOf(outlook), 'classes');
  const simulated = flag(dataOf(outlook), 'dry_run');
  const editable = may(viewer, WRITE);
  const recorded = list(dataOf(replay), 'actions');

  return (
    <>
      <Panel
        title={message(locale, 'agent.outlook.title')}
        state={stateOf(outlook, classes.length === 0)}
        dependency={dependencyOf(outlook)}
        labels={panelLabels(locale, message(locale, 'agent.outlook.title'))}
        empty={{
          heading: message(locale, 'agent.outlook.empty.heading'),
          body: message(locale, 'agent.outlook.empty.body'),
          actionLabel: message(locale, 'agent.outlook.empty.action'),
          href: '/autonomy',
        }}
      >
        <p className="text-meta text-muted pb-3">
          {message(locale, 'agent.outlook.body')}
        </p>
        {simulated ? (
          <p className="text-meta text-muted pb-3" data-testid="agent-dry-run">
            {message(locale, 'agent.outlook.dryRun')}
          </p>
        ) : null}
        <ul className="flex flex-col gap-3">
          {classes.map((entry) => (
            <li
              key={text(entry, 'risk_class')}
              data-testid="outlook-class"
              data-risk={text(entry, 'risk_class')}
              data-decision={text(entry, 'decision')}
              className="flex flex-col gap-1"
            >
              <span className="flex flex-wrap items-center gap-3">
                <RiskLadder
                  riskClass={text(entry, 'risk_class')}
                  label={humaniseIdentifier(text(entry, 'risk_class'))}
                />
                <Badge status={text(entry, 'decision')} />
                {text(entry, 'refused_by') === '' ? null : (
                  <span className="text-meta text-muted" data-testid="outlook-bound">
                    {message(locale, 'agent.outlook.bound', {
                      bound: text(entry, 'refused_by'),
                    })}
                  </span>
                )}
              </span>
              <span className="text-small max-w-prose" data-testid="outlook-sentence">
                {text(entry, 'sentence')}
              </span>
              {/* Labelled, because unlabelled it read as the sentence above it
                  said a second time in grey. It is not: the sentence says what
                  would happen, this says which rule decided — and the two
                  necessarily share most of their words, so only the label
                  tells a reader they are two different claims. It is the
                  decision's own audit text, complete on purpose, because it is
                  also read on a decision record with none of this around it. */}
              <span className="text-meta text-muted max-w-prose">
                <span className="text-strong">
                  {message(locale, 'agent.outlook.reason')}
                </span>{' '}
                {text(entry, 'reason')}
              </span>
            </li>
          ))}
        </ul>
        {/* Linked, never embedded: the editor is the autonomy area's, and a
          second copy of it here would be a second place a posture is changed. */}
        {editable ? (
          <p className="text-meta text-muted pt-4">
            <Link
              href={
                node === '' ? '/autonomy' : `/autonomy?node=${encodeURIComponent(node)}`
              }
            >
              {message(locale, 'agent.outlook.edit')}
            </Link>
          </p>
        ) : null}
      </Panel>

      {/* Beside the representative set rather than instead of it. The declared
          set answers on a deployment's first day, when there is no history and
          the decision to trust this is being made; this answers once there is,
          and the two disagreeing would itself be worth seeing. Absent entirely
          for a reader who may not ask — the route reads the decision history. */}
      {editable && recorded.length > 0 ? (
        <Panel
          title={message(locale, 'agent.replay.title')}
          state="ready"
          labels={panelLabels(locale, message(locale, 'agent.replay.title'))}
          empty={{
            heading: message(locale, 'agent.replay.empty.heading'),
            body: message(locale, 'agent.replay.empty.body'),
            actionLabel: message(locale, 'agent.outlook.empty.action'),
            href: '/autonomy',
          }}
        >
          <p className="text-meta text-muted pb-3">
            {message(locale, 'agent.replay.body')}
          </p>
          <ul className="flex flex-col gap-2">
            {recorded.map((entry) => (
              <li
                key={text(entry, 'action_id')}
                data-testid="replayed-action"
                data-capability={text(entry, 'capability')}
                className="flex flex-wrap items-center gap-3 text-small"
              >
                <span className="font-mono min-w-0 truncate">
                  {text(entry, 'capability')}
                </span>
                <span className="text-meta text-muted break-all">
                  {list(entry, 'subjects').map(String).join(', ')}
                </span>
                <ResolvedChip
                  role={statusPresentation(text(entry, 'after')).role}
                  shape={statusPresentation(text(entry, 'after')).shape}
                  label={postureName(locale, text(entry, 'after'))}
                  testId="replayed-action-level"
                />
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}
    </>
  );
}
