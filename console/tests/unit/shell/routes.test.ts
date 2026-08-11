import { describe, expect, it } from 'vitest';

import { EN } from '@/i18n/en';
import {
  AREAS,
  areaByPath,
  areaFor,
  groupsFor,
  NAV_GROUPS,
  trailFor,
  visibleAreas,
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
  'impersonation.use',
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
      approvals: 'now',
      resources: 'environment',
      topology: 'environment',
      detectors: 'environment',
      knowledge: 'environment',
      memory: 'environment',
      catalogue: 'environment',
      'first-run': 'settings',
      agent: 'settings',
      autonomy: 'settings',
      configuration: 'settings',
      data: 'settings',
      'team-context': 'settings',
      proposals: 'settings',
      administration: 'settings',
      audit: 'settings',
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
    expect(areaByPath('/audit')?.id).toBe('audit');
    expect(areaByPath('/audit/')?.id).toBe('audit');
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

  it('shows an owner every area there is', () => {
    expect(visibleAreas(OWNER)).toHaveLength(AREAS.length);
  });

  it('drops a whole group when nothing in it is permitted', () => {
    const viewer = viewerHolding(['investigation.read']);
    const groups = groupsFor(viewer).map((group) => group.group);

    expect(groups).toContain('now');
    expect(groups).not.toContain('settings');
  });

  it('keeps the groups in the documented order', () => {
    expect(groupsFor(OWNER).map((group) => group.group)).toEqual([...NAV_GROUPS]);
  });
});

describe('an area whose presence depends on the deployment rather than the viewer', () => {
  it('is absent when its own rule says so, and present when it does not', () => {
    const closed = visibleAreas(OWNER, { checklistComplete: true });
    const open = visibleAreas(OWNER, { checklistComplete: false });

    expect(closed.map((area) => area.id)).not.toContain('first-run');
    expect(open.map((area) => area.id)).toContain('first-run');
  });

  it('is shown when nobody said, because a checklist that could not be read is not a finished one', () => {
    // The shell reads the checklist for its own frame and degrades rather than
    // failing. Defaulting to hidden would take the one route that fixes a
    // half-configured deployment out of the navigation of exactly that
    // deployment.
    expect(visibleAreas(OWNER).map((area) => area.id)).toContain('first-run');
  });

  it('still answers to permission, whatever its own rule says', () => {
    const viewer = viewerHolding(['investigation.read']);
    expect(
      visibleAreas(viewer, { checklistComplete: false }).map((a) => a.id),
    ).not.toContain('first-run');
  });

  it('drops out of the navigation groups too, not only out of the list', () => {
    const groups = groupsFor(OWNER, { checklistComplete: true });
    const settings = groups.find((group) => group.group === 'settings');

    expect(settings?.areas.map((area) => area.id)).not.toContain('first-run');
    // The zone itself survives: it holds more than this one entry.
    expect(settings?.areas.length).toBeGreaterThan(0);
  });

  it('is still reachable by address once it leaves the navigation', () => {
    // "Appears and disappears" is about the sidebar. A route that stopped
    // resolving would make the settings link to it a dead end.
    expect(areaByPath('/first-run')?.id).toBe('first-run');
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
