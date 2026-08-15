import { describe, expect, it } from 'vitest';

import { EN } from '@/i18n/en';
import {
  AREAS,
  areaByPath,
  areaFor,
  groupsFor,
  NAV_GROUPS,
  SETTINGS_GROUPS,
  SETTINGS_PAGES,
  SETTINGS_REDIRECTS,
  settingsGroupsFor,
  settingsPageByPath,
  settingsPageFor,
  settingsRedirectTarget,
  trailFor,
  visibleAreas,
  visibleSettingsPages,
} from '@/shell/routes';
import type { Viewer } from '@/session/viewer';

/**
 * The route manifest, which is the console's only list of what exists.
 *
 * Everything the shell enumerates — the sign-in guard, the role matrix, the deep
 * links, the palette's navigation commands — reads this. That is the whole
 * design: a route added tomorrow is covered by the tests that already exist,
 * because they walk this rather than a list somebody remembered to extend.
 */

function viewerHolding(permissions: readonly string[]): Viewer {
  return {
    principalId: 'user-test',
    displayName: 'Test Person',
    email: null,
    roles: [],
    permissions,
    teamNodeId: 'org-test',
    impersonating: false,
    impersonatedBy: null,
  };
}

const OWNER = viewerHolding([
  'investigation.read',
  'investigation.run',
  'approval.read',
  'memory.read',
  'knowledge.read',
  'config.read',
  'config.write',
  'audit.read',
  'identity.read',
  'integration.manage',
  'impersonation.use',
  // The two the Settings subnav's own pages needed that no area ever had —
  // sso.manage and token.manage gate no top-level area, only the Single
  // sign-on and Machine tokens subnav pages, so an owner fixture built
  // before they existed had never needed either.
  'sso.manage',
  'token.manage',
]);

describe('the route manifest', () => {
  it('carries one entry per area, each with a path of its own', () => {
    const paths = AREAS.map((area) => area.path);
    expect(new Set(paths).size).toBe(AREAS.length);
    expect(AREAS.length).toBeGreaterThanOrEqual(12);
  });

  it('gives every area an identifier of its own', () => {
    const ids = AREAS.map((area) => area.id);
    expect(new Set(ids).size).toBe(AREAS.length);
  });

  it('names only groups the navigation declares, in the documented order', () => {
    // Three zones separated by how often somebody opens them, not by subject.
    // "Now" is first because it is where a person is when something broke.
    expect([...NAV_GROUPS]).toEqual(['now', 'environment', 'settings']);
    for (const area of AREAS) {
      expect(NAV_GROUPS, area.id).toContain(area.group);
    }
  });

  it('puts every area in the zone the information architecture assigns it', () => {
    const zones: Readonly<Record<string, string>> = {
      dashboard: 'now',
      incidents: 'now',
      runs: 'now',
      decisions: 'now',
      resources: 'environment',
      knowledge: 'environment',
      agent: 'environment',
      'first-run': 'settings',
      integrations: 'settings',
      'integrations-not-covered': 'settings',
      signals: 'settings',
      autonomy: 'settings',
      configuration: 'settings',
      administration: 'settings',
      settings: 'settings',
    };
    for (const area of AREAS) {
      expect(zones[area.id], `${area.id} is in no declared zone`).toBeDefined();
      expect(area.group, area.id).toBe(zones[area.id]);
    }
    // Both directions: a zone assignment for an area that no longer exists is
    // a rename nobody finished.
    for (const id of Object.keys(zones)) {
      expect(
        AREAS.some((area) => area.id === id),
        `${id} is assigned a zone and is not an area`,
      ).toBe(true);
    }
  });

  it('takes every string it renders from the catalogue', () => {
    for (const area of AREAS) {
      expect(EN[area.label], area.id).toBeDefined();
      expect(EN[area.title], area.id).toBeDefined();
      expect(EN[area.context], area.id).toBeDefined();
    }
  });

  it('declares a permission for every area, and never invents one', () => {
    // The console reads a permission the server already enforces; it never
    // decides one. `tests/contract/console/test_console_shell.py` holds each of
    // these against the gateway's own route table.
    for (const area of AREAS) {
      expect(area.permission, area.id).toMatch(/^[a-z]+\.[a-z]+$/);
    }
  });

  it('gives every area an icon, because a label with no shape is a list', () => {
    for (const area of AREAS) {
      expect(typeof area.icon, area.id).toBe('function');
    }
  });

  it('finds an area by identifier, and refuses one it does not have', () => {
    expect(areaFor('dashboard').path).toBe('/');
    expect(() => areaFor('nowhere')).toThrow('nowhere');
  });

  it('finds an area by path, and answers nothing for a path it does not serve', () => {
    expect(areaByPath('/administration')?.id).toBe('administration');
    expect(areaByPath('/administration/')?.id).toBe('administration');
    expect(areaByPath('/no-such-place')).toBeUndefined();
  });
});

