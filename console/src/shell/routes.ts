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
  AlertCircleIcon,
  BookIcon,
  BrainIcon,
  CheckIcon,
  ClipboardIcon,
  DatabaseIcon,
  GridIcon,
  ListIcon,
  ServerIcon,
  SettingsIcon,
  ShieldIcon,
  SitemapIcon,
} from '@/design/icons';
import type { MessageKey } from '@/i18n/en';
import { may, type Viewer } from '@/session/viewer';

/** The four groups the sidebar draws, in the order it draws them. */
export const NAV_GROUPS = ['operate', 'estate', 'learn', 'govern'] as const;

export type NavGroup = (typeof NAV_GROUPS)[number];

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
    group: 'operate',
    label: 'nav.dashboard',
    title: 'page.dashboard.title',
    context: 'page.dashboard.context',
    permission: 'investigation.read',
    icon: GridIcon,
  },
  {
    id: 'incidents',
    path: '/incidents',
    group: 'operate',
    label: 'nav.incidents',
    title: 'page.incidents.title',
    context: 'page.incidents.context',
    permission: 'investigation.read',
    icon: AlertCircleIcon,
  },
  {
    id: 'runs',
    path: '/runs',
    group: 'operate',
    label: 'nav.runs',
    title: 'page.runs.title',
    context: 'page.runs.context',
    permission: 'investigation.read',
    icon: ListIcon,
  },
  {
    id: 'approvals',
    path: '/approvals',
    group: 'operate',
    label: 'nav.approvals',
    title: 'page.approvals.title',
    context: 'page.approvals.context',
    permission: 'approval.read',
    icon: CheckIcon,
  },
  {
    id: 'resources',
    path: '/resources',
    group: 'estate',
    label: 'nav.resources',
    title: 'page.resources.title',
    context: 'page.resources.context',
    permission: 'investigation.read',
    icon: ServerIcon,
  },
  {
    id: 'topology',
    path: '/topology',
    group: 'estate',
    label: 'nav.topology',
    title: 'page.topology.title',
    context: 'page.topology.context',
    permission: 'memory.read',
    icon: SitemapIcon,
  },
  {
    id: 'detectors',
    path: '/detectors',
    group: 'estate',
    label: 'nav.detectors',
    title: 'page.detectors.title',
    context: 'page.detectors.context',
    permission: 'config.read',
    icon: DatabaseIcon,
  },
  {
    id: 'memory',
    path: '/memory',
    group: 'learn',
    label: 'nav.memory',
    title: 'page.memory.title',
    context: 'page.memory.context',
    permission: 'memory.read',
    icon: BrainIcon,
  },
  {
    id: 'knowledge',
    path: '/knowledge',
    group: 'learn',
    label: 'nav.knowledge',
    title: 'page.knowledge.title',
    context: 'page.knowledge.context',
    permission: 'knowledge.read',
    icon: BookIcon,
  },
  {
    id: 'autonomy',
    path: '/autonomy',
    group: 'govern',
    label: 'nav.autonomy',
    title: 'page.autonomy.title',
    context: 'page.autonomy.context',
    permission: 'config.write',
    icon: ShieldIcon,
  },
  {
    id: 'configuration',
    path: '/configuration',
    group: 'govern',
    label: 'nav.configuration',
    title: 'page.configuration.title',
    context: 'page.configuration.context',
    permission: 'config.read',
    icon: SettingsIcon,
  },
  {
    id: 'audit',
    path: '/audit',
    group: 'govern',
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
 * The areas `viewer` may reach.
 *
 * Absence, not disabled state. A disabled entry still tells a reader that the
 * capability exists and still ships whatever sits behind it; an absent one tells
 * them nothing, which is what a permission boundary is for.
 */
export function visibleAreas(viewer: Viewer): readonly Area[] {
  return AREAS.filter((area) => may(viewer, area.permission));
}

/** One group of the navigation, with the areas of it this viewer may reach. */
export interface AreaGroup {
  readonly group: NavGroup;
  readonly areas: readonly Area[];
}

/** The navigation, grouped and in order, with empty groups dropped entirely. */
export function groupsFor(viewer: Viewer): readonly AreaGroup[] {
  const visible = visibleAreas(viewer);
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
