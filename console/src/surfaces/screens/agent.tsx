import type { ReactNode } from 'react';

import NextLink from 'next/link';

import { Badge, Link, TabLinks } from '@/components';
import { Input } from '@/components/form';
import {
  BridgedServerStateChip,
  CapabilityAvailabilityChip,
  CHIP_SHAPE,
  ResolvedChip,
  SideEffectChip,
  SpecialistStateChip,
} from '@/components/status';
import { cx } from '@/design/cx';
import {
  ActivityIcon,
  AlertCircleIcon,
  ArrowRightIcon,
  CheckIcon,
  ClipboardIcon,
  SearchIcon,
  SettingsIcon,
} from '@/design/icons';
import { statusPresentation, type Shape } from '@/design/status';
import type { SemanticRole } from '@/design/tokens';
import { humaniseIdentifier } from '@/i18n/format';
import { isMessageKey, message, type Locale, type MessageKey } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { loadGuardian } from '@/shell/load';
import { areaFor } from '@/shell/routes';
import {
  AdvancedConfigSection,
  advancedConfigSectionId,
} from '../advanced-config-section';
import {
  bridgedServers,
  capabilityRows,
  readsOnly,
  type CapabilityRow,
} from '../capability-rows';
import type { SurfaceContext } from '../context';
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
  furthestCurrentStage,
  STAGE_TREATMENT_CLASSES,
  stageRegime,
  stageTreatment,
  toolSummary,
  type StageRegime,
} from './agent-pipeline-metro';
import { placedTree } from '../tree';
import {
  hrefFor,
  readViewState,
  resolveNode,
  withFilter,
  type FilterName,
  type ViewState,
} from '../url-state';
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

export const AGENT_FILTERS: readonly FilterName[] = [
  'node',
  'tab',
  'domain',
  'effect',
  'q',
  'all',
];

/** The tab the address names, and the first one when it names nothing known. */
export function tabFrom(value: string): AgentTab {
  return AGENT_TABS.find((tab) => tab === value) ?? AGENT_TABS[0];
}

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

/**
 * The name the first run gives the root it creates when nobody names one —
 * `DEFAULT_ORGANISATION_NAME`, `config/constants/first_run.py`. The one node
 * name that is the product's own word rather than an operator's, which is
 * what makes translating it honest where translating a chosen name would not
 * be.
 */
const DEFAULT_ORGANISATION_NAME = 'Default organisation';

