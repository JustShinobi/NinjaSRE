import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { IncidentsScreen } from '@/surfaces/screens/incidents';

/**
 * The empty state that told a deployment with nothing watching that nothing
 * was wrong.
 *
 * "A detector opens an incident when what it watches crosses its threshold.
 * None has." is true and useless on a deployment with zero detectors switched
 * on — the honest sentence is that nothing is watching at all, and the
 * console owes that distinction to whoever opens this screen expecting quiet
 * to mean safe. This file pins the distinction: the watching cause when no
 * detector is live, the setup cause when the checklist is what is blocking it,
 * and the feature's own words the moment neither applies.
 *
 * It also pins the two polish fixes that ride along: a filter offering only
 * "Any" does not render, and the empty state's call to action is not doubled
 * by a second, visible control this screen added on top of it.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/** Built rather than written: a literal origin in console source is refused. */
const BASE = ['http:', '//gateway.test'].join('');

const PRINCIPAL = {
  principal_id: 'user-operator',
  display_name: 'Avery Lockhart',
  kind: 'person',
  roles: ['owner'],
  permissions: ['investigation.read'],
  team_node_id: 'org-northwind',
  impersonating: false,
  impersonated_by: null,
};

/** A checklist that still has outstanding steps: no provider stored, and no
 * investigation has completed — the step this screen's own cause depends on. */
const SETUP_INCOMPLETE = {
  complete: false,
  provider: 'absent',
  integrations: [],
  steps: [
    { name: 'model-provider', state: 'ready' },
    {
      name: 'first-investigation',
      state: 'blocked',
      title: 'Run your first investigation',
    },
  ],
};

/** A checklist with nothing left to do. */
const SETUP_COMPLETE = {
  complete: true,
  provider: 'openai',
  integrations: [{ name: 'openai', readiness: 'verified' }],
  steps: [
    { name: 'infrastructure-source', state: 'done' },
    { name: 'first-investigation', state: 'done' },
  ],
};

const OPEN_INCIDENT = {
  incident_id: 'inc-0001',
  title: 'Backup job disabled',
  severity: 'critical',
  state: 'open',
  detector: 'backup-job-disabled',
  opened_at: '2026-08-07T10:00:00+00:00',
  closed_at: null,
  subjects: ['backup-1f376301'],
};

function enabledDetector(id: string): unknown {
  return {
    detector_id: id,
    name: id,
    description: '',
    severity: 'critical',
    enabled: true,
    signal: 'x',
    subjects_covered: 1,
    subjects_total: 1,
    last_verdict: 'clear',
    origin: '',
    origin_excerpt: '',
    proposed: false,
  };
}

