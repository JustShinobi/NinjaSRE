/**
 * Every area the console carries, in one list.
 *
 * This is the console's only answer to "what routes are there". The sign-in
 * guard walks it, the role matrix walks it, the deep-link test walks it, and the
 * palette's navigation commands are built from it. That is the design rather
 * than a convenience: a route added tomorrow is covered by tests that already
 * exist, because they enumerate this instead of a list somebody remembered to
 * extend.
 *
 * **The permission on each entry is the server's, never the screen's.** It is
 * the permission the gateway requires on the data the area reads, copied by
 * name. `tests/contract/console/test_console_shell.py` holds each one against
 * the gateway's own route table, so a permission that drifted fails in Python
 * rather than by showing somebody a page they cannot load.
 */

import type { ReactNode } from 'react';

import type { IconProps } from '@/design/icons';
import {
  ActivityIcon,
  AlertCircleIcon,
  BookIcon,
  BrainIcon,
  CheckIcon,
  ClipboardIcon,
  CompassIcon,
  DatabaseIcon,
  GridIcon,
  InboxIcon,
  ListIcon,
  LayersIcon,
  ServerIcon,
  SettingsIcon,
  ShieldIcon,
  SitemapIcon,
  UsersIcon,
} from '@/design/icons';
import type { MessageKey } from '@/i18n/en';
import { may, type Viewer } from '@/session/viewer';

/**
 * The three zones the sidebar draws, in the order it draws them.
 *
 * Separated by how often somebody opens them rather than by subject. The
 * previous four — Operate, Estate, Learn, Govern — described the system: they
 * put the page opened a hundred times a day and the page opened twice a year at
 * the same weight, and they gathered four unrelated screens under a heading
 * nobody thinks in. "Now" is first because it is where a person is standing
 * when something has broken.
 */
export const NAV_GROUPS = ['now', 'environment', 'settings'] as const;

export type NavGroup = (typeof NAV_GROUPS)[number];

/**
 * What the shell knows about the deployment when it decides what to draw.
 *
 * One field today, and the shape is the point: an area's presence is a question
 * about the *deployment*, so the answer has to be passed in rather than read
 * here. `routes.ts` makes no request.
 */
export interface AreaContext {
  /** Whether every first-run step is done. */
  readonly checklistComplete: boolean;
}

/**
 * What the navigation assumes when nothing has told it.
 *
 * Incomplete, so an area gated on the checklist is *shown*. The shell's own
 * read of the checklist degrades rather than throwing, and the failure this
 * default is chosen against is the one that matters: a deployment whose gateway
 * is half up losing the one route that finishes configuring it.
 */
const ASSUMED: AreaContext = { checklistComplete: false };

/** One area of the product: a route, a place in the navigation, and a gate. */
export interface Area {
  readonly id: string;
  readonly path: string;
  readonly group: NavGroup;
  readonly label: MessageKey;
  readonly title: MessageKey;
  readonly context: MessageKey;
  /** The permission the API requires on the data this area reads. */
  readonly permission: string;
  readonly icon: (props: IconProps) => ReactNode;
  /**
   * Whether the deployment's own state warrants showing this area at all.
   *
   * Absent for all but one: an area is normally present for everybody who holds
   * its permission, and a navigation that appeared and disappeared for reasons
   * a reader cannot name is a navigation they stop trusting. The exception is
   * the guided first run, which is a task rather than a place — it belongs in
   * front of somebody until it is done, and nowhere afterwards.
   */
  readonly visible?: (context: AreaContext) => boolean;
}

/**
 * The areas, grouped as the design groups them.
 *
 * Two of the permissions are worth reading twice. **Autonomy** takes
 * `config.write`: the screen exists to change what the deployment may do on its
 * own, and a reader who cannot change it already sees the current posture on the
 * overview and in the sidebar footer. **Audit** takes `audit.read`, which is an
 * administrator's permission — the record of who did what is not a thing every
 * signed-in person is entitled to.
 */