/** `name`, in the viewer's language when it is the product's own default. */
function crumbName(locale: Locale, name: string): string {
  return name === DEFAULT_ORGANISATION_NAME
    ? message(locale, 'organisation.defaultName')
    : name;
}

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

  // The same datum the sidebar's own footer reads — "Guardião ativo · só
  // propõe" — so the tab's policy chip and the frame can never disagree
  // about what the deployment currently permits.
  const guardian = tab === 'autonomy' ? await loadGuardian(credential) : null;

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
            : [
                {
                  label: crumbName(
                    locale,
                    placed.find((each) => each.id === node)?.name ?? node,
                  ),
                },
              ]
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
            state={state}
          />
        ) : null}
        {tab === 'autonomy' ? (
          <AutonomyTab
            locale={locale}
            outlook={outlook}
            replay={replay}
            posture={guardian?.posture ?? 'propose'}
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

/** A stage's own words, when this console has them; its identifier, humanised, otherwise. */
function stageWord(locale: Locale, kind: 'name' | 'copy', stage: string): string {
  const key = `agent.metro.${kind}.${stage}`;
  if (isMessageKey(key)) return message(locale, key);
  return kind === 'name' ? humaniseIdentifier(stage) : '';
}

/** The mono line under a station: its ordinal, then its regime — or "running now". */
function regimeLine(
  locale: Locale,
  ordinal: number,
  regime: StageRegime,
  running: boolean,
): string {
  const label = running
    ? message(locale, 'agent.metro.runningNow')
    : regime.kind === 'model'
      ? message(locale, 'agent.metro.regime.model', { role: regime.role })
      : regime.kind === 'deterministic'
        ? message(locale, 'agent.metro.regime.deterministic')
        : message(locale, 'agent.metro.regime.none');
  return `${String(ordinal)} · ${label}`;
}

/**
 * The six-node line the Pipeline tab opens with — one look at what a run
 * does, and the one place the per-stage prose lives: each station is a
 * disclosure, and opening it shows that stage's description, what it
 * consults, and the model role it runs under. The section that used to
 * repeat all of that below the band is gone; this is where it went.
 */
function PipelineMetro({
  locale,
  pipeline,
  stages,
  runs,
}: {
  readonly locale: Locale;
  readonly pipeline: PanelData<unknown>;
  readonly stages: readonly unknown[];
  readonly runs: PanelData<unknown>;
}): ReactNode {
  const running =
    runs.status === 'ready'
      ? list(dataOf(runs), 'runs').filter((run) => text(run, 'status') === 'running')
      : [];
  const inFlight = running.length;
  const stageNames = stages.map((stage) => text(stage, 'name'));
  // The listing's own `last_completed_stage` names where each run in flight
  // is; the furthest one along is the station the band lights and the point
  // the rail's fill reaches. With nothing in flight the band rests.
  const currentStageName = furthestCurrentStage(
    stageNames,
    running.map((run) => text(run, 'last_completed_stage')),
  );
  const currentAt =
    currentStageName === undefined ? -1 : stageNames.indexOf(currentStageName);
  const fillPercent =
    stageNames.length < 2 || currentAt < 0
      ? 0
      : (currentAt / (stageNames.length - 1)) * 100;
  return (
    <Panel
      title={message(locale, 'agent.metro.title')}
      state={stateOf(pipeline, stages.length === 0)}
      dependency={dependencyOf(pipeline)}
      labels={panelLabels(locale, message(locale, 'agent.metro.title'))}
      empty={{
        heading: message(locale, 'agent.empty.heading'),
        body: message(locale, 'agent.empty.body'),
        actionLabel: message(locale, 'agent.empty.action'),
        // The body says outright that nothing here is configuration, so
        // there is no owning page to send anyone to; the area's own
        // address is the only honest destination left.
        href: '/agent',
      }}
      action={
        inFlight === 0 ? undefined : (
          <span
            data-testid="pipeline-in-flight"
            className="flex items-center gap-2 rounded-full bg-accent-bg px-3 py-1 text-small text-accent"
          >
            <span aria-hidden="true" className="icon-inline rotate-45 bg-accent" />
            {message(locale, 'agent.metro.inFlight', { count: inFlight })}
          </span>
        )
      }
    >
      <p className="text-meta text-muted pb-4">
        {message(locale, 'agent.metro.subtitle')}
      </p>
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
          <span className="relative flex h-0 w-full items-center edge border-border">
            {/* The filled part of the line: how far the furthest run in
                flight has walked. `motion-overlay` gives the width a
                declared transition, so a stage boundary slides rather than
                jumps — and the global reduced-motion rule zeroes it. */}
            <span
              data-testid="pipeline-metro-rail-fill"
              className="motion-overlay absolute inset-y-0 left-0 my-auto h-1 rounded-full bg-accent"
              style={{ width: `${String(fillPercent)}%` }}
            />
          </span>
        </div>
        {stages.map((stage, index) => {
          const name = text(stage, 'name');
          const Icon = STAGE_ICON[name] ?? SettingsIcon;
          const regime = stageRegime(name, text(stage, 'model_role'));
          const treatment = stageTreatment(stageNames, name, currentStageName);
          return (
            <details
              key={name}
              data-testid="pipeline-metro-node"
              data-stage={name}
              data-role={text(stage, 'model_role')}
              className="min-w-0"
            >
              <summary
                className="flex cursor-pointer select-none list-none flex-col items-center gap-2 text-center [&::-webkit-details-marker]:hidden"
                data-testid="pipeline-metro-summary"
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
                  data-running={treatment === 'running' ? 'true' : undefined}
                  className={cx(
                    'font-mono text-micro',
                    treatment === 'running' ? 'text-accent' : 'text-muted',
                  )}
                >
                  {regimeLine(locale, index + 1, regime, treatment === 'running')}
                </span>
                <span
                  data-testid="pipeline-metro-name"
                  className="text-small font-medium"
                >
                  {stageWord(locale, 'name', name)}
                </span>
                <span
                  data-testid="pipeline-metro-copy"
                  className="text-micro text-muted"
                >
                  {stageWord(locale, 'copy', name)}
                </span>
              </summary>
              <div
                data-testid="pipeline-metro-detail"
                className="mt-2 flex flex-col gap-1 rounded-2 bg-sunken p-3 text-left"
              >
                {text(stage, 'summary') === '' ? null : (
                  <span className="text-meta text-muted">{text(stage, 'summary')}</span>
                )}
                {list(stage, 'consults').length === 0 ? null : (
                  <span className="text-meta text-muted">
                    {message(locale, 'agent.stage.consults')}{' '}
                    {list(stage, 'consults').map(String).join('; ')}
                  </span>
                )}
                <span className="text-meta text-muted" data-testid="stage-role">
                  {text(stage, 'model_role') === ''
                    ? message(locale, 'agent.stage.noModel')
                    : message(locale, 'agent.stage.role', {
                        role: text(stage, 'model_role'),
                      })}
                </span>
              </div>
            </details>
          );
        })}
      </div>
    </Panel>
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
      <p className="mt-auto text-small">
        <Link href={address('tools')}>
          {message(locale, 'agent.metro.tools.catalogue')}
        </Link>
      </p>
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
            className="flex items-center gap-2 rounded-2 edge border-border bg-sunken px-2 py-1 text-small"
          >
            <span className="min-w-0 shrink-0 truncate">
              {humaniseIdentifier(text(entry, 'risk_class'))}
            </span>
            {/* The board's thin connecting line: what makes five rows read
                as one ladder rather than five labels and five chips. */}
            <span aria-hidden="true" className="h-px min-w-4 flex-1 bg-border" />
            <span data-testid="autonomy-summary-decision" className="shrink-0">
              <Badge status={text(entry, 'decision')} locale={locale} />
            </span>
          </li>
        ))}
      </ul>
      <p className="text-micro text-muted">
        {message(locale, 'agent.metro.autonomy.footer')}
      </p>
      <p className="mt-auto text-small">
        <Link href="/settings/autonomy-guardrails">
          {message(locale, 'agent.metro.autonomy.adjust')}
        </Link>
      </p>
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
        <div className="flex flex-col gap-2">
          <p data-testid="team-budget" className="text-small">
            {message(locale, 'agent.metro.team.budget', {
              used: tokensUsed,
              budget: tokenBudget,
            })}
          </p>
          {/* The budget as a bar, not a sentence alone — the board's own
              treatment, and what makes "how full" readable at a glance. */}
          <span
            data-testid="team-budget-bar"
            className="flex h-2 overflow-hidden rounded-full edge border-border bg-sunken"
          >
            <span
              className="block h-full bg-accent"
              style={{
                width: `${String(Math.min(100, (tokensUsed / tokenBudget) * 100))}%`,
              }}
            />
          </span>
          <p className="text-micro text-muted">
            {message(locale, 'agent.metro.team.note')}
          </p>
        </div>
      ) : (
        <div data-testid="team-empty" className="flex flex-col gap-2">
          <p className="text-small text-muted">
            {message(locale, 'agent.metro.team.empty')}
          </p>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <span className="rounded-full edge border-border bg-sunken px-2 py-1 text-micro text-muted">
          {message(locale, 'agent.metro.team.investigator')}
        </span>
        <span className="rounded-full edge border-border bg-sunken px-2 py-1 text-micro text-muted">
          {message(locale, 'agent.metro.team.subagent')}
        </span>
      </div>
      <p className="mt-auto text-small">
        <Link href={address('team')}>{message(locale, 'agent.metro.team.write')}</Link>
      </p>
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

  return (
    <>
      <PipelineMetro locale={locale} pipeline={pipeline} stages={stages} runs={runs} />
      <PipelineSummaryCards
        locale={locale}
        capabilities={summaryCapabilities}
        entries={summaryEntries}
        outlook={summaryOutlook}
        context={summaryContext}
        address={address}
      />
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
      {(() => {
        const bindings = roles.map(
          (role) => [role, roleBinding(declared, role)] as const,
        );
        // Every role that made no choice of its own says the identical
        // sentence — seven copies of "follows the investigator" told a
        // reader nothing seven times. The ones with something of their own
        // to say stay as rows; the followers collapse to one line, with
        // the full list a disclosure away.
        const own = bindings.filter(([, binding]) => !binding.inherited);
        const followers = bindings.filter(([, binding]) => binding.inherited);
        const row = ([role, binding]: (typeof bindings)[number]): ReactNode => (
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
                  binding.inherited ? 'agent.models.inherited' : 'agent.models.default',
                )}
              </span>
            )}
          </li>
        );
        return (
          <div className="flex flex-col gap-2">
            <ul className="flex flex-col gap-2">{own.map(row)}</ul>
            {followers.length === 0 ? null : (
              <details data-testid="model-roles-followers">
                <summary className="cursor-pointer select-none text-small text-muted">
                  {message(locale, 'agent.models.followSummary', {
                    count: followers.length,
                  })}
                </summary>
                <ul className="flex flex-col gap-2 pt-2">{followers.map(row)}</ul>
              </details>
            )}
          </div>
        );
      })()}
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
        {/* Closed by default: the document is the second view of a topology
            the rest of the tab already renders, kept for the operators who
            read a tree faster than a picture — a disclosure away rather than
            a page-length block everyone else scrolls past. */}
        <details data-testid="agent-document-details">
          <summary className="cursor-pointer select-none text-small text-muted">
            {message(locale, 'agent.document.show')}
          </summary>
          <pre
            data-testid="agent-document"
            className="text-meta font-mono overflow-x-auto whitespace-pre pt-2"
          >
            {document}
          </pre>
        </details>
      </div>
    </Panel>
  );
}

