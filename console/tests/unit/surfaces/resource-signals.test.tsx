import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { ResourcesScreen } from '@/surfaces/screens/resources';

import { serveScenario, serveScenarioExcept } from '../support/dataset';

/**
 * Where a selected resource's signals come from.
 *
 * The panel exists for one number. Asked how much memory a container is using,
 * something reading from inside the container answers from cgroup accounting
 * seen through a namespace that was never built to publish it — and the answer
 * is wrong, plausible, and indistinguishable from the right one. The deployment
 * derives the map; these assert the console shows it *keyed*, rather than
 * showing the question with a blank beside it.
 *
 * The absences are the other half and are asserted just as hard. A missing log
 * store rendered as nothing reads as "there are no logs", which sends somebody
 * looking for a fault inside the container.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/** The container the committed dataset carries a detail for. */
const SELECTED = 'ct-100';

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function resources(query: Record<string, string> = {}): Promise<void> {
  render(await ResourcesScreen(await surfaceContext(query)));
}

function sourceFor(question: string): HTMLElement {
  const found = screen
    .getAllByTestId('signal-source')
    .find((row) => row.getAttribute('data-question') === question);
  if (found === undefined) throw new Error(`no source row for ${question}`);
  return found;
}

describe('where a resource’s signals come from', () => {
  it('draws nothing until a row is selected', async () => {
    serveScenario('populated');
    await resources();

    expect(screen.queryByTestId('resource-signals')).toBeNull();
  });

  it('names the source and the key a container’s pressure is read by', async () => {
    serveScenario('populated');
    await resources({ selected: SELECTED });

    const pressure = sourceFor('pressure');
    expect(pressure).toHaveTextContent('prometheus');
    expect(pressure).toHaveTextContent('vmid 100');
    expect(pressure).toHaveTextContent('shares the host');
  });

  it('answers “is it up” and “what did it write down” for a watched resource', async () => {
    serveScenario('populated');
    await resources({ selected: SELECTED });

    expect(sourceFor('up')).toHaveTextContent('proxmox');
    expect(sourceFor('logs')).toHaveTextContent('loki');
  });

  it('names what would answer a question nothing configured does', async () => {
    serveScenario('populated');
    await resources({ selected: SELECTED });

    const missing = screen.getAllByTestId('signal-missing');
    const questions = missing.map((row) => row.getAttribute('data-question'));
    expect(questions).toContain('traces');
    expect(missing.map((row) => row.textContent).join(' ')).toContain('signoz');
  });

  it('does not lose the whole screen when the detail read is refused', async () => {
    // A deployment on an older build serves no such route. The listing is still
    // the answer to the question this screen is for, and losing it over one
    // panel would be the console deciding an optional read is mandatory.
    serveScenarioExcept('populated', ['/v1/estate/resources/']);
    await resources({ selected: SELECTED });

    expect(screen.getAllByTestId('row').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('signal-source')).toBeNull();
  });
});
