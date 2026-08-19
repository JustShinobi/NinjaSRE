import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { message } from '@/i18n/messages';
import { AREAS, areaFor, settingsPageFor } from '@/shell/routes';
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
 * The areas with no screen at all, both of which only ever redirect, so
 * `AREA_SCREENS` carries no entry for either (`screens.ts` explains why) and
 * both are excluded from the bijection below for the same reason.
 *
 * `settings` redirects to whichever Settings page is first for the viewer.
 * `configuration` is the retired raw editor: every field it could reach is
 * now edited on the page that owns its subject, and its address forwards to
 * that page rather than rendering anything of its own.
 */
const HAS_NO_SCREEN = new Set(['settings', 'configuration']);

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

/**
 * `autonomy` renders normally under this file's own scenario, but the loop's
 * assertion — `data-area` equals the area id, and the metadata title is the
 * *area's* title — stopped being its own shape the day it was rebuilt as the
 * Settings page's own screen. Its header is `SettingsPageHeader`, which
 * carries the *Settings page's* id and title rather than the area's.
 * `describe('the autonomy Settings page, cold')` below covers it with the
 * assertion that is actually true of it now.
 *
 * The four `settings-*` ids Administration desmembered into carry the same
 * shape, for the same reason: each renders under `SettingsPageHeader`, with
 * its own Settings page id and title rather than any area's.
 * `describe('the Organization Settings pages, cold')` below covers them —
 * `administration` itself renders the identical `MembersScreen` one of the
 * four already does (`settings-members-roles`), so that same assertion
 * already proves it true at this old id too, without a second, redundant one.
 *
 * `settings-alert-intake` and `settings-schedules-destinations` carry the
 * same shape again: both render under `SettingsPageHeader`, in the Data
 * group of the same subnav, never under `AREAS`.
 * `describe('the Data Settings pages, cold')` covers them.
 */
const HEADER_IS_NOT_THE_AREAS_OWN = new Set([
  'autonomy',
  'administration',
  'settings-members-roles',
  'settings-single-sign-on',
  'settings-machine-tokens',
  'settings-audit-log',
  'settings-alert-intake',
  'settings-schedules-destinations',
]);

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
  it('covers every area once the screen-less one is set aside', () => {
    // A subset check rather than an equal set: `AREA_SCREENS` also carries
    // the four `settings-*` entries Administration desmembered into, which
    // have no area of their own — the completeness this guards is "every
    // area renders", not "AREA_SCREENS contains nothing else".
    const renders = new Set(AREA_SCREENS.map((file) => file.id));
    for (const area of AREAS) {
      if (HAS_NO_SCREEN.has(area.id)) continue;
      expect(renders.has(area.id), `${area.id} has no matching screen`).toBe(true);
    }
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
      (file) =>
        !RENDERS_COLD_UNDER_A_DIFFERENT_SCENARIO.has(file.id) &&
        !HEADER_IS_NOT_THE_AREAS_OWN.has(file.id),
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

describe('the autonomy Settings page, cold', () => {
  it('renders cold, with the Settings page’s own id and title rather than the area’s', async () => {
    const target = AREA_SCREENS.find((file) => file.id === 'autonomy');
    if (target === undefined) throw new Error('no autonomy screen in AREA_SCREENS');

    render(await target.render({ searchParams: Promise.resolve({}) }));

    expect(screen.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-autonomy-guardrails',
    );
    if (target.metadata === undefined) throw new Error('autonomy declares no metadata');
    expect(await target.metadata()).toMatchObject({
      title: `Autonomy & guardrails · HAL9000`,
    });
  });
});

describe('the Organization Settings pages, cold', () => {
  it.each([
    'settings-members-roles',
    'settings-single-sign-on',
    'settings-machine-tokens',
    'settings-audit-log',
  ] as const)(
    '%s renders cold, with the Settings page’s own id and title',
    async (id) => {
      const target = AREA_SCREENS.find((file) => file.id === id);
      if (target === undefined) throw new Error(`no ${id} screen in AREA_SCREENS`);

      render(await target.render({ searchParams: Promise.resolve({}) }));

      expect(screen.getByTestId('page-header')).toHaveAttribute('data-area', id);
      if (target.metadata === undefined) throw new Error(`${id} declares no metadata`);
      expect(await target.metadata()).toMatchObject({
        title: `${message('en', settingsPageFor(id).label)} · HAL9000`,
      });
    },
  );
});

describe('the Data Settings pages, cold', () => {
  it.each(['settings-alert-intake', 'settings-schedules-destinations'] as const)(
    '%s renders cold, with the Settings page’s own id and title',
    async (id) => {
      const target = AREA_SCREENS.find((file) => file.id === id);
      if (target === undefined) throw new Error(`no ${id} screen in AREA_SCREENS`);

      render(await target.render({ searchParams: Promise.resolve({}) }));

      expect(screen.getByTestId('page-header')).toHaveAttribute('data-area', id);
      if (target.metadata === undefined) throw new Error(`${id} declares no metadata`);
      expect(await target.metadata()).toMatchObject({
        title: `${message('en', settingsPageFor(id).label)} · HAL9000`,
      });
    },
  );
});

describe('a retired route file', () => {
  it.each([
    [{}, '/settings/autonomy-guardrails'],
    // The scope node this address always carried, and the tab the
    // destination now understands natively — `/autonomy` never had a
    // competing meaning for `tab` of its own, unlike `/administration` and
    // `/signals` below, so both ride along rather than only one of them.
    [{ node: 'org-northwind' }, '/settings/autonomy-guardrails?node=org-northwind'],
    [
      { node: 'org-northwind', tab: 'guardrails' },
      '/settings/autonomy-guardrails?node=org-northwind&tab=guardrails',
    ],
  ])('sends /autonomy%s to its Settings address', async (params, target) => {
    await expect(
      AutonomyPage({ searchParams: Promise.resolve(params) }),
    ).rejects.toThrow(`redirected to ${target}`);
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
