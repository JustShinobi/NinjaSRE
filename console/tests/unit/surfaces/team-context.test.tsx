import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { surfaceContext } from '@/surfaces/context';
import { TeamTab } from '@/surfaces/screens/team-context';

import { serveScenario } from '../support/dataset';

/**
 * The "Team" tab of The agent: what it says about the organisation it is
 * scoped to, and about a section nobody has written yet.
 *
 * Two defects this file exists to catch. First: a deployment with one node —
 * the ordinary shape of a fresh or small deployment — got a whole column
 * spent on a `<nav>` and a one-item `<ul>` to say a name the panel's own
 * title already implied; the tree is now drawn only where there is one to
 * navigate; one node collapses to a breadcrumb. Second: an operator opening
 * a truly empty operating-context editor for the first time read "Nothing
 * written here yet" and nothing else — no sense of what a section actually
 * is, on a screen whose own doctrine ("facts, not instructions") is
 * illustrated one panel down by an example nobody sees until they have
 * already written something. The empty state now carries that example.
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

async function renderTeamContext(): Promise<void> {
  render(await TeamTab(await surfaceContext({})));
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

/**
 * `populated`, except the tree carries one node and that node's operating
 * context is either what `context` supplies or entirely unwritten.
 */
function serveSingleNodeOrganisation(context?: {
  readonly sections: readonly unknown[];
  readonly template: readonly unknown[];
}): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    if (path === '/v1/config') {
      return Promise.resolve(respond({ nodes: [SINGLE_NODE] }));
    }
    if (path === '/v1/config/org-northwind/operating-context') {
      return Promise.resolve(
        respond({
          node_id: 'org-northwind',
          enabled: true,
          sections: context?.sections ?? [],
          template: context?.template ?? [],
          context: '',
          prompt: '',
          tokens_used: 0,
          token_budget: 1200,
          roles: ['investigator'],
        }),
      );
    }
    if (path === '/auth/me') {
      return Promise.resolve(
        respond({
          principal_id: 'user-operator',
          display_name: 'Avery Lockhart',
          email: 'avery.lockhart@example.invalid',
          kind: 'person',
          roles: ['owner'],
          permissions: ['config.read', 'config.write'],
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
    serveSingleNodeOrganisation({
      sections: [{ name: 'x', body: 'y', provenance: 'org-northwind' }],
      template: [],
    });

    await renderTeamContext();

    expect(screen.getByTestId('org-breadcrumb')).toHaveTextContent('Northwind');
    expect(screen.queryByTestId('org-tree')).not.toBeInTheDocument();
  });
});

describe('an organisation with more than one node', () => {
  it('keeps drawing the tree rather than collapsing it', async () => {
    serveScenario('populated');

    await renderTeamContext();

    expect(screen.getByTestId('org-tree')).toBeInTheDocument();
    expect(screen.queryByTestId('org-breadcrumb')).not.toBeInTheDocument();
  });
});

describe('an operating context nothing has written yet', () => {
  it('shows the concrete example of a section, not just "nothing here"', async () => {
    serveSingleNodeOrganisation();

    await renderTeamContext();

    const empty = screen
      .getAllByTestId('panel')
      .find((panel) => panel.getAttribute('data-state') === 'empty');
    expect(empty).toBeDefined();
    expect(empty).toHaveTextContent('Container metrics come from the host, by vmid');
  });

  it('keeps the same example visible once a starting document exists, before anything is written', async () => {
    serveSingleNodeOrganisation({
      sections: [],
      template: [
        {
          name: 'signals',
          body: 'Container metrics come from the host.',
          provenance: '',
        },
      ],
    });

    await renderTeamContext();

    // A node whose estate already produced a starting document is not "empty"
    // in the panel's own sense — the editor renders directly, with zero rows —
    // so the example has to come from the editor's own always-visible lead
    // sentence rather than from the panel-level empty state above.
    expect(screen.getByTestId('operating-context-editor')).toHaveTextContent(
      'Container metrics come from the host, by vmid',
    );
  });
});

describe('the starting-document button', () => {
  it('says what it does instead of the unexplained "Start from this"', async () => {
    serveSingleNodeOrganisation({
      sections: [],
      template: [
        {
          name: 'signals',
          body: 'Container metrics come from the host.',
          provenance: '',
        },
      ],
    });

    await renderTeamContext();

    expect(screen.queryByText('Start from this')).not.toBeInTheDocument();
    expect(screen.getByTestId('use-template')).toHaveTextContent(/starting document/i);
  });
});
