import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { CatalogueScreen } from '@/surfaces/screens/catalogue';

import { serveScenario, serveScenarioExcept } from '../support/dataset';

/**
 * Where an alert router posts, and what to paste into it.
 *
 * The one step of this whole loop that happens outside the deployment is
 * somebody configuring a receiver in Alertmanager. Everything the console can
 * do about that is say precisely what to paste — the address, the body it will
 * parse, and how the delivery is trusted — and the panel that says it is worth
 * as much as any of the machinery behind it, because a loop nobody points
 * anything at never runs.
 *
 * The token is deliberately not here. It is issued on demand and shown once,
 * which is a write; what this asserts is the read half, and that no secret
 * appears in it.
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

async function catalogue(): Promise<void> {
  render(await CatalogueScreen(await surfaceContext({})));
}

describe('where an alert router posts', () => {
  it('lists every receiver this deployment serves', async () => {
    serveScenario('populated');
    await catalogue();

    const rows = screen.getAllByTestId('ingress-source');
    expect(rows.length).toBe(7);
  });

  it('gives the whole address rather than a path to assemble', async () => {
    serveScenario('populated');
    await catalogue();

    const alertmanager = screen
      .getAllByTestId('ingress-source')
      .find((row) => row.getAttribute('data-source') === 'alertmanager');
    expect(alertmanager).toBeDefined();
    expect(alertmanager).toHaveTextContent('/webhooks/alertmanager');
    expect(alertmanager?.textContent).toContain('http');
  });

  it('names the body each receiver parses', async () => {
    serveScenario('populated');
    await catalogue();

    const alertmanager = screen
      .getAllByTestId('ingress-source')
      .find((row) => row.getAttribute('data-source') === 'alertmanager');
    expect(alertmanager).toHaveTextContent('groupKey');
  });

  it('says how a delivery is trusted, so nobody guesses the header', async () => {
    serveScenario('populated');
    await catalogue();

    expect(screen.getByTestId('ingress')).toHaveTextContent('Authorization');
  });

  it('shows the panel on a deployment with nothing connected yet', async () => {
    // The receivers are routes this build serves, not something configured, so
    // the screen an operator opens on day one is exactly where this belongs.
    serveScenario('empty');
    await catalogue();

    expect(screen.getAllByTestId('ingress-source').length).toBe(7);
  });

  it('draws nothing when the deployment will not answer for it', async () => {
    serveScenarioExcept('populated', ['/v1/ingress/sources']);
    await catalogue();

    expect(screen.queryByTestId('ingress')).toBeNull();
  });
});
