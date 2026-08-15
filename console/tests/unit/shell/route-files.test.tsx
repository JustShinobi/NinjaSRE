import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { message } from '@/i18n/messages';
import { AREAS, areaFor } from '@/shell/routes';
import { SESSION_COOKIE } from '@/session/cookies';

import AdministrationPage from '@/app/(shell)/administration/page';
import AutonomyPage from '@/app/(shell)/autonomy/page';
import FirstRunPage from '@/app/(shell)/first-run/page';
import SignalsPage from '@/app/(shell)/signals/page';

import { AREA_SCREENS } from '../support/screens';
import { serveScenario } from '../support/dataset';

/**
 * Every route file, opened directly.
 *
 * A deep link is a cold render of one route file, so this imports each and
 * renders it — no shell, no navigation, nothing warmed up. The point is the
 * completeness check underneath: `AREA_SCREENS` (`../support/screens.ts`,
 * which every cross-cutting proof in this suite shares) is compared against
 * the manifest, so an area added without a route file fails, and a route
 * file added without an entry in the manifest fails too — modulo `settings`,
 * whose own route file only ever redirects.
 *
 * `signals`, `autonomy`, `administration` are *not* excluded here: their own
 * address (`/signals`, `/autonomy`, `/administration`) now redirects to a
 * Settings page, but `AREA_SCREENS`'s entries for the three call the screen
 * function directly rather than the redirecting page file (`screens.ts`
 * explains why), so "renders cold, with its own title" is still a true thing
 * to assert about them. `describe('a retired route file')` below is what
 * covers the redirect itself, against the actual page files.
 *
 * `redirect` itself is not mocked here: `tests/unit/setup.ts` already mocks
 * `next/navigation` for the whole suite, and its `redirect` throws
 * `redirected to ${href}` — the floor a file about navigation is free to
 * override and this one does not need to, because that throw is exactly the
 * proof a redirect test wants.
 */

/**
 * The one area with no screen at all: `settings` only ever redirects, to
 * whichever Settings page is first for the viewer, so `AREA_SCREENS` carries
 * no entry for it (`screens.ts` explains why) and it is excluded from the
 * bijection below for the same reason.
 */
const HAS_NO_SCREEN = new Set(['settings']);

/**
 * `first-run` renders normally under every scenario `AREA_SCREENS`'s other
 * consumers serve it against, but not under this file's own: `populated` —
 * what this file serves throughout — carries `"complete": true`
 * (`fixtures/scenarios/populated/setup-checklist.json`), and a complete
 * checklist is exactly what sends this one route to the dashboard instead of
 * rendering. Excluded from *this file's own* "renders cold" loop only, not
 * from `AREA_SCREENS` itself. `describe('the first-run route, both ways')`
 * below covers both of its states explicitly instead of leaving it to a loop
 * that can only ever serve one scenario at a time.
 */
const RENDERS_COLD_UNDER_A_DIFFERENT_SCENARIO = new Set(['first-run']);

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      // The credential a signed-in request carries. The pages resolve the viewer
      // themselves rather than trusting the layout to have done it, because a
      // client-side transition fetches the page segment alone.
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
  serveScenario('populated');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the route files and the manifest', () => {
  it('are the same set, once the screen-less area is set aside', () => {
    const renders = AREAS.map((area) => area.id)
      .sort()
      .filter((id) => !HAS_NO_SCREEN.has(id));
    expect(AREA_SCREENS.map((file) => file.id).sort()).toEqual(renders);
  });

  it('never sets an id aside that the manifest does not still declare', () => {
    // The exclusion above is only honest if every id it names is still a real
    // area — a typo'd id here would silently stop covering an area that
    // still renders normally.
    for (const id of HAS_NO_SCREEN) {
      expect(
        AREAS.map((area) => area.id),
        id,
      ).toContain(id);
    }
  });
});

describe('a deep link to every route', () => {
  it.each(
    AREA_SCREENS.filter(
      (file) => !RENDERS_COLD_UNDER_A_DIFFERENT_SCENARIO.has(file.id),
    ).map((file) => [file.id, file] as const),
  )('%s renders cold, with its own title', async (id, file) => {
    // Awaited, because a route file is an async server component: what a cold
    // request renders is what the page resolves to, not the page itself.
    render(await file.render({ searchParams: Promise.resolve({}) }));

    expect(screen.getByTestId('page-header')).toHaveAttribute('data-area', id);
    if (file.metadata === undefined) throw new Error(`${id} declares no metadata`);
    expect(await file.metadata()).toMatchObject({
      title: `${message('en', areaFor(id).title)} · HAL9000`,
    });
  });
});

describe('a retired route file', () => {
  it('sends /autonomy to its Settings address', async () => {
    await expect(AutonomyPage({ searchParams: Promise.resolve({}) })).rejects.toThrow(
      'redirected to /settings/autonomy-guardrails',
    );
  });

  it.each([
    [{}, '/settings/members-roles'],
    [{ tab: 'people' }, '/settings/members-roles'],
    [{ tab: 'audit' }, '/settings/audit-log'],
    // A filter carried on the audit tab survives the hop, so a link into a
    // filtered view of the old screen still lands on the same filtered view
    // of its replacement rather than losing the filter on the way.
    [{ tab: 'audit', actor: 'avery' }, '/settings/audit-log?actor=avery'],
  ])('sends /administration%s to its Settings address', async (params, target) => {
    await expect(
      AdministrationPage({ searchParams: Promise.resolve(params) }),
    ).rejects.toThrow(`redirected to ${target}`);
  });

  it.each([
    [{}, '/settings/alert-intake'],
    [{ tab: 'intake' }, '/settings/alert-intake'],
    [{ tab: 'destinations' }, '/settings/schedules-destinations'],
    [{ tab: 'schedules' }, '/settings/schedules-destinations'],
  ])('sends /signals%s to its Settings address', async (params, target) => {
    await expect(
      SignalsPage({ searchParams: Promise.resolve(params) }),
    ).rejects.toThrow(`redirected to ${target}`);
  });

  it('renders /signals?tab=observation as it always has, rather than redirecting it away', async () => {
    // A deliberate, committed exception, not an oversight: nothing in the
    // nine Settings pages replaces continuous observation, and
    // `emptiness.ts`'s `watchingCause` still sends a viewer to exactly this
    // address. Redirecting it would land that CTA on a page saying something
    // else is missing.
    render(
      await SignalsPage({ searchParams: Promise.resolve({ tab: 'observation' }) }),
    );

    expect(screen.getByTestId('page-header')).toHaveAttribute('data-area', 'signals');
  });
});

describe('the first-run route, both ways', () => {
  it('sends a deployment with a complete checklist to the dashboard', async () => {
    // The default scenario this file serves throughout: complete.
    await expect(FirstRunPage({ searchParams: Promise.resolve({}) })).rejects.toThrow(
      'redirected to /',
    );
  });

  it('still renders the wizard while the checklist has something left', async () => {
    serveScenario('first-run');
    render(await FirstRunPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByTestId('page-header')).toHaveAttribute('data-area', 'first-run');
  });
});
