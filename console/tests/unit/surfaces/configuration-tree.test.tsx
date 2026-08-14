import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { serveScenario } from '../support/dataset';

/**
 * The Organisation panel on the Configuration screen, at a single-node
 * deployment.
 *
 * Team Context's own confrontation already collapsed this panel to a
 * breadcrumb when there is nothing to navigate
 * (`tests/unit/surfaces/team-context.test.tsx`). Spec 033's own problem
 * statement, for the same numbered item, names Configuration as sharing the
 * identical defect verbatim ("Vale igual para Configuration e Autonomy, que
 * têm o mesmo painel") — so this file exists to prove the fix on this
 * screen specifically, not to assume the shared helper (`OrgNav`,
 * `tree.tsx`) is wired in just because it exists.
 */

const BASE = ['http:', '//fixtures.invalid'].join('');

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: () => ({ value: 'session-under-test' }),
    }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderConfiguration(): Promise<void> {
  const { default: Page } = await import('@/app/(shell)/configuration/page');
  render(await Page({ searchParams: Promise.resolve({}) }));
}

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

const SINGLE_NODE = {
  kind: 'organisation',
  name: 'Northwind',
  node_id: 'org-northwind',
  parent_id: null,
};

/** A deployment whose tree carries exactly one node, reading only. */
function serveSingleNodeOrganisation(): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    if (path === '/v1/config') {
      return Promise.resolve(respond({ nodes: [SINGLE_NODE] }));
    }
    if (path === '/v1/config/org-northwind') {
      return Promise.resolve(
        respond({ node_id: 'org-northwind', values: {}, provenance: {} }),
      );
    }
    if (path === '/auth/me') {
      return Promise.resolve(
        respond({
          principal_id: 'user-operator',
          display_name: 'Avery Lockhart',
          email: 'avery.lockhart@example.invalid',
          kind: 'person',
          roles: ['reader'],
          permissions: ['config.read'],
          team_node_id: 'org-northwind',
          impersonated_by: null,
          impersonating: false,
        }),
      );
    }
    return Promise.resolve(respond({}, 404));
  });
}

describe('an organisation with exactly one node', () => {
  it('collapses the tree panel to a breadcrumb rather than a one-row nav', async () => {
    serveSingleNodeOrganisation();

    await renderConfiguration();

    expect(screen.getByTestId('org-breadcrumb')).toHaveTextContent('Northwind');
    expect(screen.queryByTestId('org-tree')).not.toBeInTheDocument();
  });
});

describe('an organisation with more than one node', () => {
  it('keeps drawing the tree rather than collapsing it', async () => {
    serveScenario('populated');

    await renderConfiguration();

    expect(screen.getByTestId('org-tree')).toBeInTheDocument();
    expect(screen.queryByTestId('org-breadcrumb')).not.toBeInTheDocument();
  });
});
