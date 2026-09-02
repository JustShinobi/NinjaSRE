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
  BookIcon,
  ClockIcon,
  CompassIcon,
  DatabaseIcon,
  GridIcon,
  LayersIcon,
  SearchIcon,
  ServerIcon,
  SettingsIcon,
  ShieldIcon,
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
 * Eighteen areas became thirteen (twelve once the guided first run is done)
 * in one pass, on the reasoning that the previous grouping — one screen per
 * subsystem — followed the software's own architecture rather than the six
 * questions an operator actually asks. Six fusions did the shrinking, each a
 * tabbed screen rather than a lost feature: **Decisions** absorbs Approvals
 * and Proposed changes (the same "may the agent act" / "should the
 * deployment be different" split, now sitting beside each other instead of
 * behind separate menu entries); **Knowledge** absorbs Memory and Topology
 * (learned, documented, observed — three angles on one question, "what does
 * the agent know about this environment"); **The agent** absorbs the
 * Catalogue's read surface and Team context (reading what the agent is
 * stays here; writing stays on the screens built for it); **Integrations**
 * is what the Catalogue's write surface becomes, on its own address;
 * **Signals** absorbs Detectors and Data (what enters continuous
 * observation and what leaves it, which were two screens in two different
 * zones for no reason a reader could see); and **Administration** absorbs
 * Audit as a tab, because both answer "who did what" from an
 * administrator's own permission.
 *
 * Two of the permissions are worth reading twice. **Autonomy** takes
 * `config.write`: the screen exists to change what the deployment may do on its
 * own, and a reader who cannot change it already sees the current posture on the
 * overview and in the sidebar footer. **Administration** takes `identity.read`,
 * which is an administrator's permission and also covers `audit.read` by
 * construction — the two are granted together at every role that holds either
 * (see `platform/identity/permissions.py`'s `Role.ADMIN` increment) — so the
 * area's own gate never hides the Audit tab from somebody who could open the
 * People one.
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
    // The board draws a clock beside "Incidentes" — `ClockIcon` was unused
    // in this navigation before this feature.
    icon: ClockIcon,
  },
  {
    id: 'runs',
    path: '/runs',
    group: 'now',
    label: 'nav.runs',
    title: 'page.runs.title',
    context: 'page.runs.context',
    permission: 'investigation.read',
    // The board draws a search lens beside "Investigações" — the same lens
    // the topbar's own search box uses.
    icon: SearchIcon,
  },
  // Fuses Approvals ("may the agent do this now") and Proposed changes
  // ("should the deployment be different from tomorrow") into one screen,
  // two tabs. Both already needed `approval.read`, so the fusion needed no
  // new permission — a reader who could open either queue before can open
  // both tabs now, and nobody who could not gains access to either.
  {
    id: 'decisions',
    path: '/decisions',
    group: 'now',
    label: 'nav.decisions',
    title: 'page.decisions.title',
    context: 'page.decisions.context',
    permission: 'approval.read',
    // The board draws a shield with a check inside beside "Decisões" —
    // `ShieldIcon` was already exported, for `proposal.tsx` and the
    // transcript/activity "guardrail"/"guardian" kinds, and fits this
    // navigation entry too; `CheckIcon` stays the plain checkmark those two
    // files use for "report"/"verification".
    icon: ShieldIcon,
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
  // Fuses Memory, Topology and this screen's own prior content (the
  // documents an investigation may read) into three tabs on one question:
  // what does the agent know about this environment. `memory.read` and
  // `knowledge.read` are both granted at `Role.VIEWER` (see
  // `platform/identity/permissions.py`), so every viewer who could reach any
  // one of the three before can reach all three tabs now.
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
    // What the agent is, what it can do, and what it will do alone — now also
    // the catalogue's own read surface (tools and skills, in read mode, with
    // search) and the team's operating context, both absorbed whole. Writing
    // still happens on the screens built for it (Integrations, Autonomy,
    // Configuration); this is where an operator comes to read the agent, not
    // to change it. The permission is the narrowest of the reads it makes —
    // the node's catalogue, its fields, its effective configuration and its
    // posture are all `config.read`.
    id: 'agent',
    path: '/agent',
    group: 'environment',
    label: 'nav.agent',
    title: 'page.agent.title',
    context: 'page.agent.context',
    permission: 'config.read',
    icon: ActivityIcon,
  },
  {
    // The one entry whose `visible` rule is unconditional rather than a
    // question about the deployment: the hybrid navigation retired this from
    // the sidebar outright, because setting a deployment up is a task rather
    // than a place and it is rebuilt as a wizard of its own. The route
    // stays served — nothing redirects away from it while there is a
    // checklist left to finish — so an operator still deciding whether to
    // keep this product can look at the whole of it before filling in a
    // form, and a link into it from anywhere in the product still resolves.
    id: 'first-run',
    path: '/first-run',
    group: 'settings',
    label: 'nav.firstRun',
    title: 'page.firstRun.title',
    context: 'page.firstRun.context',
    permission: 'config.read',
    icon: CompassIcon,
    visible: () => false,
  },
  // What the Catalogue used to be, once its browsing half moved to The
  // agent: the validated integrations as cards with a real state (absent,
  // stored, verified, failing), a credential form collapsed until asked
  // for, and the credential test. The first run points here, a blocked
  // tool's "connect it" link points here, and there is no third place a
  // credential is entered from. `integration.manage` rather than a broader read
  // permission: the gateway's own `GET /v1/integrations` already requires it
  // (`gateway/http/security/gateway_routes.py`), so a broader area gate
  // would only mean the one screen's one panel 403s for whoever it let in —
  // the same reasoning Autonomy's own gate already applies.
  {
    id: 'integrations',
    path: '/integrations',
    group: 'settings',
    label: 'nav.integrations',
    title: 'page.integrations.title',
    context: 'page.integrations.context',
    permission: 'integration.manage',
    icon: LayersIcon,
  },
  // The hybrid navigation's other sidebar entry: Settings opens a subnav of
  // its own (`SETTINGS_PAGES`, below) rather than a screen. Gated on the one
  // permission every signed-in principal holds — the same one `dashboard`
  // uses — because the hub itself reads nothing; what a viewer's own
  // permissions narrow is which of the nine pages the subnav offers once
  // they are inside, exactly the way an empty incidents list still opens.
  {
    id: 'settings',
    path: '/settings',
    group: 'settings',
    label: 'nav.settings',
    title: 'page.settings.title',
    context: 'page.settings.context',
    permission: 'investigation.read',
    icon: SettingsIcon,
  },
  // Fuses Detectors and Data: two halves of the one pipe an alert travels
  // through, entrada and saída, that used to sit in different zones of the
  // menu for no reason a reader could see. Both already needed
  // `config.read`.
  //
  // Retired from the sidebar by the hybrid navigation (its own `visible`
  // rule, below) — two of its four tabs now have Settings pages of their own
  // (`settings-alert-intake`, `settings-schedules-destinations`) and the old
  // address redirects to whichever the query names. The area entry itself
  // stays: `/signals?tab=observation` keeps rendering this screen, because
  // nothing in the nine Settings pages replaces continuous observation yet,
  // and `emptiness.ts`'s `watchingCause` still points there by address.
  {
    id: 'signals',
    path: '/signals',
    group: 'settings',
    label: 'nav.signals',
    title: 'page.signals.title',
    context: 'page.signals.context',
    permission: 'config.read',
    icon: DatabaseIcon,
    visible: () => false,
  },
  // Retired from the sidebar by the hybrid navigation; `/settings/autonomy-
  // guardrails` renders this same screen. The area entry stays because the
  // screen's own header still resolves it by this id.
  {
    id: 'autonomy',
    path: '/autonomy',
    group: 'settings',
    label: 'nav.autonomy',
    title: 'page.autonomy.title',
    context: 'page.autonomy.context',
    permission: 'config.write',
    icon: ShieldIcon,
    visible: () => false,
  },
  // Retired: the raw editor is gone, and every field it could reach is now
  // edited on the page that owns its subject. The address stays, like the
  // other retired ones, so an old bookmark still lands somewhere — but it
  // redirects rather than renders, and it redirects per *section*, because
  // the group a visitor wanted is in the URL fragment. The entry is kept
  // rather than deleted so the deploy walk still opens the address and finds
  // it answering; the page behind it is a forwarder, not a screen.
  {
    id: 'configuration',
    path: '/configuration',
    group: 'settings',
    label: 'nav.configuration',
    title: 'page.configuration.title',
    context: 'page.configuration.context',
    permission: 'config.read',
    icon: SettingsIcon,
    visible: () => false,
  },
  // Audit is a tab here rather than its own entry: it is read in the context
  // of "who did what", the neighbouring question to "who may do what", and
  // both already took an administrator's own permission.
  //
  // The comment is outside the object literal deliberately: the contract suite
  // parses this file with a regular expression that reads `id` immediately
  // after the brace, so a comment inside makes an area invisible to the check
  // that every declared route is walked.
  //
  // Retired from the sidebar by the hybrid navigation; `settings-members-
  // roles` and `settings-audit-log` carry this screen's two tabs onward as
  // their own addresses. The area entry stays because this screen's own
  // header still resolves it by this id.
  {
    id: 'administration',
    path: '/administration',
    group: 'settings',
    label: 'nav.administration',
    title: 'page.administration.title',
    context: 'page.administration.context',
    permission: 'identity.read',
    icon: UsersIcon,
    visible: () => false,
  },
  // The catalogue's own reference page: every vendor this deployment does not
  // cover, and why. Reached only by a link from the catalogue's footer and
  // from its own search-empty state, never from the sidebar — the same
  // `visible: () => false` the other reference-only addresses use. The
  // permission is the catalogue's own: the data is `known_gaps`, served
  // alongside `GET /v1/integrations` rather than from a route of its own.
  {
    id: 'integrations-not-covered',
    path: '/integrations/not-covered',
    group: 'settings',
    label: 'nav.integrationsNotCovered',
    title: 'page.integrationsNotCovered.title',
    context: 'page.integrationsNotCovered.context',
    permission: 'integration.manage',
    icon: LayersIcon,
    visible: () => false,
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

/**
 * The Settings subnav.
 *
 * A page here is a sibling of `Area` rather than one: it has no place in the
 * top-level sidebar and no icon (the subnav draws it as plain text, the way
 * the mockup does), and it is reached through exactly one address, the
 * Settings area's own. What it shares with `Area` is everything that matters
 * for the same reasons — a route, a permission copied from the gateway by
 * name, and the same absence-not-disabled rule `groupsFor` already applies —
 * so the shape below mirrors `Area` deliberately rather than by coincidence.
 */

/** The three groups the subnav draws, in the order the mockup draws them. */
export const SETTINGS_GROUPS = ['organization', 'agent', 'data'] as const;

export type SettingsGroup = (typeof SETTINGS_GROUPS)[number];

/** One page of the Settings subnav: a route, a group, a gate. */
export interface SettingsPage {
  readonly id: string;
  readonly path: string;
  readonly group: SettingsGroup;
  /** Doubles as the subnav's own link text and the page's title — the mockup
   * draws them as the same word, and a separate title key would only ever
   * hold the same string a second time. */
  readonly label: MessageKey;
  readonly context: MessageKey;
  /** The permission the API requires on the data this page reads. */
  readonly permission: string;
}

/**
 * The nine pages, in the three groups the mockup draws them in.
 *
 * None of the nine has a screen purpose-built for it yet; the work that
 * builds each domain's own screen is still ahead.
 * Four of the nine (Members & roles, Audit log, Models & providers,
 * Autonomy & guardrails) render a screen this console already has, because
 * an equivalent screen already exists; the remaining five render the shared
 * empty state, naming the page that arrives with the work that builds it,
 * because a route that exists and says so is worth more than a screen
 * invented to fill the gap.
 *
 * The comment below is outside every object literal deliberately, for the
 * same reason `administration`'s comment above is: the contract suite parses
 * this file with a regular expression that reads `id` immediately after the
 * brace, and a comment inside would make that entry invisible to the check
 * that every declared route is covered.
 */
export const SETTINGS_PAGES: readonly SettingsPage[] = [
  {
    id: 'settings-members-roles',
    path: '/settings/members-roles',
    group: 'organization',
    label: 'settings.page.membersRoles',
    context: 'settings.page.membersRoles.context',
    permission: 'identity.read',
  },
  {
    id: 'settings-single-sign-on',
    path: '/settings/single-sign-on',
    group: 'organization',
    label: 'settings.page.singleSignOn',
    context: 'settings.page.singleSignOn.context',
    permission: 'sso.manage',
  },
  {
    id: 'settings-machine-tokens',
    path: '/settings/machine-tokens',
    group: 'organization',
    label: 'settings.page.machineTokens',
    context: 'settings.page.machineTokens.context',
    permission: 'token.manage',
  },
  {
    id: 'settings-audit-log',
    path: '/settings/audit-log',
    group: 'organization',
    label: 'settings.page.auditLog',
    context: 'settings.page.auditLog.context',
    permission: 'audit.read',
  },
  // Models & providers has no screen of its own yet — the raw editor and the
  // setup wizard are the only places a provider is chosen today, and neither
  // is what this page becomes. `config.write` because choosing what drives
  // an investigation is a change to configuration, the same reasoning
  // `autonomy`'s own gate already applies.
  {
    id: 'settings-models-providers',
    path: '/settings/models-providers',
    group: 'agent',
    label: 'settings.page.modelsProviders',
    context: 'settings.page.modelsProviders.context',
    permission: 'config.write',
  },
  {
    id: 'settings-autonomy-guardrails',
    path: '/settings/autonomy-guardrails',
    group: 'agent',
    label: 'settings.page.autonomyGuardrails',
    context: 'settings.page.autonomyGuardrails.context',
    permission: 'config.write',
  },
  // No screen anywhere in the console reads or writes notification policy
  // today. `config.write` for the same reason `settings-models-providers`
  // takes it: the domain is a configuration change, not a read.
  {
    id: 'settings-notifications',
    path: '/settings/notifications',
    group: 'agent',
    label: 'settings.page.notifications',
    context: 'settings.page.notifications.context',
    permission: 'config.write',
  },
  // `config.read`, copied from the permission the retired `signals` area
  // already declared for this exact domain (the gateway's own
  // `/v1/transit/ingress` and `/v1/transit/destinations` both take it too).
  {
    id: 'settings-alert-intake',
    path: '/settings/alert-intake',
    group: 'data',
    label: 'settings.page.alertIntake',
    context: 'settings.page.alertIntake.context',
    permission: 'config.read',
  },
  {
    id: 'settings-schedules-destinations',
    path: '/settings/schedules-destinations',
    group: 'data',
    label: 'settings.page.schedulesDestinations',
    context: 'settings.page.schedulesDestinations.context',
    permission: 'config.read',
  },
];

/** Kept so the subnav is a closed list rather than a suggestion. */
const SETTINGS_PAGES_BY_ID: ReadonlyMap<string, SettingsPage> = new Map(
  SETTINGS_PAGES.map((page) => [page.id, page]),
);

/** The settings page called `id`, or an error naming what was asked for. */
export function settingsPageFor(id: string): SettingsPage {
  const page = SETTINGS_PAGES_BY_ID.get(id);
  if (page === undefined) {
    throw new Error(`${id} is not a page of the Settings subnav`);
  }
  return page;
}

/**
 * The settings page a path names, ignoring a trailing slash.
 *
 * `undefined` rather than a throw, for the reason `areaByPath` gives: an
 * address a person typed is not a defect.
 */
export function settingsPageByPath(path: string): SettingsPage | undefined {
  const trimmed = path.length > 1 && path.endsWith('/') ? path.slice(0, -1) : path;
  return SETTINGS_PAGES.find((page) => page.path === trimmed);
}

/** The settings pages `viewer` may reach. Absence, not disabled — the same rule `visibleAreas` follows. */
export function visibleSettingsPages(viewer: Viewer): readonly SettingsPage[] {
  return SETTINGS_PAGES.filter((page) => may(viewer, page.permission));
}

/** One group of the subnav, with the pages of it this viewer may reach. */
export interface SettingsPageGroup {
  readonly group: SettingsGroup;
  readonly pages: readonly SettingsPage[];
}

/**
 * The subnav, grouped and in order, with empty groups dropped entirely.
 *
 * The same construction as `groupsFor`, over the sibling list: a group
 * nothing in it is reachable is omitted rather than shown open and empty.
 */
export function settingsGroupsFor(viewer: Viewer): readonly SettingsPageGroup[] {
  const visible = visibleSettingsPages(viewer);
  return SETTINGS_GROUPS.map((group) => ({
    group,
    pages: visible.filter((page) => page.group === group),
  })).filter((entry) => entry.pages.length > 0);
}

/**
 * One retired address, and the live one it sends a visitor to instead.
 *
 * Not only Settings: the same shape and the same mechanism serve any old
 * address whose name people kept using after the screen behind it moved —
 * `/investigations` and `/setup` are the console's own vocabulary
 * (`nav.decisions`'s neighbours, the setup wizard everybody calls "setup"),
 * not screens that were ever under the Settings subnav.
 *
 * `tab` absent is the entry `legacyRouteTarget` falls back to when the query
 * names no tab this table recognises — the same address the retired screen
 * itself used to default to, so a visitor who bookmarked the bare route or
 * an unrecognised variant of it still lands somewhere true to what they had.
 */
export interface LegacyRouteRedirect {
  readonly from: string;
  readonly tab?: string;
  readonly to: string;
}

/**
 * Every redirect the console ships with, for a route it no longer serves.
 *
 * `/first-run` is not here as a *source*: its own redirect (when the
 * checklist is already complete) depends on deployment state this table
 * cannot hold, so its own route file reads that directly. It is very much a
 * *destination* here, for `/setup`. `/configuration` is not here at all — it
 * is the one Settings address the migration does not retire yet.
 *
 * `/signals?tab=observation` is deliberately absent too: nothing in the nine
 * Settings pages replaces continuous observation, so that one variant keeps
 * rendering the screen it always has rather than redirecting to a page that
 * would say the wrong thing about why nothing is here.
 */
export const LEGACY_ROUTE_REDIRECTS: readonly LegacyRouteRedirect[] = [
  { from: '/autonomy', to: '/settings/autonomy-guardrails' },
  { from: '/administration', to: '/settings/members-roles' },
  { from: '/administration', tab: 'people', to: '/settings/members-roles' },
  { from: '/administration', tab: 'audit', to: '/settings/audit-log' },
  { from: '/signals', to: '/settings/alert-intake' },
  { from: '/signals', tab: 'intake', to: '/settings/alert-intake' },
  { from: '/signals', tab: 'destinations', to: '/settings/schedules-destinations' },
  { from: '/signals', tab: 'schedules', to: '/settings/schedules-destinations' },
  // The names the sidebar and the search palette already use for these two
  // areas — `/investigations` for the runs list, `/setup` for the guided
  // first run — answered "there is no such page" until this feature gave
  // them the same retired-route mechanism every other renamed screen uses.
  { from: '/investigations', to: '/runs' },
  { from: '/setup', to: '/first-run' },
];

/**
 * Where `path` (with `tab`, when the caller has one) redirects to, or
 * `undefined` when nothing retires it.
 */
export function legacyRouteTarget(
  path: string,
  tab: string | null,
): string | undefined {
  const candidates = LEGACY_ROUTE_REDIRECTS.filter((entry) => entry.from === path);
  if (tab !== null) {
    const named = candidates.find((entry) => entry.tab === tab);
    if (named !== undefined) return named.to;
  }
  return candidates.find((entry) => entry.tab === undefined)?.to;
}
