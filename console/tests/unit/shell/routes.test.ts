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
    expect([...NAV_GROUPS]).toEqual(['operate', 'estate', 'learn', 'govern']);
    for (const area of AREAS) {
      expect(NAV_GROUPS, area.id).toContain(area.group);
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

    expect(groups).toContain('operate');
    expect(groups).not.toContain('govern');
  });

  it('keeps the groups in the documented order', () => {
    expect(groupsFor(OWNER).map((group) => group.group)).toEqual([...NAV_GROUPS]);
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
