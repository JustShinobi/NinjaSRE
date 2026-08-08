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

function nothing(): void {
  // Every control the shell hands out needs a handler; none of them is what
  // this file is about.
}

function renderSidebar(role: string): void {
  render(
    <Sidebar viewer={viewerAt(role)} locale="en" current="/" guardian={GUARDIAN} />,
  );
}

describe('the navigation, per role', () => {
  for (const role of ROLE_ORDER) {
    for (const area of AREAS) {
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

describe('the shell controls, per role', () => {
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
