import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { IntakeTab } from '@/surfaces/screens/data';

import { serveScenario, serveScenarioExcept } from '../support/dataset';

/**
 * Where an alert router posts, and whether anything ever came of it.
 *
 * The one step of this whole loop that happens outside the deployment is
 * somebody configuring a receiver in Alertmanager. Everything the console can
 * do about that is say precisely what to paste — the address, the body it will
 * parse, and how the delivery is trusted — and then say whether it worked.
 *
 * These assertions moved here from the catalogue with 062. The panel that says
 * what to paste and the column that says what arrived are two halves of one
 * question, and the operator asking it is standing on this screen.
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

async function data(): Promise<void> {
  render(await IntakeTab(await surfaceContext({})));
}

function sourceRow(name: string): HTMLElement | undefined {
  return screen
    .getAllByTestId('ingress-source')
    .find((row) => row.getAttribute('data-source') === name);
}

describe('where an alert router posts', () => {
  it('lists every receiver this deployment serves', async () => {
    serveScenario('populated');
    await data();

    expect(screen.getAllByTestId('ingress-source').length).toBe(7);
  });

  it('gives the whole address rather than a path to assemble', async () => {
    serveScenario('populated');
    await data();

    const alertmanager = sourceRow('alertmanager');
    expect(alertmanager).toBeDefined();
    expect(alertmanager).toHaveTextContent('/webhooks/alertmanager');
    expect(alertmanager?.textContent).toContain('http');
  });

  it('names the body each receiver parses', async () => {
    serveScenario('populated');
    await data();

    expect(sourceRow('alertmanager')).toHaveTextContent('groupKey');
  });

  it('says how a delivery is trusted, so nobody guesses the header', async () => {
    serveScenario('populated');
    await data();

    expect(screen.getByTestId('ingress-sources')).toHaveTextContent('Authorization');
  });

  it('shows the receivers on a deployment with nothing connected yet', async () => {
    // The receivers are routes this build serves, not something configured, so
    // the screen an operator opens on day one is exactly where this belongs.
    serveScenario('empty');
    await data();

    expect(screen.getAllByTestId('ingress-source').length).toBe(7);
  });

  it('draws no paste-ready address when the deployment will not answer for it', async () => {
    serveScenarioExcept('populated', ['/v1/ingress/sources']);
    await data();

    // The column is still there — its own read answered — and the absolute URL
    // an operator pastes is the one thing missing, which is the honest failure.
    expect(screen.getAllByTestId('ingress-source').length).toBe(7);
    expect(screen.queryAllByTestId('ingress-url')).toEqual([]);
  });
});
