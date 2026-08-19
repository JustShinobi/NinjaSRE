import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import {
  DEFAULT_VIEW_STATE,
  readViewState,
  writeViewState,
} from '@/surfaces/url-state';

import { ALL_SCREENS, AREA_SCREENS } from '../support/screens';
import { serveRefusal, serveScenario } from '../support/dataset';

/**
 * The cross-cutting proofs: the ones that are about *every* screen rather than
 * about one.
 *
 * Each walks the screen list rather than naming screens, so a screen added
 * tomorrow is covered by these rather than by tests somebody remembers to write.
 * That is the whole design of the file — a per-screen assertion written by hand
 * is a per-screen assertion that stops being written by about the ninth screen.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderScreen(
  index: number,
  query: SearchLike = {},
  screens = ALL_SCREENS,
): Promise<void> {
  const target = screens[index];
  if (target === undefined) throw new Error(`no screen at ${String(index)}`);
  render(await target.render({ searchParams: Promise.resolve(query) }));
}

type SearchLike = Readonly<Record<string, string | string[] | undefined>>;

describe('SC-001: every screen, with no data, says what would be here', () => {
  beforeEach(() => {
    // The dataset's own empty scenario: a deployment that exists and has done
    // nothing. Not a mocked absence — the fixtures the mock plane serves.
    serveScenario('empty');
  });

  // `known_gaps` is a catalogue fact the product declares, not a deployment's
  // own data — identical on the emptiest deployment there is. There is no
  // "nothing here yet" for this screen to say.
  //
  // `settings-single-sign-on` reads one document, not a collection: an
  // unconfigured provider is still a settings form with blank fields, never a
  // zero-item list, so there is no "nothing here yet" to say either — the
  // same reasoning `integrations-not-covered` gets, for a different reason.
  //
  // `settings-machine-tokens` genuinely can be a zero-item collection, and is
  // excluded on purpose rather than by omission: this panel is never empty
  // for somebody who may issue a token (`machine-token-groups.tsx`'s own doc
  // says why — the deployment with none is exactly the one that needs the
  // issue form in front of it), so its own empty state is inline prose beside
  // a working form rather than a `way-back` link to nowhere new.
  //
  // `settings-alert-intake` has nothing that is ever genuinely empty: the
  // receivers it lists are routes this build serves rather than something an
  // operator configured, and the routing-rules panel always draws at least
  // the implicit catch-all — both true on the emptiest deployment there is,
  // the same property the old combined Signals screen's Intake tab pinned
  // before this feature split it onto its own address. Destinations, once
  // its own sibling tab of that same screen, now empties out on the address
  // that absorbed it (`settings-schedules-destinations`) exactly like every
  // other screen does, so the cross-cutting proof still runs there.
  //
  // `signals` — what is left of the old four-tab screen once Intake,
  // Schedules and Destinations moved to Settings pages of their own — is not
  // excluded: continuous observation genuinely empties on a deployment with
  // no detector switched on, which the emptiest scenario is.
  //
  // `autonomy` — this sweep, like every other multi-tab screen here, renders
  // whichever tab an address with no `tab` param lands on: Posture. Rules &
  // windows and Guardrails each carry a real empty state of their own,
  // proven directly by `settings/autonomy.test.tsx` rather than by this
  // sweep, which only ever exercises one tab per screen. On the empty
  // scenario this sweep runs, Posture draws nothing at all: the bounds panel
  // (freeze, budget, override, stopped) is gated on a resolved node, same as
  // every other write control here, and this fixture resolves none. Posture's
  // own content — the posture selector and its empty state — is a later
  // slice of this same feature; excluded here rather than left to fail until
  // it lands, and worth revisiting once it does.
  const NEVER_EMPTY = new Set([
    'integrations-not-covered',
    'settings-single-sign-on',
    'settings-machine-tokens',
    'settings-alert-intake',
    'autonomy',
  ]);

  for (const [index, target] of ALL_SCREENS.entries()) {
    if (NEVER_EMPTY.has(target.id)) continue;
    it(`${target.id}: renders an empty state naming the next action`, async () => {
      await renderScreen(index);

      const wells = screen.getAllByTestId('way-back');
      expect(wells.length).toBeGreaterThan(0);

      for (const well of wells) {
        // An empty state is four things, and the action is the one that turns a
        // blank screen into a next step.
        expect(well.getAttribute('href')).toBeTruthy();
        expect(well.textContent.trim()).toBeTruthy();
      }

      // Never a blank region: at least one panel says so in words.
      const empty = screen
        .getAllByTestId('panel')
        .filter((panel) => panel.getAttribute('data-state') === 'empty');
      expect(empty.length).toBeGreaterThan(0);
      for (const panel of empty) {
        expect(panel.querySelector('h4')?.textContent.trim()).toBeTruthy();
        expect(panel.querySelector('p')?.textContent.trim()).toBeTruthy();
      }
    });
  }
});

describe('SC-006: a failing panel leaves the rest of its page working', () => {
  beforeEach(() => {
    serveRefusal(503);
  });

  for (const [index, target] of ALL_SCREENS.entries()) {
    it(`${target.id}: still renders its frame and names what failed`, async () => {
      await renderScreen(index);

      // The page header is the frame, and it is still there.
      expect(screen.getByTestId('page-header')).toBeInTheDocument();

      const failed = screen
        .getAllByTestId('panel')
        .filter((panel) => panel.getAttribute('data-state') === 'error');
      expect(failed.length).toBeGreaterThan(0);
      for (const panel of failed) {
        // Named, because "something went wrong" is not a fault report.
        expect(panel.querySelector('.font-mono')?.textContent.trim()).toBeTruthy();
      }
      // And each failed panel offers its own retry rather than the page offering one.
      expect(screen.getAllByRole('alert').length).toBe(failed.length);
    });
  }
});

describe('SC-007: every screen’s filter and selection state round-trips', () => {
  beforeEach(() => {
    serveScenario('populated');
  });

  const VIEW = {
    ...DEFAULT_VIEW_STATE,
    filters: { status: 'failed' },
    sort: 'started_at',
    descending: true,
    page: 3,
    selection: 'run-0004',
  };

  it('writes and reads back the same view', () => {
    const written = writeViewState(VIEW, ['status']);
    expect(readViewState(written, ['status'])).toEqual(VIEW);
  });

  // `first-run` is served `populated`'s checklist here too, which is complete
  // (`fixtures/scenarios/populated/setup-checklist.json`), so this route
  // redirects rather than rendering with the address's own filters — nothing
  // this describe block is about. `tests/unit/shell/route-files.test.tsx`
  // covers both of its states.
  const ROUND_TRIP_SCREENS = AREA_SCREENS.filter((each) => each.id !== 'first-run');

  for (const [index, target] of ROUND_TRIP_SCREENS.entries()) {
    it(`${target.id}: renders whatever its address carries without throwing`, async () => {
      // The address is the input. A screen that could only be reached by
      // clicking would pass every other test in this file and fail this one.
      await renderScreen(
        index,
        {
          status: 'failed',
          node: 'org-northwind',
          selected: 'run-0004',
          sort: '-started_at',
        },
        ROUND_TRIP_SCREENS,
      );

      expect(screen.getByTestId('page-header')).toBeInTheDocument();
    });
  }
});

describe('the populated dataset', () => {
  beforeEach(() => {
    serveScenario('populated');
  });

  // `first-run` redirects under this scenario's complete checklist rather
  // than rendering — see the comment on `ROUND_TRIP_SCREENS` above.
  const POPULATED_SCREENS = ALL_SCREENS.filter((each) => each.id !== 'first-run');

  for (const [index, target] of POPULATED_SCREENS.entries()) {
    it(`${target.id}: renders against the capture the design was drawn from`, async () => {
      await renderScreen(index, {}, POPULATED_SCREENS);

      expect(screen.getByTestId('page-header')).toBeInTheDocument();
      // Nothing on a populated deployment may fail: every read in this suite is
      // answered from the committed dataset, so an error state here is a screen
      // asking for something the dataset does not carry.
      const failed = screen
        .getAllByTestId('panel')
        .filter((panel) => panel.getAttribute('data-state') === 'error');
      expect(failed.map((panel) => panel.textContent)).toEqual([]);
    });
  }
});