describe('what a viewer may see', () => {
  it('drops the areas the viewer has no permission for', () => {
    const viewer = viewerHolding(['investigation.read']);
    const visible = visibleAreas(viewer).map((area) => area.id);

    expect(visible).toContain('dashboard');
    expect(visible).not.toContain('audit');
    expect(visible).not.toContain('autonomy');
  });

  it('shows an owner every area whose own rule does not retire it', () => {
    // The subnav pages that replace autonomy/signals/administration/configuration
    // in the sidebar carry their own rule that hides them unconditionally — an
    // owner sees them only by their new, addressed-by-Settings-page presence, not
    // as sidebar areas any more.
    const retired = AREAS.filter(
      (area) => area.visible?.({ checklistComplete: false }) === false,
    ).length;
    expect(visibleAreas(OWNER)).toHaveLength(AREAS.length - retired);
  });

  it('drops a whole group when nothing in it is permitted', () => {
    // knowledge.read reaches only the Knowledge area, in `environment` — not
    // `now` (every one of its four areas wants investigation.read or
    // approval.read) and not `settings` (the hub itself wants
    // investigation.read, same as dashboard, and nothing else in the group
    // is knowledge-gated).
    const viewer = viewerHolding(['knowledge.read']);
    const groups = groupsFor(viewer).map((group) => group.group);

    expect(groups).toContain('environment');
    expect(groups).not.toContain('now');
    expect(groups).not.toContain('settings');
  });

  it('keeps the Settings hub itself present when every subnav page is retired for this viewer', () => {
    // investigation.read is the hub's own gate, the same one dashboard uses,
    // so a viewer holding it always finds Settings in the sidebar even when
    // none of the nine subnav pages are theirs to open.
    const viewer = viewerHolding(['investigation.read']);
    const settings = groupsFor(viewer).find((group) => group.group === 'settings');

    expect(settings?.areas.map((area) => area.id)).toEqual(['settings']);
  });

  it('keeps the groups in the documented order', () => {
    expect(groupsFor(OWNER).map((group) => group.group)).toEqual([...NAV_GROUPS]);
  });
});

describe('the areas the Settings subnav replaced', () => {
  // first-run, integrations' former siblings (signals, autonomy, configuration,
  // administration) are retired from the sidebar by the hybrid navigation: the
  // sidebar's Settings group now carries only Integrations and Settings itself.
  // Each of the four is still a real area — `areaFor`/`areaByPath` still resolve
  // it, because its route is still served (a redirect, or, for first-run and
  // configuration, its own unchanged content) — it is only offered nowhere in
  // the navigation any more.
  const RETIRED = [
    'first-run',
    'signals',
    'autonomy',
    'configuration',
    'administration',
  ];

  it('is absent from every viewer, in every deployment state', () => {
    for (const id of RETIRED) {
      expect(
        visibleAreas(OWNER, { checklistComplete: true }).map((area) => area.id),
        id,
      ).not.toContain(id);
      expect(
        visibleAreas(OWNER, { checklistComplete: false }).map((area) => area.id),
        id,
      ).not.toContain(id);
    }
  });

  it('drops out of the navigation groups too, not only out of the list', () => {
    const groups = groupsFor(OWNER, { checklistComplete: true });
    const settings = groups.find((group) => group.group === 'settings');

    for (const id of RETIRED) {
      expect(settings?.areas.map((area) => area.id)).not.toContain(id);
    }
    // The zone itself survives: Integrations and Settings still hold it open.
    expect(settings?.areas.map((area) => area.id)).toEqual([
      'integrations',
      'settings',
    ]);
  });

  it('is still reachable by address once it leaves the navigation', () => {
    // "Appears and disappears" is about the sidebar. A route that stopped
    // resolving would make a link to it — or an internal `areaFor` call the
    // screen it still renders depends on — a dead end.
    for (const id of RETIRED) {
      expect(areaByPath(areaFor(id).path)?.id, id).toBe(id);
    }
  });
});

describe('the trail a page header carries', () => {
  it('is one crumb for a top-level area, which is no breadcrumb at all', () => {
    expect(trailFor(areaFor('runs'))).toHaveLength(1);
  });

  it('puts the area in front of anything nested under it, and links only the parent', () => {
    const trail = trailFor(areaFor('runs'), [{ label: 'run-0001' }]);

    expect(trail.map((crumb) => crumb.label)).toEqual(['page.runs.title', 'run-0001']);
    expect(trail[0]?.href).toBe('/runs');
    expect(trail[1]?.href).toBeUndefined();
  });
});

