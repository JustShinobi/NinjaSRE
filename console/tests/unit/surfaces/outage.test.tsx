import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AuditLogPage from '@/app/(shell)/settings/audit-log/page';
import AutonomyGuardrailsPage from '@/app/(shell)/settings/autonomy-guardrails/page';
import MembersRolesPage from '@/app/(shell)/settings/members-roles/page';
import { SESSION_COOKIE } from '@/session/cookies';
import { AREAS } from '@/shell/routes';

import { AREA_SCREENS } from '../support/screens';
import { principalHolding, serveOutage } from '../support/dataset';

/**
 * The one area with no screen at all: `settings` only ever redirects, to
 * whichever Settings page is first for the viewer, so there is no panel for
 * it to fail inside. `signals`, `autonomy`, `administration` are *not* here —
 * their own address also redirects now, but `AREA_SCREENS`'s entries for the
 * three call the screen function directly (`../support/screens.ts` explains
 * why), so the property below still holds for them at their old id. Three of
 * them also get a second, direct proof at their new Settings address, in
 * `describe('the Settings pages that reuse a retired screen')`.
 */
const HAS_NO_SCREEN = new Set(['settings']);

/**
 * Every route of the shell, with nothing behind it.
 *
 * The property is the one the panel boundary exists for and the one nothing was
 * holding: **a dependency that is unavailable takes down a panel, never a
 * route.** A screen that throws instead reaches the route's error boundary,
 * which is an HTTP 500 — a page an operator cannot read, cannot navigate away
 * from, and cannot tell apart from the console being broken.
 *
 * This walks `AREAS` rather than the screen list, because `AREAS` is the
 * console's own closed answer to "what routes are there". A fifteenth area
 * added tomorrow is covered by this the day it is added rather than the day
 * somebody remembers to extend a list — and an area with no screen behind it
 * fails here rather than in a browser.
 *
 * The outage is a *connection* that is never made, which is the half
 * `screens.test.tsx` does not cover: it serves a 503, and a refusal and a
 * silence are different exceptions.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/** Every permission there is, so nothing is skipped by a gate rather than survived. */
const EVERYTHING = [
  'approval.read',
  'audit.read',
  'config.read',
  'config.write',
  'identity.read',
  'integration.manage',
  'investigation.read',
  'investigation.run',
  'knowledge.read',
  'memory.read',
  'remediation.approve',
  'remediation.execute',
  'schedule.manage',
  'token.manage',
];

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
  serveOutage();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderArea(id: string): Promise<void> {
  const target = AREA_SCREENS.find((each) => each.id === id);
  if (target === undefined) throw new Error(`no screen renders the ${id} area`);
  render(await target.render({ searchParams: Promise.resolve({}) }));
}

describe('the shell with its gateway unreachable', () => {
  it('has a screen for every area the manifest declares, once the screen-less one is set aside', () => {
    // The guard on the walk below: an area nothing renders would otherwise be
    // silently skipped by it.
    expect(AREA_SCREENS.map((each) => each.id).sort()).toEqual(
      AREAS.map((area) => area.id)
        .filter((id) => !HAS_NO_SCREEN.has(id))
        .sort(),
    );
  });

  for (const area of AREAS.filter((each) => !HAS_NO_SCREEN.has(each.id))) {
    it(`${area.path}: renders the page and fails inside its panels`, async () => {
      // Rendering at all is the assertion: a screen that throws here is a 500.
      await renderArea(area.id);

      expect(screen.getByTestId('page-header')).toBeInTheDocument();

      const panels = screen.getAllByTestId('panel');
      expect(panels.length).toBeGreaterThan(0);
      const failed = panels.filter(
        (panel) => panel.getAttribute('data-state') === 'error',
      );
      expect(failed.length).toBeGreaterThan(0);
      for (const panel of failed) {
        // Named, so a reader knows which dependency to go and look at.
        expect(panel.querySelector('.font-mono')?.textContent.trim()).toBeTruthy();
      }
    });
  }
});

/**
 * The same property, at the addresses that carry it onward: three of the
 * Settings pages render a screen the hybrid navigation retired from its own
 * address, unchanged, so a gateway that stopped answering still has to fail
 * inside a panel there rather than take the whole page down.
 */
describe('the Settings pages that reuse a retired screen', () => {
  const PAGES = [
    { id: 'settings-autonomy-guardrails', render: AutonomyGuardrailsPage },
    { id: 'settings-members-roles', render: MembersRolesPage },
    { id: 'settings-audit-log', render: AuditLogPage },
  ] as const;

  for (const page of PAGES) {
    it(`${page.id}: renders the page and fails inside its panels`, async () => {
      render(await page.render({ searchParams: Promise.resolve({}) }));

      expect(screen.getByTestId('page-header')).toBeInTheDocument();

      const panels = screen.getAllByTestId('panel');
      expect(panels.length).toBeGreaterThan(0);
      const failed = panels.filter(
        (panel) => panel.getAttribute('data-state') === 'error',
      );
      expect(failed.length).toBeGreaterThan(0);
    });
  }
});

/**
 * The same walk on the worst morning there is: nothing answers *and* nobody has
 * built an organisation tree, so no screen can even name the node it would ask
 * about. This is the state a deployment is in between being installed and being
 * configured, and it is the one the two broken routes were reachable in.
 */
describe('the shell with no gateway and no node', () => {
  beforeEach(() => {
    serveOutage(principalHolding(EVERYTHING, ''));
  });

  for (const area of AREAS.filter((each) => !HAS_NO_SCREEN.has(each.id))) {
    it(`${area.path}: still renders`, async () => {
      await renderArea(area.id);

      expect(screen.getByTestId('page-header')).toBeInTheDocument();
      expect(screen.getAllByTestId('panel').length).toBeGreaterThan(0);
    });
  }
});