// --- What it can do --------------------------------------------------------------

/**
 * The board's own set of domains, worded — the catalogue's closed vocabulary,
 * not the open case §11 protects. A domain outside it (an anonymised dataset,
 * a bridged server's own grouping) falls back to its humanised identifier.
 */
const TOOL_DOMAIN_LABEL: Readonly<Record<string, MessageKey>> = {
  remediation: 'agent.tools.domain.remediation',
  cloud_control_plane: 'agent.tools.domain.cloud_control_plane',
  skills: 'agent.tools.domain.skills',
  methodology: 'agent.tools.domain.methodology',
  logstore: 'agent.tools.domain.logstore',
  communication: 'agent.tools.domain.communication',
  metrics: 'agent.tools.domain.metrics',
  incident: 'agent.tools.domain.incident',
  cicd: 'agent.tools.domain.cicd',
  vcs: 'agent.tools.domain.vcs',
  database: 'agent.tools.domain.database',
  tracing: 'agent.tools.domain.tracing',
  changes: 'agent.tools.domain.changes',
  model_provider: 'agent.tools.domain.model_provider',
  observability: 'agent.tools.domain.observability',
  topology: 'agent.tools.domain.topology',
  estate: 'agent.tools.domain.estate',
  other: 'agent.tools.domain.other',
};