export const AREAS: readonly Area[] = [
  {
    id: 'dashboard',
    path: '/',
    group: 'now',
    label: 'nav.dashboard',
    title: 'page.dashboard.title',
    context: 'page.dashboard.context',
    permission: 'investigation.read',
    icon: GridIcon,
  },
  {
    id: 'incidents',
    path: '/incidents',
    group: 'now',
    label: 'nav.incidents',
    title: 'page.incidents.title',
    context: 'page.incidents.context',
    permission: 'investigation.read',
    icon: AlertCircleIcon,
  },
  {
    id: 'runs',
    path: '/runs',
    group: 'now',
    label: 'nav.runs',
    title: 'page.runs.title',
    context: 'page.runs.context',
    permission: 'investigation.read',
    icon: ListIcon,
  },
  {
    id: 'approvals',
    path: '/approvals',
    group: 'now',
    label: 'nav.approvals',
    title: 'page.approvals.title',
    context: 'page.approvals.context',
    permission: 'approval.read',
    icon: CheckIcon,
  },
  {
    id: 'resources',
    path: '/resources',
    group: 'environment',
    label: 'nav.resources',
    title: 'page.resources.title',
    context: 'page.resources.context',
    permission: 'investigation.read',
    icon: ServerIcon,
  },
  {
    id: 'topology',
    path: '/topology',
    group: 'environment',
    label: 'nav.topology',
    title: 'page.topology.title',
    context: 'page.topology.context',
    permission: 'memory.read',
    icon: SitemapIcon,
  },
  {
    id: 'detectors',
    path: '/detectors',
    group: 'environment',
    label: 'nav.detectors',
    title: 'page.detectors.title',
    context: 'page.detectors.context',
    permission: 'config.read',
    icon: DatabaseIcon,
  },
  {
    id: 'memory',
    path: '/memory',
    group: 'environment',
    label: 'nav.memory',
    title: 'page.memory.title',
    context: 'page.memory.context',
    permission: 'memory.read',
    icon: BrainIcon,
  },
  {
    id: 'knowledge',
    path: '/knowledge',
    group: 'environment',
    label: 'nav.knowledge',
    title: 'page.knowledge.title',
    context: 'page.knowledge.context',
    permission: 'knowledge.read',
    icon: BookIcon,
  },
  {
    // First in its zone, and the one entry with a `visible` rule: this is a
    // task rather than a place. It sits *inside* the shell — nothing redirects
    // to it, so an operator still deciding whether to keep this product can
    // look at the whole of it before filling in a form.
    id: 'first-run',
    path: '/first-run',
    group: 'settings',
    label: 'nav.firstRun',
    title: 'page.firstRun.title',
    context: 'page.firstRun.context',
    permission: 'config.read',
    icon: CompassIcon,
    visible: (context) => !context.checklistComplete,
  },
  {
    id: 'autonomy',
    path: '/autonomy',
    group: 'settings',
    label: 'nav.autonomy',
    title: 'page.autonomy.title',
    context: 'page.autonomy.context',
    permission: 'config.write',
    icon: ShieldIcon,
  },
  {
    id: 'configuration',
    path: '/configuration',
    group: 'settings',
    label: 'nav.configuration',
    title: 'page.configuration.title',
    context: 'page.configuration.context',
    permission: 'config.read',
    icon: SettingsIcon,
  },
  // Beside Configuration rather than inside it. What a team knows about its own
  // environment is prose somebody writes and rereads, not a field with a range —
  // and a panel that needs an editor, a budget meter and a preview of the
  // assembled prompt is a panel trying to be a screen.
  {
    id: 'team-context',
    path: '/team-context',
    group: 'settings',
    label: 'nav.teamContext',
    title: 'page.teamContext.title',
    context: 'page.teamContext.context',
    permission: 'config.read',
    icon: BookIcon,
  },
  // Its own item in Settings rather than a tab of Approvals, and the reason is
  // the question each answers. Approvals is "may the agent do this now"; this is
  // "should the deployment be different from tomorrow". They are read at
  // different times by, often, different people — and a queue that only exists
  // behind somebody else's screen is a queue that grows until it is discovered.
  {
    id: 'proposals',
    path: '/proposals',
    group: 'settings',
    label: 'nav.proposals',
    title: 'page.proposals.title',
    context: 'page.proposals.context',
    permission: 'approval.read',
    icon: InboxIcon,
  },
  {
    id: 'catalogue',
    path: '/catalogue',
    // Grouped with memory, knowledge and the estate rather than with settings:
    // what the deployment *can do* is part of what exists and what is known
    // about it, and it is read far more often than it is changed — which is the
    // axis the zones are cut on.
    group: 'environment',
    label: 'nav.catalogue',
    title: 'page.catalogue.title',
    context: 'page.catalogue.context',
    permission: 'investigation.read',
    icon: LayersIcon,
  },
  {
    // What the agent is, what it can do, and what it will do alone. In
    // settings because that is where the information architecture puts it: it
    // is what the platform *is* rather than what is happening. The permission
    // is the narrowest of the four reads it makes — the node's catalogue, its
    // fields, its effective configuration and its posture are all `config.read`
    // — following the same rule the catalogue route's row states.
    id: 'agent',
    path: '/agent',
    group: 'settings',
    label: 'nav.agent',
    title: 'page.agent.title',
    context: 'page.agent.context',
    permission: 'config.read',
    icon: ActivityIcon,
  },
  {
    id: 'administration',
    path: '/administration',
    group: 'settings',
    label: 'nav.administration',
    title: 'page.administration.title',
    context: 'page.administration.context',
    permission: 'identity.read',
    icon: UsersIcon,
  },
  // Its own place rather than a corner of configuration, and the reason is a
  // different question: the configuration tree answers "what value applies
  // here", and this answers "where did this come from and where did it go".
  // Mixing the two is how an operator ends up opening five screens to find out
  // why an alert never became an investigation.
  //
  // The comment is outside the object literal deliberately: the contract suite
  // parses this file with a regular expression that reads `id` immediately
  // after the brace, so a comment inside makes an area invisible to the check
  // that every declared route is walked.
  {
    id: 'data',
    path: '/data',
    group: 'settings',
    label: 'nav.data',
    title: 'page.data.title',
    context: 'page.data.context',
    permission: 'config.read',
    icon: DatabaseIcon,
  },
  {
    id: 'audit',
    path: '/audit',
    group: 'settings',
    label: 'nav.audit',
    title: 'page.audit.title',
    context: 'page.audit.context',
    permission: 'audit.read',
    icon: ClipboardIcon,
  },
];

