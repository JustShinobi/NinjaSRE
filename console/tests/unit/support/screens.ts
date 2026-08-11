import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import type { SearchParams } from '@/surfaces/context';

import Administration, {
  generateMetadata as administrationMeta,
} from '@/app/(shell)/administration/page';
import Agent, { generateMetadata as agentMeta } from '@/app/(shell)/agent/page';
import Approvals, {
  generateMetadata as approvalsMeta,
} from '@/app/(shell)/approvals/page';
import Audit, { generateMetadata as auditMeta } from '@/app/(shell)/audit/page';
import Autonomy, {
  generateMetadata as autonomyMeta,
} from '@/app/(shell)/autonomy/page';
import Catalogue, {
  generateMetadata as catalogueMeta,
} from '@/app/(shell)/catalogue/page';
import Configuration, {
  generateMetadata as configurationMeta,
} from '@/app/(shell)/configuration/page';
import Data, { generateMetadata as dataMeta } from '@/app/(shell)/data/page';
import Detectors, {
  generateMetadata as detectorsMeta,
} from '@/app/(shell)/detectors/page';
import FirstRun, {
  generateMetadata as firstRunMeta,
} from '@/app/(shell)/first-run/page';
import IncidentDetail from '@/app/(shell)/incidents/[incidentId]/page';
import Incidents, {
  generateMetadata as incidentsMeta,
} from '@/app/(shell)/incidents/page';
import Knowledge, {
  generateMetadata as knowledgeMeta,
} from '@/app/(shell)/knowledge/page';
import Memory, { generateMetadata as memoryMeta } from '@/app/(shell)/memory/page';
import Overview, { generateMetadata as overviewMeta } from '@/app/(shell)/page';
import Resources, {
  generateMetadata as resourcesMeta,
} from '@/app/(shell)/resources/page';
import RunDetail from '@/app/(shell)/runs/[runId]/page';
import Runs, { generateMetadata as runsMeta } from '@/app/(shell)/runs/page';
import Topology, {
  generateMetadata as topologyMeta,
} from '@/app/(shell)/topology/page';

/**
 * Every screen this console has, in one list.
 *
 * The cross-cutting proofs are all "for every screen …" — an empty state on each,
 * no write control on any for a role that lacks the permission, a filter state
 * that round-trips on each. Each of those is only worth as much as the list it
 * walks, so there is one list and the tests share it: a screen added tomorrow is
 * covered by proofs that already exist rather than by proofs somebody remembers
 * to extend.
 */

/** One screen: how to render it, and what it is called. */
export interface Screen {
  /** The area's identifier, matching the route manifest. */
  readonly id: string;
  readonly render: (props: {
    readonly searchParams: Promise<SearchParams>;
  }) => Promise<ReactNode>;
  /** Absent for a detail route, whose title is the subject rather than the area. */
  readonly metadata?: () => Promise<Metadata>;
}

/** Every area the manifest declares, whether or not the navigation is showing it. */
export const AREA_SCREENS: readonly Screen[] = [
  { id: 'dashboard', render: Overview, metadata: overviewMeta },
  { id: 'incidents', render: Incidents, metadata: incidentsMeta },
  { id: 'runs', render: Runs, metadata: runsMeta },
  { id: 'approvals', render: Approvals, metadata: approvalsMeta },
  { id: 'resources', render: Resources, metadata: resourcesMeta },
  { id: 'topology', render: Topology, metadata: topologyMeta },
  { id: 'detectors', render: Detectors, metadata: detectorsMeta },
  { id: 'memory', render: Memory, metadata: memoryMeta },
  { id: 'knowledge', render: Knowledge, metadata: knowledgeMeta },
  { id: 'catalogue', render: Catalogue, metadata: catalogueMeta },
  { id: 'autonomy', render: Autonomy, metadata: autonomyMeta },
  { id: 'configuration', render: Configuration, metadata: configurationMeta },
  { id: 'first-run', render: FirstRun, metadata: firstRunMeta },
  { id: 'agent', render: Agent, metadata: agentMeta },
  { id: 'administration', render: Administration, metadata: administrationMeta },
  { id: 'audit', render: Audit, metadata: auditMeta },
  { id: 'data', render: Data, metadata: dataMeta },
];

/** The two detail screens, which are reached from a list rather than the navigation. */
export const DETAIL_SCREENS: readonly Screen[] = [
  {
    id: 'runs',
    render: ({ searchParams }) =>
      RunDetail({ params: Promise.resolve({ runId: 'run-0001' }), searchParams }),
  },
  {
    // A run that has not finished, so every cross-cutting proof — the role
    // matrix, the empty states, the accessibility audit — also walks the live
    // half of the screen rather than only the replayed one.
    id: 'runs-live',
    render: ({ searchParams }) =>
      RunDetail({ params: Promise.resolve({ runId: 'run-0003' }), searchParams }),
  },
  {
    id: 'incidents',
    render: ({ searchParams }) =>
      IncidentDetail({
        params: Promise.resolve({ incidentId: 'INC-2026-0814' }),
        searchParams,
      }),
  },
];

/** Every screen there is. */
export const ALL_SCREENS: readonly Screen[] = [...AREA_SCREENS, ...DETAIL_SCREENS];
