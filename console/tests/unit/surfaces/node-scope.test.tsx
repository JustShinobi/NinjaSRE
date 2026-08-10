import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

import { AREA_SCREENS } from '../support/screens';
import {
  principalHolding,
  serveScenario,
  serveScenarioExcept,
} from '../support/dataset';

/**
 * The screens whose data is scoped to a node, in the state where there is no
 * node.
 *
 * This is the initial state of a deployment nobody has configured yet: the
 * organisation tree is empty, so the principal resolves to no team node and the
 * address carries no `?node=`. A screen that reads a node-scoped endpoint
 * anyway builds `/v1/config/{node_id}/catalogue` with the brace still in it,
 * which throws before any request is made — and a throw is not a panel state,
 * it is the route boundary, which is an HTTP 500 on the very first page an
 * operator opens.
 *
 * So each node-scoped screen gets its own named case, and the list is written
 * out rather than derived: a screen becomes node-scoped by reading a
 * `{node_id}` endpoint, which is a fact about its source rather than about the
 * route manifest.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/** Every permission the dataset's operator holds, so nothing is hidden by a gate. */
const EVERYTHING = [
  'approval.read',
  'audit.read',
  'config.read',
  'config.write',
  'identity.read',
  'integration.manage',
  'investigation.read',
  'investigation.run',
  'knowledge.read',
  'memory.read',
  'remediation.approve',
  'remediation.execute',
  'schedule.manage',
  'token.manage',
];

/** The screens that read an endpoint with a `{node_id}` in it. */
const NODE_SCOPED = ['catalogue', 'autonomy', 'configuration'] as const;

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderArea(
  id: string,
  query: Readonly<Record<string, string>> = {},
): Promise<void> {
  const target = AREA_SCREENS.find((each) => each.id === id);
  if (target === undefined) throw new Error(`there is no ${id} screen`);
  render(await target.render({ searchParams: Promise.resolve(query) }));
}

describe('a node-scoped screen with no node selected', () => {
  beforeEach(() => {
    // The empty scenario's tree holds no nodes at all, and the principal
    // resolves to none — which is a deployment on its first morning, not a
    // fault.
    serveScenario('empty', principalHolding(EVERYTHING, ''));
  });

  for (const id of NODE_SCOPED) {
    it(`${id}: renders rather than throwing when no node resolves`, async () => {
      await renderArea(id);

      // The page is a page: the frame rendered, so the route did not fall
      // through to its error boundary.
      expect(screen.getByTestId('page-header')).toBeInTheDocument();

      // And the node-scoped regions say there is nothing here rather than
      // claiming the gateway let them down — nobody asked it anything.
      const panels = screen.getAllByTestId('panel');
      expect(panels.length).toBeGreaterThan(0);
      expect(
        panels.filter((panel) => panel.getAttribute('data-state') === 'empty').length,
      ).toBeGreaterThan(0);
      expect(
        panels.filter((panel) => panel.getAttribute('data-state') === 'error'),
      ).toEqual([]);
    });
  }
});

describe('a node-scoped screen resolving which node to read', () => {
  it('catalogue: reads the node the address names even for a viewer with no team', async () => {
    serveScenario('populated', principalHolding(EVERYTHING, ''));
    await renderArea('catalogue', { node: 'org-northwind' });

    expect(screen.getByTestId('page-header')).toBeInTheDocument();
    // Availability came back, which it only can if the entries read was made
    // with a node in it.
    const availability = screen
      .getAllByTestId('capability')
      .map((row) => row.textContent);
    expect(availability.length).toBeGreaterThan(0);
    expect(
      screen
        .getAllByTestId('panel')
        .filter((panel) => panel.getAttribute('data-state') === 'error'),
    ).toEqual([]);
  });

  it('autonomy: falls back to the root of the tree when the viewer has no team', async () => {
    serveScenario('populated', principalHolding(EVERYTHING, ''));
    await renderArea('autonomy');

    expect(screen.getByTestId('page-header')).toBeInTheDocument();
    // The root of the committed tree, reached without anybody naming it.
    expect(screen.getByTestId('page-header').textContent).toContain('org-northwind');
    expect(
      screen
        .getAllByTestId('panel')
        .filter((panel) => panel.getAttribute('data-state') === 'error'),
    ).toEqual([]);
  });
});

/**
 * One dependency down, and the rest of the deployment fine.
 *
 * A whole-gateway outage cannot tell these apart: a panel that reads two
 * endpoints renders its error state either way, whichever of the two it is
 * actually reporting. These are the cases that say which.
 */
describe('a node-scoped read that fails on its own', () => {
  it('catalogue: says the availability is unknown rather than showing none', async () => {
    serveScenarioExcept('populated', ['/catalogue'], principalHolding(EVERYTHING));
    await renderArea('catalogue');

    expect(screen.getByTestId('page-header')).toBeInTheDocument();
    // The capability panel, which reads capabilities *and* the entries that say
    // which of them are available here. Rendering the capability rows with a
    // blank availability column would be the screen saying "nothing is
    // configured" when what happened is that nobody answered.
    const failed = screen
      .getAllByTestId('panel')
      .filter((panel) => panel.getAttribute('data-state') === 'error');
    expect(failed.length).toBe(1);
    expect(failed[0]?.textContent).toContain('/v1/config/{node_id}/catalogue');
  });

  it('autonomy: keeps its node when the tree it did not need is unreachable', async () => {
    // The tree read is the node *selector*. Losing it must not cost the screen
    // the node it already had from the viewer.
    serveScenarioExcept('populated', ['/v1/config'], principalHolding(EVERYTHING));
    await renderArea('autonomy');

    expect(screen.getByTestId('page-header')).toBeInTheDocument();
    expect(
      screen
        .getAllByTestId('panel')
        .filter((panel) => panel.getAttribute('data-state') === 'error'),
    ).toEqual([]);
    expect(screen.getAllByTestId('autonomy-rule').length).toBeGreaterThan(0);
  });
});

/**
 * The breadcrumb, which is where a screen says which node it is showing.
 *
 * A trail whose last step is blank reads as a page that lost its subject, and
 * `trailFor` already draws no breadcrumb at all for a trail of one — so the
 * absence is the designed shape rather than a missing crumb.
 */
describe('the crumb naming the node', () => {
  it('autonomy: names the node it resolved', async () => {
    serveScenario('populated', principalHolding(EVERYTHING));
    await renderArea('autonomy', { node: 'team-storage' });

    const header = screen.getByTestId('page-header');
    const trail = header.querySelector('nav ol');
    expect(trail).not.toBeNull();
    expect(trail?.textContent).toContain('team-storage');
  });

  it('autonomy: draws no breadcrumb at all when it resolved none', async () => {
    serveScenario('empty', principalHolding(EVERYTHING, ''));
    await renderArea('autonomy');

    const header = screen.getByTestId('page-header');
    expect(header.querySelector('nav ol')).toBeNull();
  });
});