describe('the Settings subnav manifest', () => {
  it('carries the nine pages the subnav needs, each with a path of its own', () => {
    const paths = SETTINGS_PAGES.map((page) => page.path);
    expect(new Set(paths).size).toBe(SETTINGS_PAGES.length);
    expect(SETTINGS_PAGES.length).toBe(9);
    for (const page of SETTINGS_PAGES) {
      expect(page.path.startsWith('/settings/'), page.id).toBe(true);
    }
  });

  it('gives every settings page an identifier of its own', () => {
    const ids = SETTINGS_PAGES.map((page) => page.id);
    expect(new Set(ids).size).toBe(SETTINGS_PAGES.length);
  });

  it('names only groups the subnav declares, in the documented order', () => {
    expect([...SETTINGS_GROUPS]).toEqual(['organization', 'agent', 'data']);
    for (const page of SETTINGS_PAGES) {
      expect(SETTINGS_GROUPS, page.id).toContain(page.group);
    }
  });

  it('puts every page in the group the mockup assigns it, in the mockup order', () => {
    expect(
      SETTINGS_PAGES.filter((p) => p.group === 'organization').map((p) => p.id),
    ).toEqual([
      'settings-members-roles',
      'settings-single-sign-on',
      'settings-machine-tokens',
      'settings-audit-log',
    ]);
    expect(SETTINGS_PAGES.filter((p) => p.group === 'agent').map((p) => p.id)).toEqual([
      'settings-models-providers',
      'settings-autonomy-guardrails',
      'settings-notifications',
    ]);
    expect(SETTINGS_PAGES.filter((p) => p.group === 'data').map((p) => p.id)).toEqual([
      'settings-alert-intake',
      'settings-schedules-destinations',
    ]);
  });

  it('takes every string it renders from the catalogue', () => {
    for (const page of SETTINGS_PAGES) {
      expect(EN[page.label], page.id).toBeDefined();
      expect(EN[page.context], page.id).toBeDefined();
    }
    for (const group of SETTINGS_GROUPS) {
      expect(EN[`settings.group.${group}` as const], group).toBeDefined();
    }
  });

  it('declares a permission for every page, and never invents one — the same contract as an area', () => {
    for (const page of SETTINGS_PAGES) {
      expect(page.permission, page.id).toMatch(/^[a-z]+\.[a-z]+$/);
    }
  });

  it('finds a settings page by identifier, and refuses one it does not have', () => {
    expect(settingsPageFor('settings-audit-log').path).toBe('/settings/audit-log');
    expect(() => settingsPageFor('nowhere')).toThrow('nowhere');
  });

  it('finds a settings page by path, and answers nothing for a path it does not serve', () => {
    expect(settingsPageByPath('/settings/audit-log')?.id).toBe('settings-audit-log');
    expect(settingsPageByPath('/settings/audit-log/')?.id).toBe('settings-audit-log');
    expect(settingsPageByPath('/settings/no-such-page')).toBeUndefined();
  });

  it('drops the pages the viewer has no permission for', () => {
    const viewer = viewerHolding(['config.read']);
    const visible = visibleSettingsPages(viewer).map((page) => page.id);

    expect(visible).toContain('settings-alert-intake');
    expect(visible).not.toContain('settings-audit-log');
    expect(visible).not.toContain('settings-autonomy-guardrails');
  });

  it('shows an owner every settings page there is', () => {
    expect(visibleSettingsPages(OWNER)).toHaveLength(SETTINGS_PAGES.length);
  });

  it('drops a whole subnav group when nothing in it is permitted, the same rule groupsFor follows', () => {
    // A viewer holding only what every role holds (config.read) reaches both
    // Data pages and nothing in Organization or Agent — so the subnav offers
    // exactly one group, not three with two of them empty.
    const viewer = viewerHolding(['config.read']);
    const groups = settingsGroupsFor(viewer).map((group) => group.group);

    expect(groups).toEqual(['data']);
  });

  it('keeps the groups in the documented order, for a viewer who reaches all three', () => {
    expect(settingsGroupsFor(OWNER).map((group) => group.group)).toEqual([
      ...SETTINGS_GROUPS,
    ]);
  });
});

describe('the redirect table from a retired route to its settings equivalent', () => {
  it('carries at least one destination for every retired route the acceptance scenarios name', () => {
    const from = new Set(SETTINGS_REDIRECTS.map((entry) => entry.from));
    expect(from).toContain('/autonomy');
    expect(from).toContain('/administration');
    expect(from).toContain('/signals');
  });

  it('sends every redirect to a page this console actually serves', () => {
    for (const entry of SETTINGS_REDIRECTS) {
      expect(
        areaByPath(entry.to) ?? settingsPageByPath(entry.to),
        `${entry.from}${entry.tab === undefined ? '' : `?tab=${entry.tab}`}`,
      ).toBeDefined();
    }
  });

  it('resolves a bare old route to its new address', () => {
    expect(settingsRedirectTarget('/autonomy', null)).toBe(
      '/settings/autonomy-guardrails',
    );
  });

  it('resolves a query-of-tab variant to a different address than the bare route', () => {
    expect(settingsRedirectTarget('/signals', null)).toBe('/settings/alert-intake');
    expect(settingsRedirectTarget('/signals', 'destinations')).toBe(
      '/settings/schedules-destinations',
    );
    expect(settingsRedirectTarget('/administration', 'audit')).toBe(
      '/settings/audit-log',
    );
    expect(settingsRedirectTarget('/administration', 'people')).toBe(
      '/settings/members-roles',
    );
  });

  it('answers nothing for a route the table does not retire', () => {
    expect(settingsRedirectTarget('/incidents', null)).toBeUndefined();
  });
});
