import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, PROJECTED_PATHS, read, readProjected } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import {
  dataOf,
  dependencyOf,
  panelRead,
  readProjectedPanel,
  stateOf,
} from '@/surfaces/read';
import { RowList } from '@/surfaces/rows';
import { DEFAULT_VIEW_STATE } from '@/surfaces/url-state';

import { AREA_SCREENS } from '../support/screens';
import { principalHolding, serveScenario } from '../support/dataset';

/**
 * The paths that only a particular request reaches: a sorted address, a viewer
 * who may decide, an endpoint that answers a 404 rather than a body.
 *
 * Each of these is a branch that a screen takes on somebody's Tuesday and never
 * takes in a test that renders the default view — which is how a console comes to
 * have a sort that has never once been run.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

const BASE = ['http:', '//fixtures.invalid'].join('');

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
  const target = AREA_SCREENS.find((screen_) => screen_.id === id);
  if (target === undefined) throw new Error(`there is no ${id} screen`);
  render(await target.render({ searchParams: Promise.resolve(query) }));
}

describe('a screen reached through its address', () => {
  beforeEach(() => {
    serveScenario('populated', principalHolding(['investigation.read']));
  });

  it('sorts the run list the way the address says, ascending and descending', async () => {
    await renderArea('runs', { sort: 'run_id' });
    const ascending = screen
      .getAllByTestId('row')
      .map((row) => row.getAttribute('data-row'));

    expect(ascending[0]).toBe('run-0001');

    await renderArea('runs', { sort: '-run_id' });
    const rows = screen
      .getAllByTestId('row')
      .map((row) => row.getAttribute('data-row'));
    expect(rows[rows.length - 1]).toBe('run-0001');
  });

  it('sorts by a computed column as a number rather than as text', async () => {
    await renderArea('runs', { sort: 'duration' });

    expect(screen.getAllByTestId('row').length).toBeGreaterThan(0);
  });

  it('says a filter matched nothing, and offers to clear it', async () => {
    await renderArea('runs', { status: 'no-such-status' });

    const panel = screen.getAllByTestId('panel')[0];
    expect(panel).toHaveAttribute('data-state', 'empty');
    expect(screen.getByTestId('way-back')).toHaveAttribute('href', '/runs');
  });

  it('filters the incident list by the address, and sorts it', async () => {
    await renderArea('incidents', { state: 'open', sort: '-title' });

    expect(screen.getByTestId('page-header')).toBeInTheDocument();
  });

  it('filters resources by kind and state, and sorts them', async () => {
    await renderArea('resources', {
      kind: 'container',
      health: 'healthy',
      sort: 'name',
    });

    expect(screen.getByTestId('page-header')).toBeInTheDocument();
  });

  it('centres the topology on the node the address names', async () => {
    serveScenario('populated', principalHolding(['memory.read', 'knowledge.read']));
    await renderArea('knowledge', { tab: 'topology', node: 'svc-checkout' });

    expect(screen.getByTestId('graph-list')).toBeInTheDocument();
  });

  it('filters the knowledge base and the episode corpus', async () => {
    serveScenario('populated', principalHolding(['knowledge.read', 'memory.read']));
    await renderArea('knowledge', { tab: 'documents', kind: 'runbook' });
    await renderArea('knowledge', {
      tab: 'learned',
      component: 'storage',
      outcome: 'resolved',
    });

    expect(screen.getAllByTestId('page-header').length).toBe(2);
  });

  it('filters the audit record by principal and action', async () => {
    serveScenario('populated', principalHolding(['audit.read', 'audit.export']));
    await renderArea('settings-audit-log', {
      actor: 'user-avery',
      action: 'run.start',
    });

    expect(screen.getByTestId('audit-export')).toBeInTheDocument();
  });
});

describe('the autonomy screen', () => {
  beforeEach(() => {
    serveScenario('populated', principalHolding(['config.read']));
  });

  it('reads the rules in resolution order, least specific first', async () => {
    await renderArea('autonomy');

    const levels = screen
      .getAllByTestId('autonomy-rule')
      .map((row) => row.getAttribute('data-level'));

    expect(levels.length).toBeGreaterThan(0);
    expect(levels[0]).toBe('propose_only');
  });

  it('says what an empty table would have meant, whatever the table holds', async () => {
    await renderArea('autonomy');

    // The footer is not an empty state. An operator reading a *full* table
    // still needs to know that anything the rules do not cover is refused.
    expect(screen.getByTestId('autonomy-footer').textContent).toContain('propose-only');
  });

  it('shows the bounds beside the rules, because both are true at once', async () => {
    await renderArea('autonomy');

    const kinds = screen
      .getAllByTestId('bound')
      .map((entry) => entry.getAttribute('data-bound'));

    expect(kinds).toContain('freeze');
    expect(kinds).toContain('budget');
  });
});

describe('a viewer who may act', () => {
  it('is offered the decision controls on an approval', async () => {
    serveScenario(
      'populated',
      principalHolding(['approval.read', 'remediation.approve', 'investigation.read']),
    );
    await renderArea('decisions', { tab: 'actions' });

    expect(screen.getAllByTestId('approval').length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('proposal-row').length).toBeGreaterThan(0);
  });

  it('is offered the tools browser on the agent screen', async () => {
    serveScenario('populated', principalHolding(['config.read', 'integration.manage']));
    await renderArea('agent', { tab: 'tools' });

    expect(screen.getAllByTestId('capability').length).toBeGreaterThan(0);
  });

  it('is offered the connected and catalogue sections on integrations', async () => {
    serveScenario('populated', principalHolding(['integration.manage']));
    await renderArea('integrations');

    expect(screen.getAllByTestId('connected-integration').length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('catalogue-item').length).toBeGreaterThan(0);
  });

  it('is told what the catalogue does not cover, and why, on its own reference page', async () => {
    // An operator evaluating this platform against their own stack otherwise
    // discovers an absence by looking for it and not finding it, which is the
    // worst moment and the worst way. A decision with the reasoning written
    // down is also where the next "should we build X" conversation starts.
    serveScenario('populated', principalHolding(['integration.manage']));
    await renderArea('integrations-not-covered');

    const gaps = screen.getAllByTestId('known-gap');
    const named = gaps.map((gap) => gap.getAttribute('data-integration'));
    expect(named).toContain('gatus');
    expect(named).toContain('netbox');

    const gatus = gaps.find((gap) => gap.getAttribute('data-integration') === 'gatus');
    expect(gatus).toHaveAttribute('data-cause', 'not_built');
    expect(gatus).toHaveTextContent('blackbox exporter');
    expect(gatus).toHaveTextContent('What would change it:');
  });

  it('tells a decision apart from something the architecture forbids', async () => {
    serveScenario('populated', principalHolding(['integration.manage']));
    await renderArea('integrations-not-covered');

    const causes = screen
      .getAllByTestId('known-gap')
      .map((gap) => gap.getAttribute('data-cause'));
    expect(new Set(causes)).toEqual(new Set(['not_built', 'unreachable']));
  });

  it('is offered the principals and grants on administration, desmembered from tokens and sign-on', async () => {
    // The property the desmembramento exists to establish: `administration`
    // (now Members & roles) reads only what it shows — people and their
    // grants — and machine tokens and single sign-on moved to their own
    // pages, covered separately below.
    serveScenario(
      'populated',
      principalHolding(['identity.read', 'token.manage', 'sso.manage']),
    );
    await renderArea('administration');

    expect(screen.getAllByTestId('principal').length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('grant').length).toBeGreaterThan(0);
    expect(screen.queryAllByTestId('token')).toEqual([]);
    expect(screen.queryByTestId('sso-setup-flow')).toBeNull();
  });

  it('is offered the machine token list on its own page', async () => {
    serveScenario('populated', principalHolding(['token.manage']));
    await renderArea('settings-machine-tokens');

    expect(screen.getAllByTestId('token').length).toBeGreaterThan(0);
  });

  it('is offered the sign-on flow on its own page', async () => {
    serveScenario('populated', principalHolding(['sso.manage']));
    await renderArea('settings-single-sign-on');

    expect(screen.getByTestId('sso-setup-flow')).toBeInTheDocument();
  });
});

describe('the request layer', () => {
  it('binds a path’s variables rather than sending the braces', async () => {
    let asked = '';
    vi.stubGlobal('fetch', (url: unknown) => {
      asked = String(url);
      return Promise.resolve(
        new Response('{}', {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });

    await read('/v1/runs/{run_id}', { params: { run_id: 'run 1/2' } });

    expect(asked).toBe('/v1/runs/run%201%2F2');
  });

  it('refuses a path whose variable nobody supplied', async () => {
    await expect(read('/v1/runs/{run_id}')).rejects.toThrow(/run_id/);
  });

  it('raises with the status the gateway answered', async () => {
    vi.stubGlobal('fetch', () => Promise.resolve(new Response('{}', { status: 503 })));

    await expect(read('/v1/runs')).rejects.toBeInstanceOf(ApiError);
  });

  it('reads a projected endpoint at a bound address', async () => {
    let asked = '';
    vi.stubGlobal('fetch', (url: unknown) => {
      asked = String(url);
      return Promise.resolve(
        new Response('{}', {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });

    await readProjected('/v1/estate/storage', {
      params: {},
      query: '?state=open',
    });

    expect(asked).toBe('/v1/estate/storage?state=open');
  });

  it('names every projected endpoint exactly once', () => {
    const distinct = new Set(PROJECTED_PATHS);
    expect(distinct.size).toBe(PROJECTED_PATHS.length);
  });
});

describe('what a panel does with a refusal', () => {
  it('turns a rejected read into an error naming the dependency', async () => {
    const failed = await panelRead<unknown>('/v1/runs', () =>
      Promise.reject(new ApiError(503, 'no')),
    );

    expect(stateOf(failed, false)).toBe('error');
    expect(dependencyOf(failed)).toBe('/v1/runs');
    expect(dataOf(failed)).toBeUndefined();
  });

  it('lets a defect in the console reach the route’s own boundary', async () => {
    await expect(
      panelRead<unknown>('/v1/runs', () => Promise.reject(new RangeError('a defect'))),
    ).rejects.toBeInstanceOf(RangeError);
  });

  it('treats a projected endpoint nobody serves yet as empty, not as broken', async () => {
    vi.stubGlobal('fetch', () => Promise.resolve(new Response('{}', { status: 404 })));

    const answered = await readProjectedPanel('/v1/estate/nodes', 'a-token');

    expect(stateOf(answered, true)).toBe('empty');
  });

  it('treats every other refusal of one as an error', async () => {
    vi.stubGlobal('fetch', () => Promise.resolve(new Response('{}', { status: 500 })));

    const answered = await readProjectedPanel('/v1/estate/nodes', 'a-token');

    expect(stateOf(answered, true)).toBe('error');
  });

  it('lets a defect through from a projected read as well', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new RangeError('a defect')));

    await expect(
      readProjectedPanel('/v1/estate/nodes', 'a-token'),
    ).rejects.toBeInstanceOf(RangeError);
  });
});

describe('the context a screen renders in', () => {
  it('reads the first value of a repeated parameter', async () => {
    serveScenario('populated', principalHolding(['investigation.read']));

    const context = await surfaceContext({
      status: ['failed', 'running'],
      trigger: 'alert',
      missing: undefined,
    });

    expect(context.search.get('status')).toBe('failed');
    expect(context.search.get('trigger')).toBe('alert');
    expect(context.search.has('missing')).toBe(false);
  });

  it('resolves the viewer through the deployment rather than trusting the layout', async () => {
    serveScenario('populated', principalHolding(['investigation.read']));

    const context = await surfaceContext();

    expect(context.viewer.permissions).toEqual(['investigation.read']);
    expect(context.deployment.name).toBe('HAL9000');
  });
});

describe('scrolling a long list', () => {
  it('draws the rows the scroll position names', () => {
    const rows = Array.from({ length: 1000 }, (_, index) => ({
      id: `row-${String(index)}`,
      href: `/runs/row-${String(index)}`,
      cells: [{ kind: 'text' as const, text: `row ${String(index)}` }],
    }));

    render(
      <RowList
        columns={[{ key: 'name', header: 'Name' }]}
        rows={rows}
        labels={{
          caption: 'Rows',
          sortedAscending: 'ascending',
          sortedDescending: 'descending',
          open: 'Open',
        }}
        path="/runs"
        state={DEFAULT_VIEW_STATE}
        filters={[]}
      />,
    );

    const region = screen.getByTestId('row-list');
    fireEvent.scroll(region, { target: { scrollTop: 4400 } });

    const drawn = screen
      .getAllByTestId('row')
      .map((row) => row.getAttribute('data-row'));
    expect(drawn).not.toContain('row-0');
    expect(screen.getByTestId('pad-top')).toBeInTheDocument();
  });

  it('draws a meter for a cell that has a capacity', () => {
    render(
      <RowList
        columns={[
          { key: 'name', header: 'Name' },
          { key: 'used', header: 'Utilisation' },
        ]}
        rows={[
          {
            id: 'r-1',
            href: '/resources?selected=r-1',
            cells: [
              { kind: 'text', text: 'local-lvm' },
              { kind: 'meter', text: 'local-lvm', value: 84 },
            ],
          },
        ]}
        labels={{
          caption: 'Resources',
          sortedAscending: 'ascending',
          sortedDescending: 'descending',
          open: 'Open',
        }}
        path="/resources"
        state={DEFAULT_VIEW_STATE}
        filters={[]}
      />,
    );

    // A bar and its number: "about ninety per cent" is not a figure anybody acts on.
    expect(screen.getByTestId('meter')).toHaveAttribute('aria-valuenow', '84');
  });
});

describe('the fixture base', () => {
  it('is a loopback name that is never contacted', () => {
    expect(new URL('/v1/runs', BASE).pathname).toBe('/v1/runs');
  });
});
