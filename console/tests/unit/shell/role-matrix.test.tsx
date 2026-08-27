import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AREAS, visibleAreas } from '@/shell/routes';
import { Sidebar } from '@/shell/sidebar';
import { Topbar } from '@/shell/topbar';
import { may } from '@/session/viewer';

import { ROLE_ORDER, viewerAt } from './support';

/**
 * Every role × every area, and every shell control — asserted as **absence**.
 *
 * A disabled control is not a substitute. It still says the capability exists,
 * it still says somebody else has it, and it still ships whatever handler sits
 * behind it. So the assertion is that the element is not in the document at all,
 * and it is made for every role the platform declares against every area the
 * manifest carries. Adding either is covered by having added it.
 */

const GUARDIAN = { live: true, posture: 'propose' } as const;

/**
 * A deadlock ceiling, not a performance budget — and the reason it is stated.
 *
 * This file is the widest one in the suite: every role the platform declares
 * against every area the manifest carries, each case rendering a full shell
 * from scratch. That is sixty-odd renders, and it is deliberate — the whole
 * point is that adding a role or an area is covered by having added it.
 *
 * Measured on an idle machine, the slowest single case is under forty
 * milliseconds. Under load it went past vitest's five-second default and the
 * file went red, twice in one day, on a tree that had not changed: the same
 * commit passed and failed on consecutive full runs, with the suite itself
 * taking 383s and then 694s. Nothing about the test was slow; its worker was
 * simply not being scheduled.
 *
 * A gate that goes red for machine load is one people learn to re-run instead
 * of read, and a re-run is how a real failure gets waved through. So the
 * timeout is set where it can only be reached by a test that never finishes —
 * three orders of magnitude above the measured worst case. Raising a timeout
 * hides a genuine slowdown only when the timeout was a budget; this one never
 * was, and the budgets that do exist are the browser suite's first-paint and
 * route-transition assertions.
 */
const MATRIX_TIMEOUT_MS = 30_000;

/**
 * Areas the hybrid navigation retires from the sidebar unconditionally — an
 * unconditional `visible: () => false`, not a permission question — so the
 * "present only if held" property below does not hold for them: holding the
 * permission is no longer sufficient, by design. Their own screens are
 * covered where they now live, under the Settings subnav; the manifest's own
 * `the areas the Settings subnav replaced` suite in `routes.test.ts` covers
 * the retirement itself.
 */
const RETIRED_FROM_SIDEBAR = new Set([
  'first-run',
  'signals',
  'autonomy',
  'configuration',
  'administration',
  // Reference-only: reached from the catalogue's own footer and its
  // search-empty state, never from the sidebar.
  'integrations-not-covered',
]);

function nothing(): void {
  // Every control the shell hands out needs a handler; none of them is what
  // this file is about.
}

function renderSidebar(role: string): void {
  render(<Sidebar viewer={viewerAt(role)} locale="en" guardian={GUARDIAN} />);
}

describe('the navigation, per role', { timeout: MATRIX_TIMEOUT_MS }, () => {
  for (const role of ROLE_ORDER) {
    for (const area of AREAS.filter((each) => !RETIRED_FROM_SIDEBAR.has(each.id))) {
      it(`${role}: ${area.id} is ${area.permission} and is present only if held`, () => {
        renderSidebar(role);
        const viewer = viewerAt(role);
        const entry = screen.queryByTestId('nav-entry-marker');
        expect(entry).toBeNull();

        const entries = screen
          .queryAllByTestId('nav-entry')
          .map((element) => element.getAttribute('data-area'));

        if (may(viewer, area.permission)) {
          expect(entries).toContain(area.id);
        } else {
          // Absent, not disabled. This is the assertion the whole criterion is.
          expect(entries).not.toContain(area.id);
        }
      });
    }
  }

  for (const role of ROLE_ORDER) {
    it(`${role}: none of the areas the hybrid navigation retired is ever in the sidebar`, () => {
      renderSidebar(role);
      const entries = screen
        .queryAllByTestId('nav-entry')
        .map((element) => element.getAttribute('data-area'));

      for (const id of RETIRED_FROM_SIDEBAR) {
        expect(entries, `${role}: ${id}`).not.toContain(id);
      }
    });
  }

  it('shows the least privileged role strictly fewer areas than the most', () => {
    const least = ROLE_ORDER[0];
    const most = ROLE_ORDER[ROLE_ORDER.length - 1];
    expect(least).toBeDefined();
    expect(most).toBeDefined();
    if (least === undefined || most === undefined) return;

    // Without this the matrix above could pass against a manifest where every
    // area needs the same permission, which would prove nothing at all.
    expect(visibleAreas(viewerAt(least)).length).toBeLessThan(
      visibleAreas(viewerAt(most)).length,
    );
  });
});

describe('the shell controls, per role', { timeout: MATRIX_TIMEOUT_MS }, () => {
  const CONTROLS = [
    { testId: 'investigate', permission: 'investigation.run' },
    { testId: 'impersonate', permission: 'impersonation.use' },
  ] as const;

  for (const role of ROLE_ORDER) {
    for (const control of CONTROLS) {
      it(`${role}: ${control.testId} is present only with ${control.permission}`, () => {
        render(
          <Topbar
            viewer={viewerAt(role)}
            locale="en"
            deployment={{ name: 'HAL9000', timezone: 'UTC' }}
            attention={[]}
            onOpenPalette={nothing}
            onOpenNotifications={nothing}
            onOpenDrawer={nothing}
            onInvestigate={nothing}
            onSignOut={nothing}
          />,
        );

        const found = screen.queryByTestId(control.testId);
        if (may(viewerAt(role), control.permission)) {
          expect(found).not.toBeNull();
        } else {
          expect(found).toBeNull();
        }
      });
    }
  }

  it('has at least one control the least privileged role does not get', () => {
    const least = ROLE_ORDER[0];
    if (least === undefined) throw new Error('the role catalogue is empty');
    expect(CONTROLS.some((control) => !may(viewerAt(least), control.permission))).toBe(
      true,
    );
  });
});