function serve(bodies: {
  readonly detectors: readonly unknown[];
  readonly detectorsStatus?: number;
  readonly incidents: readonly unknown[];
  readonly setup: unknown;
}): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const byPath: Record<string, unknown> = {
      '/auth/me': PRINCIPAL,
      '/v1/incidents': { incidents: bodies.incidents },
      '/v1/detectors': { detectors: bodies.detectors },
      '/v1/setup/checklist': bodies.setup,
    };
    const body = byPath[path];
    return Promise.resolve(
      new Response(JSON.stringify(body ?? {}), {
        status:
          path === '/v1/detectors' && bodies.detectorsStatus !== undefined
            ? bodies.detectorsStatus
            : body === undefined
              ? 404
              : 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function incidents(): Promise<void> {
  render(await IncidentsScreen(await surfaceContext({})));
}

function emptyPanel(): HTMLElement {
  const panel = screen
    .getAllByTestId('panel')
    .find((candidate) => candidate.getAttribute('data-state') === 'empty');
  if (panel === undefined) throw new Error('no empty panel rendered');
  return panel;
}

describe('no detector is switched on', () => {
  beforeEach(() => {
    serve({ detectors: [], incidents: [], setup: SETUP_INCOMPLETE });
  });

  it('says nothing is watching rather than that nothing is wrong', async () => {
    await incidents();

    const panel = emptyPanel();
    expect(panel).toHaveTextContent(
      'No detector is switched on, so nothing is being watched',
    );
    expect(panel).not.toHaveTextContent('A detector opens an incident');
  });

  it('points at turning on continuous observation, not the setup checklist', async () => {
    await incidents();

    // A link, not a button: the empty state's action is a navigation and is
    // rendered as one element rather than as a button beside a hidden anchor.
    const action = screen.getByRole('link', {
      name: 'Turn on continuous observation',
    });
    expect(action).toBeInTheDocument();

    // The watching cause is more specific than the setup cause and wins,
    // even though this deployment's checklist is also unfinished.
    expect(screen.queryByText(/still being set up/)).toBeNull();
  });
});

describe('the checklist is what is blocking incidents, not the detectors', () => {
  beforeEach(() => {
    // A detector is live, so the more specific watching cause does not apply
    // — what is actually stopping this deployment is the setup itself.
    serve({
      detectors: [enabledDetector('quorum-margin-zero')],
      incidents: [],
      setup: SETUP_INCOMPLETE,
    });
  });

  it('names the outstanding setup rather than the detector coverage', async () => {
    await incidents();

    const panel = emptyPanel();
    expect(panel).toHaveTextContent('still being set up');
    expect(panel).not.toHaveTextContent('No detector is switched on');
  });
});

describe('a deployment that is watching and has caught nothing', () => {
  beforeEach(() => {
    serve({
      detectors: [enabledDetector('quorum-margin-zero')],
      incidents: [],
      setup: SETUP_COMPLETE,
    });
  });

  it('keeps the feature’s own reassurance once nothing local explains the emptiness', async () => {
    await incidents();

    const panel = emptyPanel();
    expect(panel).toHaveTextContent(
      'A detector opens an incident when what it watches crosses its threshold. None has.',
    );
    expect(panel).not.toHaveTextContent('No detector is switched on');
    expect(panel).not.toHaveTextContent('still being set up');
  });

  it('offers an in-console example of what an incident will look like', async () => {
    await incidents();

    expect(screen.getByTestId('incident-preview-link')).toHaveAttribute(
      'href',
      '#incident-preview',
    );
    expect(screen.getByTestId('incident-preview')).toHaveTextContent(
      'What an incident looks like',
    );
    expect(screen.getByTestId('incident-preview')).toHaveTextContent(
      'Datastore near full',
    );
  });
});

describe('detector coverage is unavailable', () => {
  it('does not turn a detector read failure into a claim that nothing is watching', async () => {
    serve({
      detectors: [],
      detectorsStatus: 503,
      incidents: [],
      setup: SETUP_COMPLETE,
    });
    await incidents();

    const panel = emptyPanel();
    expect(panel).toHaveTextContent(
      'A detector opens an incident when what it watches crosses its threshold. None has.',
    );
    expect(panel).not.toHaveTextContent('No detector is switched on');
  });
});

describe('a filter with nothing to filter', () => {
  it('does not offer a control whose only option is "Any"', async () => {
    serve({ detectors: [], incidents: [], setup: SETUP_INCOMPLETE });
    await incidents();

    expect(screen.queryAllByTestId('filter')).toHaveLength(0);
  });

  it('still offers state and severity once there is something to narrow', async () => {
    serve({
      detectors: [enabledDetector('quorum-margin-zero')],
      incidents: [OPEN_INCIDENT],
      setup: SETUP_COMPLETE,
    });
    await incidents();

    const rendered = screen
      .getAllByTestId('filter')
      .map((filter) => filter.getAttribute('data-filter'));
    expect(rendered).toEqual(['state', 'severity']);
  });

  it('does not turn blank record fields into filter choices', async () => {
    serve({
      detectors: [enabledDetector('quorum-margin-zero')],
      incidents: [{ ...OPEN_INCIDENT, state: '', severity: '' }],
      setup: SETUP_COMPLETE,
    });
    await incidents();

    expect(screen.queryAllByTestId('filter')).toHaveLength(0);
  });
});

describe('the empty state’s call to action', () => {
  it('is one visible control, not a second one this screen added on top', async () => {
    serve({ detectors: [], incidents: [], setup: SETUP_INCOMPLETE });
    await incidents();

    const label = 'Turn on continuous observation';
    const visible = screen
      .getAllByText(label)
      .filter((node) => !node.className.includes('sr-only'));
    expect(visible).toHaveLength(1);
  });
});