function domainLabel(locale: Locale, slug: string): string {
  const key = TOOL_DOMAIN_LABEL[slug];
  return key === undefined ? humaniseIdentifier(slug) : message(locale, key);
}

/** The rail's bucket for `row`: its own domain, skills, or the leftover bucket. */
function domainOf(row: CapabilityRow): string {
  if (row.kind === 'skill') return 'skills';
  return row.domain === '' ? 'other' : row.domain;
}

/** The four effect filters the band offers, beyond "all". */
const EFFECT_FILTERS = [
  'read',
  'write_reversible',
  'write_irreversible',
  'destructive',
] as const;

const EFFECT_LABEL: Readonly<Record<(typeof EFFECT_FILTERS)[number], MessageKey>> = {
  read: 'agent.tools.effect.read',
  write_reversible: 'agent.tools.effect.write_reversible',
  write_irreversible: 'agent.tools.effect.write_irreversible',
  destructive: 'agent.tools.effect.destructive',
};

/** Whether `row` falls under `effect` — "read" folds the sensitive read in. */
function matchesEffect(row: CapabilityRow, effect: string): boolean {
  if (effect === '') return true;
  if (effect === 'read') return readsOnly(row.sideEffect);
  return row.sideEffect === effect;
}

/** How many capability cards show before "see all" is the way to the rest. */
const CAPABILITY_CARD_LIMIT = 8;

