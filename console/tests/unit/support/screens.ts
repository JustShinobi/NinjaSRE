import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { areaMetadata, settingsPageMetadata } from '@/shell/area';
import { SignalsScreen } from '@/surfaces/screens/signals';
import { AuditLogScreen } from '@/surfaces/settings/audit';
import { AutonomyScreen } from '@/surfaces/settings/autonomy';
import { MachineTokensScreen } from '@/surfaces/settings/machine-tokens';
import { MembersScreen } from '@/surfaces/settings/members';
import { SingleSignOnScreen } from '@/surfaces/settings/sso';
import { surfaceContext, type SearchParams } from '@/surfaces/context';

import Agent, { generateMetadata as agentMeta } from '@/app/(shell)/agent/page';
import Configuration, {
  generateMetadata as configurationMeta,
} from '@/app/(shell)/configuration/page';
import Decisions, {
  generateMetadata as decisionsMeta,
} from '@/app/(shell)/decisions/page';
import FirstRun, {
  generateMetadata as firstRunMeta,
} from '@/app/(shell)/first-run/page';
import IncidentDetail from '@/app/(shell)/incidents/[incidentId]/page';
import Incidents, {
  generateMetadata as incidentsMeta,
} from '@/app/(shell)/incidents/page';
import Integrations, {
  generateMetadata as integrationsMeta,
} from '@/app/(shell)/integrations/page';
import IntegrationDetail from '@/app/(shell)/integrations/[name]/page';
import NotCovered, {
  generateMetadata as notCoveredMeta,
} from '@/app/(shell)/integrations/not-covered/page';
import Knowledge, {
  generateMetadata as knowledgeMeta,
} from '@/app/(shell)/knowledge/page';
import Overview, { generateMetadata as overviewMeta } from '@/app/(shell)/page';
import Resources, {
  generateMetadata as resourcesMeta,
} from '@/app/(shell)/resources/page';
import RunDetail from '@/app/(shell)/runs/[runId]/page';
import Runs, { generateMetadata as runsMeta } from '@/app/(shell)/runs/page';
import AlertIntake, {
  generateMetadata as alertIntakeMeta,
} from '@/app/(shell)/settings/alert-intake/page';
import SchedulesDestinations, {
  generateMetadata as schedulesDestinationsMeta,
} from '@/app/(shell)/settings/schedules-destinations/page';

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

/**
 * `signals`, `autonomy`, `administration`, rendered directly under their own
 * retired area id.
 *
 * The hybrid navigation retired all three from their own address — that
 * address now redirects to a Settings page instead of rendering
 * (`tests/unit/shell/route-files.test.tsx` covers the redirect). `signals` is
 * unchanged, reused whole at its new Settings address; `autonomy` was rebuilt
 * as the Settings page's own screen (`@/surfaces/settings/autonomy`), which
 * absorbed rule/freeze/budget creation and the guardrails domain. Both old
 * ids keep pointing at their successor so every cross-cutting proof this list
 * feeds — about the *screen*, not the address it used to answer at — keeps
 * covering it.
 *
 * `administration` desmembered into four pages rather than one, so its old
 * id cannot stand for all of them the way `autonomy`'s can for one — it now
 * points at Members & roles, the page nearest its old default (a bare
 * `/administration` already redirected to `/settings/members-roles`). The
 * other three successors are covered under their own `settings-*` id below,
 * each with its own permission, rather than falsely under the retired one.
 */
