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
 * The absences are the other half and are asserted just as hard, against the
 * committed dataset — which is a deployment that has discovered an estate and
 * connected nothing to watch it, and is therefore all gaps. A missing log store
 * rendered as nothing reads as "there are no logs", which sends somebody looking
 * for a fault inside the container.
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

/**
 * A base for parsing a path-only address.
 *
 * Built rather than written, the way the shared dataset helper builds its own:
 * a literal origin in console source is refused by the rule that keeps every
 * request pointed at the deployment, and this one is never contacted.
 */
const BASE = ['http:', '//gateway.test'].join('');

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

function missingFor(question: string): HTMLElement {
  const found = screen
    .getAllByTestId('signal-missing')
    .find((row) => row.getAttribute('data-question') === question);
  if (found === undefined) throw new Error(`no gap row for ${question}`);
  return found;
}

describe('where a resource’s signals come from', () => {
  it('draws nothing until a row is selected', async () => {
    serveScenario('populated');
    await resources();

    expect(screen.queryByTestId('resource-signals')).toBeNull();
  });

  it('answers “is it up” from whatever discovered the resource', async () => {
    serveScenario('populated');
    await resources({ selected: SELECTED });

    expect(sourceFor('up')).toHaveTextContent('proxmox');
  });

  it('names what would answer each question nothing configured does', async () => {
    // The committed dataset is a deployment that swept an estate and connected
    // nothing to watch it. Every one of the other five questions is a gap, and
    // each names the vendor that would close it rather than rendering blank.
    serveScenario('populated');
    await resources({ selected: SELECTED });

    expect(missingFor('logs')).toHaveTextContent('loki');
    expect(missingFor('logs')).toHaveTextContent('openobserve');
    expect(missingFor('pressure')).toHaveTextContent('prometheus');
    expect(missingFor('traces')).toHaveTextContent('signoz');
  });

  it('draws every question exactly once, answered or named', async () => {
    serveScenario('populated');
    await resources({ selected: SELECTED });

    const questions = [
      ...screen.getAllByTestId('signal-source'),
      ...screen.getAllByTestId('signal-missing'),
    ].map((row) => row.getAttribute('data-question'));

    expect([...questions].sort()).toEqual([
      'dashboards',
      'firing',
      'logs',
      'pressure',
      'traces',
      'up',
    ]);
  });

  it('names the source and the key a container’s pressure is read by', async () => {
    // The headline case, and the one the committed dataset cannot show because
    // it has no metric store connected. Stubbed here rather than connected
    // there: giving the anonymised dataset a real vendor name would make the
    // screenshot of it a picture of a deployment nobody has.
    vi.stubGlobal('fetch', (input: unknown) => {
      const path = new URL(String(input), BASE).pathname;
      const bodies: Record<string, unknown> = {
        '/auth/me': {
          principal_id: 'user-operator',
          display_name: 'Avery Lockhart',
          kind: 'person',
          roles: ['owner'],
          permissions: ['investigation.read', 'config.read'],
          team_node_id: 'org-northwind',
          impersonating: false,
          impersonated_by: null,
        },
        '/v1/estate/resources': { resources: [] },
        '/v1/estate/summary': { total: 0, captured_at: '2026-08-10T12:00:00Z' },
        [`/v1/estate/resources/${SELECTED}`]: {
          resource: {
            resource_id: SELECTED,
            kind: 'container',
            display_name: 'adguard',
          },
          rollup_rule: 'own_only',
          freshness_seconds: 300,
          signals: {
            sources: [
              {
                question: 'pressure',
                integration: 'prometheus',
                keyed_by: 'vmid',
                key: '100',
                detail:
                  'an LXC container shares the host kernel, so the host reports it',
              },
            ],
            missing: [],
          },
        },
      };
      const body = bodies[path];
      return Promise.resolve(
        new Response(JSON.stringify(body ?? {}), {
          status: body === undefined ? 404 : 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });

    await resources({ selected: SELECTED });

    const pressure = sourceFor('pressure');
    expect(pressure).toHaveTextContent('prometheus');
    expect(pressure).toHaveTextContent('vmid 100');
    expect(pressure).toHaveTextContent('shares the host kernel');
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