/** One capability, as the board's card: face always, prose one disclosure away. */
function CapabilityCard({
  locale,
  row,
}: {
  readonly locale: Locale;
  readonly row: CapabilityRow;
}): ReactNode {
  const destructive = row.sideEffect === 'destructive';
  const off = row.known && !row.available;
  return (
    <details
      data-testid="capability-card"
      data-capability={row.name}
      data-available={!row.known ? 'unknown' : row.available ? 'true' : 'false'}
      className={cx(
        'rounded-3 edge bg-raised p-3',
        destructive ? 'border-danger' : 'border-border',
        off && 'opacity-60',
      )}
    >
      <summary className="flex cursor-pointer select-none list-none flex-wrap items-center gap-3 [&::-webkit-details-marker]:hidden">
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="font-mono text-small text-strong break-all">{row.name}</span>
          {row.kind === 'skill' ? null : (
            <span className="self-start">
              <SideEffectChip locale={locale} level={row.sideEffect} />
            </span>
          )}
        </span>
        {row.known ? (
          <CapabilityAvailabilityChip locale={locale} available={row.available} />
        ) : null}
      </summary>
      {/* The prose that used to repeat in two page-length sections lives
          here, on the card it describes. */}
      <div className="flex flex-col gap-1 pt-2" data-testid="capability-card-detail">
        {row.summary === '' ? null : (
          <span className="text-meta text-muted">{row.summary}</span>
        )}
        {row.origin === '' ? null : (
          <span className="text-meta text-muted" data-testid="tool-origin">
            {message(locale, 'agent.tools.origin', { server: row.origin })}
          </span>
        )}
        {!row.known ? (
          <span className="text-meta text-muted">
            {message(locale, 'agent.tools.unknown')}
          </span>
        ) : row.available ? null : row.requiredIntegrations.length > 0 ? (
          // Structured data leads: what the node actually declares this tool
          // needs, not a parse of the deployment's own free-text reason —
          // and the integration is the thing somebody can go and connect.
          <span className="text-meta text-muted" data-testid="tool-blocked">
            {message(locale, 'catalogue.blocked', {
              integration: row.requiredIntegrations.join(', '),
            })}{' '}
            <Link href="/integrations">
              {message(locale, 'catalogue.blocked.action')}
            </Link>
          </span>
        ) : (
          <span className="text-meta text-muted" data-testid="tool-blocked">
            {row.reason === '' ? message(locale, 'surface.none') : row.reason}
          </span>
        )}
      </div>
    </details>
  );
}