async function renderSignals({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return SignalsScreen(await surfaceContext(await searchParams));
}

async function renderAutonomy({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return AutonomyScreen(await surfaceContext(await searchParams));
}

async function renderMembers({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return MembersScreen(await surfaceContext(await searchParams));
}

async function renderSingleSignOn({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return SingleSignOnScreen(await surfaceContext(await searchParams));
}

async function renderMachineTokens({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return MachineTokensScreen(await surfaceContext(await searchParams));
}

async function renderAuditLog({
  searchParams,
}: {
  readonly searchParams: Promise<SearchParams>;
}): Promise<ReactNode> {
  return AuditLogScreen(await surfaceContext(await searchParams));
}

/**
 * Every area the manifest declares and still renders its own screen, whether
 * or not the navigation is showing it — modulo `settings`, the one entry with
 * no screen at all: it only ever redirects, to whichever Settings page is
 * first for the viewer, so there is nothing here for a cross-cutting proof to
 * render.
 *
 * `integrations-not-covered` stays on this list — it makes the same
 * `panelRead('/v1/integrations', …)` every other data screen does, so an
 * outage takes its panel down exactly the way `outage.test.tsx` proves for
 * every area — but its content, `known_gaps`, is a catalogue fact the product
 * declares rather than something a deployment configures, so it never becomes
 * *empty* the way a deployment's own data can, and it has no write control to
 * check. `tests/unit/surfaces/screens.test.tsx` and
 * `tests/unit/surfaces/role-matrix.test.tsx` each name it in their own local
 * exclusion, with the same reasoning stated where it is used.
 *
 * `first-run` stays, and renders normally under every scenario this suite
 * serves except the one whose checklist is complete
 * (`serveScenario('populated')`, in `tests/unit/shell/route-files.test.tsx`,
 * which excludes it from its own render loop rather than from this list).
 */
export const AREA_SCREENS: readonly Screen[] = [
  { id: 'dashboard', render: Overview, metadata: overviewMeta },
  { id: 'incidents', render: Incidents, metadata: incidentsMeta },
  { id: 'runs', render: Runs, metadata: runsMeta },
  { id: 'decisions', render: Decisions, metadata: decisionsMeta },
  { id: 'resources', render: Resources, metadata: resourcesMeta },
  { id: 'knowledge', render: Knowledge, metadata: knowledgeMeta },
  { id: 'agent', render: Agent, metadata: agentMeta },
  { id: 'first-run', render: FirstRun, metadata: firstRunMeta },
  { id: 'integrations', render: Integrations, metadata: integrationsMeta },
  {
    id: 'integrations-not-covered',
    render: NotCovered,
    metadata: notCoveredMeta,
  },
  {
    id: 'signals',
    render: renderSignals,
    metadata: () => areaMetadata('signals'),
  },
  {
    id: 'autonomy',
    render: renderAutonomy,
    // The Settings page's own metadata, not the retired area's: the real
    // route file (`app/(shell)/settings/autonomy-guardrails/page.tsx`) calls
    // `settingsPageMetadata`, and this entry has to match what it actually
    // produces.
    metadata: () => settingsPageMetadata('settings-autonomy-guardrails'),
  },
  { id: 'configuration', render: Configuration, metadata: configurationMeta },
  {
    id: 'administration',
    render: renderMembers,
    metadata: () => areaMetadata('administration'),
  },
  {
    id: 'settings-members-roles',
    render: renderMembers,
    metadata: () => settingsPageMetadata('settings-members-roles'),
  },
  {
    id: 'settings-single-sign-on',
    render: renderSingleSignOn,
    metadata: () => settingsPageMetadata('settings-single-sign-on'),
  },
  {
    id: 'settings-machine-tokens',
    render: renderMachineTokens,
    metadata: () => settingsPageMetadata('settings-machine-tokens'),
  },
  {
    id: 'settings-audit-log',
    render: renderAuditLog,
    metadata: () => settingsPageMetadata('settings-audit-log'),
  },
  {
    id: 'settings-alert-intake',
    render: AlertIntake,
    metadata: alertIntakeMeta,
  },
  {
    id: 'settings-schedules-destinations',
    render: SchedulesDestinations,
    metadata: schedulesDestinationsMeta,
  },
];

/** The detail screens, which are reached from a list rather than the navigation. */
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
    // A connected integration, so the panel's credential form, its state chip
    // and the "already established" content all render — the same reasoning
    // `runs-live` follows for a run still in flight.
    id: 'integrations',
    render: ({ searchParams }) =>
      IntegrationDetail({ params: Promise.resolve({ name: 'chat' }), searchParams }),
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
