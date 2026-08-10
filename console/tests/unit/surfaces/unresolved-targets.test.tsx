import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { ResourcesScreen } from '@/surfaces/screens/resources';

import { serveScenario, serveScenarioExcept } from '../support/dataset';

/**
 * Alerts that arrived for something this estate does not hold.
 *
 * The same class of thing as the inventory divergence beside it, and it earns a
 * panel for the same reason: there is no row to mark. An alert for a guest
 * nothing swept has no resource to hang a mark on, and the two facts it can mean
 * — a machine nobody discovered, or a receiver pointed at the wrong deployment —
 * are both worth someone's morning.
 *
 * The failure this replaces is silence. Before resolution existed the alert
 * still opened an investigation, about a label value, and nothing anywhere said
 * that the deployment had never heard of it.
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

async function resources(): Promise<void> {
  render(await ResourcesScreen(await surfaceContext({})));
}

describe('alert targets this estate does not hold', () => {
  it('names every one of them, and what the alert was', async () => {
    serveScenario('populated');
    await resources();

    const entries = screen.getAllByTestId('unresolved-target-entry');
    expect(entries.length).toBeGreaterThan(0);
    expect(entries[0]).toHaveTextContent('vmid');
  });

  it('says why it could not be resolved rather than only that it was not', async () => {
    serveScenario('populated');
    await resources();

    expect(screen.getByTestId('unresolved-targets')).toHaveTextContent(
      'no guest in this estate carries that identifier',
    );
  });

  it('draws no panel when every alert resolved', async () => {
    serveScenario('empty');
    await resources();

    expect(screen.queryByTestId('unresolved-targets')).toBeNull();
  });

  it('draws no panel when the deployment will not answer for it', async () => {
    serveScenarioExcept('populated', ['/v1/estate/unresolved-alert-targets']);
    await resources();

    expect(screen.queryByTestId('unresolved-targets')).toBeNull();
  });
});