function ToolsTab({
  locale,
  capabilities,
  entries,
  effective,
  fields,
  node,
  writable,
  state,
}: {
  readonly locale: Locale;
  readonly capabilities: PanelData<unknown>;
  readonly entries: PanelData<unknown>;
  readonly effective: PanelData<unknown>;
  readonly fields: PanelData<unknown>;
  readonly node: string;
  readonly writable: boolean;
  readonly state: ViewState;
}): ReactNode {
  const rows = capabilityRows(dataOf(capabilities), dataOf(entries));
  const tools = rows.filter((row) => row.kind === 'tool');
  const servers = bridgedServers(field(dataOf(effective), 'values'));
  // One panel, two reads: a failed capability read must not render as "no tool
  // is blocked" beside a list that is itself empty for another reason.
  const source = capabilities.status === 'error' ? capabilities : entries;

  // Selection lives in the address, the way the tabs already do — a filtered
  // view is a link somebody can send, never component state.
  const linkFor = (changes: readonly (readonly [string, string])[]): string => {
    let next = state;
    for (const [name, value] of changes) next = withFilter(next, name, value);
    return hrefFor('/agent', next, AGENT_FILTERS);
  };
  const effect = state.filters.effect ?? '';
  const query = (state.filters.q ?? '').trim().toLowerCase();

  // The rail: every bucket with its full count, most capabilities first, so
  // the list reads as the shape of what this deployment can do.
  const byDomain = new Map<string, CapabilityRow[]>();
  for (const row of rows) {
    const bucket = domainOf(row);
    byDomain.set(bucket, [...(byDomain.get(bucket) ?? []), row]);
  }
  const rail = [...byDomain.entries()].sort(
    ([, left], [, right]) => right.length - left.length,
  );
  const selectedDomain = state.filters.domain ?? rail[0]?.[0] ?? '';
  const domainRows = byDomain.get(selectedDomain) ?? [];
  const filtered = domainRows.filter(
    (row) =>
      matchesEffect(row, effect) &&
      (query === '' ||
        row.name.toLowerCase().includes(query) ||
        row.domain.toLowerCase().includes(query) ||
        row.summary.toLowerCase().includes(query)),
  );
  const showAll = state.filters.all === '1';
  const shown = showAll ? filtered : filtered.slice(0, CAPABILITY_CARD_LIMIT);

  const enabledCount = tools.filter((row) => row.known && row.available).length;
  const destructiveCount = tools.filter(
    (row) => row.sideEffect === 'destructive',
  ).length;
  const domainEnabled = domainRows.filter((row) => row.known && row.available).length;
  const ratioPercent = tools.length === 0 ? 0 : (enabledCount / tools.length) * 100;

  return (
    <>
      <Panel
        title={message(locale, 'agent.tools.browse')}
        state={stateOf(source, rows.length === 0)}
        dependency={dependencyOf(source)}
        labels={panelLabels(locale, message(locale, 'agent.tools.browse'))}
        empty={{
          heading: message(locale, 'agent.tools.empty.heading'),
          body: message(locale, 'agent.tools.empty.body'),
          actionLabel: message(locale, 'agent.tools.empty.action'),
          href: CAPABILITIES_ADVANCED_HREF,
        }}
      >
        {/* The band: how much of the catalogue is on, the search, and the
            effect filters — the one row that frames everything below it. */}
        <div
          data-testid="tools-band"
          className="flex flex-wrap items-center gap-4 pb-4"
        >
          <div className="flex min-w-0 flex-col gap-1">
            <span className="text-small" data-testid="tools-ratio">
              {message(locale, 'catalogue.count', {
                enabled: enabledCount,
                total: tools.length,
              })}
            </span>
            <span className="flex h-1 w-column-measure overflow-hidden rounded-full bg-sunken">
              <span
                className="block h-full bg-accent"
                style={{ width: `${String(ratioPercent)}%` }}
              />
            </span>
          </div>
          <form action="/agent" method="get" className="flex min-w-0 items-center">
            <input type="hidden" name="tab" value="tools" />
            {node === '' ? null : <input type="hidden" name="node" value={node} />}
            {selectedDomain === '' ? null : (
              <input type="hidden" name="domain" value={selectedDomain} />
            )}
            {effect === '' ? null : (
              <input type="hidden" name="effect" value={effect} />
            )}
            <Input
              type="search"
              name="q"
              label={message(locale, 'catalogue.search')}
              defaultValue={state.filters.q ?? ''}
            />
          </form>
          <nav
            aria-label={message(locale, 'catalogue.column.effect')}
            className="ml-auto flex flex-wrap items-center gap-2"
          >
            <NextLink
              prefetch={false}
              data-testid="tools-effect-chip"
              data-effect=""
              aria-current={effect === '' ? 'true' : undefined}
              className={cx(
                CHIP_SHAPE,
                effect === ''
                  ? 'bg-accent-bg text-accent edge border-accent'
                  : 'bg-sunken text-muted edge border-border',
              )}
              href={linkFor([
                ['effect', ''],
                ['all', ''],
              ])}
            >
              {message(locale, 'agent.tools.effect.all')}
            </NextLink>
            {EFFECT_FILTERS.map((each) => (
              <NextLink
                key={each}
                prefetch={false}
                data-testid="tools-effect-chip"
                data-effect={each}
                aria-current={effect === each ? 'true' : undefined}
                className={cx(
                  CHIP_SHAPE,
                  effect === each
                    ? 'bg-accent-bg text-accent edge border-accent'
                    : 'bg-sunken text-muted edge border-border',
                )}
                href={linkFor([
                  ['effect', each],
                  ['all', ''],
                ])}
              >
                {message(locale, EFFECT_LABEL[each])}
                {each === 'destructive' ? (
                  <span className="font-mono text-micro">{destructiveCount}</span>
                ) : null}
              </NextLink>
            ))}
          </nav>
        </div>

        {/* Master-detail: the domain rail, then the selected domain's cards. */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
          <nav
            aria-label={message(locale, 'catalogue.domains.nav')}
            data-testid="tools-domain-rail"
            className="flex flex-col gap-1 self-start rounded-3 edge border-border bg-raised p-2 lg:col-span-1"
          >
            {rail.map(([slug, bucket]) => (
              <NextLink
                key={slug}
                prefetch={false}
                data-testid="tools-domain"
                data-domain={slug}
                aria-current={slug === selectedDomain ? 'true' : undefined}
                className={cx(
                  'flex items-center gap-2 rounded-2 px-2 py-1 text-small',
                  slug === selectedDomain
                    ? 'bg-accent-bg text-accent'
                    : 'text-muted hover:bg-hover motion-hover',
                )}
                href={linkFor([
                  ['domain', slug],
                  ['all', ''],
                ])}
              >
                <span className="min-w-0 flex-1 truncate">
                  {domainLabel(locale, slug)}
                </span>
                <span className="font-mono text-micro">{bucket.length}</span>
              </NextLink>
            ))}
          </nav>

          <div className="flex min-w-0 flex-col gap-3 lg:col-span-3">
            <div className="flex flex-wrap items-baseline gap-3">
              <span className="text-strong" data-testid="tools-domain-title">
                {domainLabel(locale, selectedDomain)}
              </span>
              <span className="text-meta text-muted">
                {message(locale, 'agent.tools.domainMeta', {
                  count: domainRows.length,
                  enabled: domainEnabled,
                })}
              </span>
            </div>
            {filtered.length === 0 ? (
              <p className="text-small text-muted" data-testid="tools-none-match">
                {message(locale, 'catalogue.search.empty')}
              </p>
            ) : (
              <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-2">
                {shown.map((row) => (
                  <CapabilityCard key={row.name} locale={locale} row={row} />
                ))}
              </div>
            )}
            {filtered.length <= shown.length ? null : (
              <p className="text-meta text-muted" data-testid="tools-showing">
                {message(locale, 'agent.tools.showing', {
                  shown: shown.length,
                  total: filtered.length,
                })}{' '}
                <Link href={linkFor([['all', '1']])}>
                  {message(locale, 'agent.tools.showAll', {
                    domain: domainLabel(locale, selectedDomain),
                  })}
                </Link>
              </p>
            )}
            <p className="text-meta text-muted edge border-border border-x-0 border-b-0 pt-3">
              {message(locale, 'agent.tools.footer')}
            </p>
          </div>
        </div>
      </Panel>

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

// --- What it will do alone -------------------------------------------------------

/** The words and dress of one rung of the board's ladder. */
const AUTONOMY_CLASS_CHIP: Readonly<
  Record<
    string,
    { readonly label: MessageKey; readonly role: SemanticRole; readonly shape: Shape }
  >
> = {
  trivial: {
    label: 'agent.autonomy.class.trivial',
    role: 'neutral',
    shape: 'hollow-circle',
  },
  low: { label: 'agent.autonomy.class.low', role: 'neutral', shape: 'filled-circle' },
  moderate: {
    label: 'agent.autonomy.class.moderate',
    role: 'warning',
    shape: 'rotated-square',
  },
  high: { label: 'agent.autonomy.class.high', role: 'warning', shape: 'triangle' },
  critical: { label: 'agent.autonomy.class.critical', role: 'danger', shape: 'square' },
};

/** `sentence` split at its first full stop: the row's short line, and the rest. */
export function firstSentence(sentence: string): readonly [string, string] {
  const match = /^(.*?[.!?])\s+(\S.*)$/su.exec(sentence.trim());
  if (match === null) return [sentence.trim(), ''];
  return [match[1] ?? '', match[2] ?? ''];
}

function AutonomyTab({
  locale,
  outlook,
  replay,
  posture,
  node,
  viewer,
}: {
  readonly locale: Locale;
  readonly outlook: PanelData<unknown>;
  readonly replay: PanelData<unknown>;
  /** What the deployment currently permits, the same datum the sidebar's footer reads. */
  readonly posture: string;
  readonly node: string;
  readonly viewer: SurfaceContext['viewer'];
}): ReactNode {
  const classes = list(dataOf(outlook), 'classes');
  const simulated = flag(dataOf(outlook), 'dry_run');
  const editable = may(viewer, WRITE);
  const recorded = list(dataOf(replay), 'actions');
  const ruleHref = '/settings/autonomy-guardrails';

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
        action={
          <span
            data-testid="autonomy-policy-chip"
            className="flex items-center gap-2 rounded-full bg-accent-bg px-3 py-1 text-small text-accent"
          >
            <span
              aria-hidden="true"
              className="pulse-live inline-block size-2 rounded-full bg-accent"
            >
              <span className="pulse-live-ring" />
            </span>
            {message(locale, 'agent.autonomy.policyChip', {
              posture: postureName(locale, posture),
            })}
          </span>
        }
      >
        <p className="text-meta text-muted pb-3">
          {message(locale, 'agent.outlook.body')}
        </p>
        {simulated ? (
          <p className="text-meta text-muted pb-3" data-testid="agent-dry-run">
            {message(locale, 'agent.outlook.dryRun')}
          </p>
        ) : null}
        <ul className="flex flex-col" data-testid="autonomy-ladder">
          {classes.map((entry) => {
            const riskClass = text(entry, 'risk_class');
            const chip = AUTONOMY_CLASS_CHIP[riskClass];
            const [lead, rest] = firstSentence(text(entry, 'sentence'));
            return (
              <li
                key={riskClass}
                data-testid="outlook-class"
                data-risk={riskClass}
                data-decision={text(entry, 'decision')}
                className="edge border-border border-x-0 border-t-0 last:border-b-0"
              >
                <details>
                  <summary className="flex cursor-pointer select-none list-none flex-wrap items-center gap-3 py-3 [&::-webkit-details-marker]:hidden">
                    {chip === undefined ? (
                      <Badge status={riskClass} locale={locale} />
                    ) : (
                      <ResolvedChip
                        role={chip.role}
                        shape={chip.shape}
                        label={message(locale, chip.label)}
                        testId="autonomy-class-chip"
                      />
                    )}
                    <span
                      className="min-w-0 flex-1 text-small"
                      data-testid="outlook-sentence"
                    >
                      {lead}
                    </span>
                    <ArrowRightIcon
                      aria-hidden="true"
                      className="icon-inline text-muted"
                    />
                    <span data-testid="outlook-decision">
                      <Badge status={text(entry, 'decision')} locale={locale} />
                    </span>
                    <span className="text-micro text-muted">
                      {message(locale, 'agent.autonomy.nobodyAlone')}
                    </span>
                  </summary>
                  {/* The "why" lives here, once per row and one disclosure
                      away, instead of repeating below all five rows. It is
                      the decision's own audit text, complete on purpose,
                      because it is also read on a decision record with none
                      of this around it. */}
                  <div
                    data-testid="outlook-why"
                    className="mb-3 flex flex-col gap-2 edge border-accent border-y-0 border-r-0 pl-3"
                  >
                    {rest === '' ? null : (
                      <span className="text-small max-w-prose">{rest}</span>
                    )}
                    {text(entry, 'refused_by') === '' ? null : (
                      <span
                        className="text-meta text-muted"
                        data-testid="outlook-bound"
                      >
                        {message(locale, 'agent.outlook.bound', {
                          bound: text(entry, 'refused_by'),
                        })}
                      </span>
                    )}
                    <span className="text-meta text-muted max-w-prose">
                      <span className="text-strong">
                        {message(locale, 'agent.outlook.reason')}
                      </span>{' '}
                      {text(entry, 'reason')}
                    </span>
                    <span className="text-meta">
                      <Link href={ruleHref}>
                        {message(locale, 'agent.autonomy.seeRule')}
                      </Link>
                    </span>
                  </div>
                </details>
              </li>
            );
          })}
        </ul>
        {/* The board's closing card: what changing the policy means, and that
            doing so is itself a recorded decision. Linked, never embedded —
            the editor is the settings area's, and a second copy of it here
            would be a second place a posture is changed. */}
        <div
          data-testid="autonomy-change-card"
          className="mt-4 flex flex-wrap items-center gap-4 rounded-3 edge border-border bg-sunken p-4"
        >
          <span
            aria-hidden="true"
            className="flex size-7 shrink-0 items-center justify-center rounded-2 bg-accent-bg text-accent edge border-accent"
          >
            <SettingsIcon className="icon-head" />
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-strong">
              {message(locale, 'agent.autonomy.change.title')}
            </span>
            <span className="text-meta text-muted max-w-prose">
              {message(locale, 'agent.autonomy.change.body')}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <span className="text-micro text-muted">
              {message(locale, 'agent.autonomy.change.note')}
            </span>
            {editable ? (
              <Link
                href={
                  node === ''
                    ? '/autonomy'
                    : `/autonomy?node=${encodeURIComponent(node)}`
                }
              >
                {message(locale, 'agent.metro.autonomy.adjust')}
              </Link>
            ) : null}
          </div>
        </div>
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