/** Kept so the manifest is a closed list rather than a suggestion. */
const BY_ID: ReadonlyMap<string, Area> = new Map(AREAS.map((area) => [area.id, area]));

/** The area called `id`, or an error naming what was asked for. */
export function areaFor(id: string): Area {
  const area = BY_ID.get(id);
  if (area === undefined) {
    throw new Error(`${id} is not an area of this console`);
  }
  return area;
}

/**
 * The area a path names, ignoring a trailing slash.
 *
 * `undefined` rather than a throw: an address a person typed is not a defect,
 * and what it deserves is the not-found page inside the shell.
 */
export function areaByPath(path: string): Area | undefined {
  const trimmed = path.length > 1 && path.endsWith('/') ? path.slice(0, -1) : path;
  return AREAS.find((area) => area.path === trimmed);
}

/**
 * The areas `viewer` may reach, in the deployment's current state.
 *
 * Absence, not disabled state. A disabled entry still tells a reader that the
 * capability exists and still ships whatever sits behind it; an absent one tells
 * them nothing, which is what a permission boundary is for.
 *
 * Two questions, and they are asked in this order for a reason. Permission
 * first, because it is the one that must never be got wrong; the deployment's
 * own rule second, because it is about relevance rather than entitlement and an
 * area it hides is still served at its address.
 */
export function visibleAreas(
  viewer: Viewer,
  context: AreaContext = ASSUMED,
): readonly Area[] {
  return AREAS.filter(
    (area) => may(viewer, area.permission) && (area.visible?.(context) ?? true),
  );
}

/** One group of the navigation, with the areas of it this viewer may reach. */
export interface AreaGroup {
  readonly group: NavGroup;
  readonly areas: readonly Area[];
}

/** The navigation, grouped and in order, with empty groups dropped entirely. */
export function groupsFor(
  viewer: Viewer,
  context: AreaContext = ASSUMED,
): readonly AreaGroup[] {
  const visible = visibleAreas(viewer, context);
  return NAV_GROUPS.map((group) => ({
    group,
    areas: visible.filter((area) => area.group === group),
  })).filter((entry) => entry.areas.length > 0);
}

/**
 * One step of a page header's trail.
 *
 * A discriminated union rather than a string and a flag, so that a crumb which
 * says it is translatable is *typed* as a catalogue key. The alternative is an
 * assertion at the point of rendering, and an assertion is exactly where a key
 * that is not a key gets through.
 */
export type TrailCrumb =
  | {
      readonly translate: true;
      readonly label: MessageKey;
      /** Absent for the crumb that is the current page, which never links to itself. */
      readonly href?: string;
    }
  | {
      readonly translate: false;
      /** Text the catalogue cannot hold — a run identifier, a resource name. */
      readonly label: string;
      readonly href?: string;
    };

/**
 * Where a page sits: the area, then anything nested under it.
 *
 * A top-level area returns one crumb, and the header renders no breadcrumb for a
 * trail of one — a breadcrumb that says only where you already are is furniture.
 * The crumbs a detail page adds carry their own text, because a run identifier is
 * not a thing any catalogue can hold.
 */
export function trailFor(
  area: Area,
  nested: readonly { readonly label: string; readonly href?: string }[] = [],
): readonly TrailCrumb[] {
  if (nested.length === 0) {
    return [{ label: area.title, translate: true }];
  }
  const trail: TrailCrumb[] = [{ label: area.title, translate: true, href: area.path }];
  nested.forEach((crumb, index) => {
    const last = index === nested.length - 1;
    trail.push(
      last || crumb.href === undefined
        ? { label: crumb.label, translate: false }
        : { label: crumb.label, translate: false, href: crumb.href },
    );
  });
  return trail;
}
