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

  for (const [index, target] of ALL_SCREENS.entries()) {
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

  for (const [index, target] of AREA_SCREENS.entries()) {
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
        AREA_SCREENS,
      );

      expect(screen.getByTestId('page-header')).toBeInTheDocument();
    });
  }
});

describe('the populated dataset', () => {
  beforeEach(() => {
    serveScenario('populated');
  });

  for (const [index, target] of ALL_SCREENS.entries()) {
    it(`${target.id}: renders against the capture the design was drawn from`, async () => {
      await renderScreen(index);

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
