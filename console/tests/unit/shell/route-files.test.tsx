import { render, screen } from '@testing-library/react';
import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { message } from '@/i18n/messages';
import { AREAS, areaFor } from '@/shell/routes';
import { SESSION_COOKIE } from '@/session/cookies';
import type { SearchParams } from '@/surfaces/context';

import { serveScenario } from '../support/dataset';

import Approvals, {
  generateMetadata as approvalsMeta,
} from '@/app/(shell)/approvals/page';
import Agent, { generateMetadata as agentMeta } from '@/app/(shell)/agent/page';
import Administration, {
  generateMetadata as administrationMeta,
} from '@/app/(shell)/administration/page';
import Audit, { generateMetadata as auditMeta } from '@/app/(shell)/audit/page';
import Catalogue, {
  generateMetadata as catalogueMeta,
} from '@/app/(shell)/catalogue/page';
import Autonomy, {
  generateMetadata as autonomyMeta,
} from '@/app/(shell)/autonomy/page';
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
import Runs, { generateMetadata as runsMeta } from '@/app/(shell)/runs/page';
import TeamContext, {
  generateMetadata as teamContextMeta,
} from '@/app/(shell)/team-context/page';
import Topology, {
  generateMetadata as topologyMeta,
} from '@/app/(shell)/topology/page';

/**
 * Every route file, opened directly.
 *
 * A deep link is a cold render of one route file, so this imports each of the
 * twelve and renders it — no shell, no navigation, nothing warmed up. The point
 * is the completeness check underneath: the list here is compared against the
 * manifest, so an area added without a route file fails, and a route file added
 * without an entry in the manifest fails too.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      // The credential a signed-in request carries. The pages resolve the viewer
      // themselves rather than trusting the layout to have done it, because a
      // client-side transition fetches the page segment alone.
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

interface RouteFile {
  readonly id: string;
  readonly page: (props: {
    readonly searchParams: Promise<SearchParams>;
  }) => Promise<ReactNode>;
  readonly metadata: () => Promise<Metadata>;
}

const ROUTE_FILES: readonly RouteFile[] = [
  { id: 'dashboard', page: Overview, metadata: overviewMeta },
  { id: 'incidents', page: Incidents, metadata: incidentsMeta },
  { id: 'runs', page: Runs, metadata: runsMeta },
  { id: 'approvals', page: Approvals, metadata: approvalsMeta },
  { id: 'resources', page: Resources, metadata: resourcesMeta },
  { id: 'topology', page: Topology, metadata: topologyMeta },
  { id: 'detectors', page: Detectors, metadata: detectorsMeta },
  { id: 'memory', page: Memory, metadata: memoryMeta },
  { id: 'knowledge', page: Knowledge, metadata: knowledgeMeta },
  { id: 'autonomy', page: Autonomy, metadata: autonomyMeta },
  { id: 'configuration', page: Configuration, metadata: configurationMeta },
  { id: 'team-context', page: TeamContext, metadata: teamContextMeta },
  { id: 'first-run', page: FirstRun, metadata: firstRunMeta },
  { id: 'catalogue', page: Catalogue, metadata: catalogueMeta },
  { id: 'agent', page: Agent, metadata: agentMeta },
  { id: 'administration', page: Administration, metadata: administrationMeta },
  { id: 'audit', page: Audit, metadata: auditMeta },
  { id: 'data', page: Data, metadata: dataMeta },
];

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
  serveScenario('populated');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the route files and the manifest', () => {
  it('are the same set, so neither can gain an entry alone', () => {
    expect(ROUTE_FILES.map((file) => file.id).sort()).toEqual(
      AREAS.map((area) => area.id).sort(),
    );
  });
});

describe('a deep link to every route', () => {
  it.each(ROUTE_FILES.map((file) => [file.id, file] as const))(
    '%s renders cold, with its own title',
    async (id, file) => {
      // Awaited, because a route file is an async server component: what a cold
      // request renders is what the page resolves to, not the page itself.
      render(await file.page({ searchParams: Promise.resolve({}) }));

      expect(screen.getByTestId('page-header')).toHaveAttribute('data-area', id);
      expect(await file.metadata()).toMatchObject({
        title: `${message('en', areaFor(id).title)} · HAL9000`,
      });
    },
  );
});
