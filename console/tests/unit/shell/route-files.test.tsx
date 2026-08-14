import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { message } from '@/i18n/messages';
import { AREAS, areaFor } from '@/shell/routes';
import { SESSION_COOKIE } from '@/session/cookies';

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
 * file added without an entry in the manifest fails too.
 */

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
  it('are the same set, so neither can gain an entry alone', () => {
    expect(AREA_SCREENS.map((file) => file.id).sort()).toEqual(
      AREAS.map((area) => area.id).sort(),
    );
  });
});

describe('a deep link to every route', () => {
  it.each(AREA_SCREENS.map((file) => [file.id, file] as const))(
    '%s renders cold, with its own title',
    async (id, file) => {
      // Awaited, because a route file is an async server component: what a cold
      // request renders is what the page resolves to, not the page itself.
      render(await file.render({ searchParams: Promise.resolve({}) }));

      expect(screen.getByTestId('page-header')).toHaveAttribute('data-area', id);
      if (file.metadata === undefined) throw new Error(`${id} declares no metadata`);
      expect(await file.metadata()).toMatchObject({
        title: `${message('en', areaFor(id).title)} · HAL9000`,
      });
    },
  );
});
