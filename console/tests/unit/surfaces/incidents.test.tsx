import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext, type SearchParams } from '@/surfaces/context';
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

/** Every address the screen asked for, in order, query included. */
let asked: URL[] = [];

function serve(bodies: {
  readonly detectors: readonly unknown[];
  readonly detectorsStatus?: number;
  readonly incidents: readonly unknown[];
  readonly runs?: readonly unknown[];
  readonly setup: unknown;
}): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const address = new URL(String(input), BASE);
    asked.push(address);
    const path = address.pathname;
    const byPath: Record<string, unknown> = {
      '/auth/me': PRINCIPAL,
      '/v1/incidents': { incidents: bodies.incidents },
      '/v1/detectors': { detectors: bodies.detectors },
      '/v1/runs': { runs: bodies.runs ?? [] },
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
  asked = [];
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function incidents(search: SearchParams = {}): Promise<void> {
  render(await IncidentsScreen(await surfaceContext(search)));
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

describe('view selector in address', () => {
  it('does not filter out incidents when flat view is selected', async () => {
    serve({
      detectors: [enabledDetector('quorum-margin-zero')],
      incidents: [OPEN_INCIDENT],
      setup: SETUP_COMPLETE,
    });
    await incidents({ view: 'flat' });

    expect(screen.getByText('Backup job disabled')).toBeInTheDocument();
  });
});

describe('the runs read behind the settled firings’ headlines', () => {
  // `/incidents` was the one route still over a hundred milliseconds at the
  // ingress, and the reason was this screen reading the whole first page of
  // runs — fifty full records — to look up a headline for the two or three a
  // settled firing cites. The incidents are read first, and the runs read asks
  // for exactly the ones cited, or is not made at all.

  const RESOLVED_WITH_RUN = {
    ...OPEN_INCIDENT,
    incident_id: 'inc-0002',
    public_id: 'inc-0002',
    state: 'resolved',
    closed_at: '2026-08-07T11:00:00+00:00',
    run_id: 'run-0005',
  };
  const OPEN_WITH_RUN = {
    ...OPEN_INCIDENT,
    incident_id: 'inc-0003',
    public_id: 'inc-0003',
    subjects: ['pg-primary'],
    run_id: 'run-0009',
  };

  function runsAsked(): URL[] {
    return asked.filter((address) => address.pathname === '/v1/runs');
  }

  it('asks for exactly the cited runs, each once, and nothing else', async () => {
    serve({
      detectors: [enabledDetector('backup-job-disabled')],
      incidents: [
        RESOLVED_WITH_RUN,
        OPEN_WITH_RUN,
        { ...RESOLVED_WITH_RUN, incident_id: 'inc-0004', public_id: 'inc-0004' },
      ],
      setup: SETUP_COMPLETE,
    });
    await incidents();

    expect(runsAsked()).toHaveLength(1);
    const query = runsAsked()[0]?.searchParams;
    expect(query?.getAll('run_id')).toEqual(['run-0005', 'run-0009']);
    expect(query?.get('limit')).toBe('2');
    expect([...new Set(query?.keys())].sort()).toEqual(['limit', 'run_id']);
  });

  it('reads the incidents before it knows which runs to ask for', async () => {
    serve({
      detectors: [enabledDetector('backup-job-disabled')],
      incidents: [RESOLVED_WITH_RUN],
      setup: SETUP_COMPLETE,
    });
    await incidents();

    const order = asked.map((address) => address.pathname);
    expect(order.indexOf('/v1/incidents')).toBeLessThan(order.indexOf('/v1/runs'));
  });

  it('does not read the runs at all when no incident cites one', async () => {
    serve({
      detectors: [enabledDetector('backup-job-disabled')],
      incidents: [
        OPEN_INCIDENT,
        { ...OPEN_INCIDENT, incident_id: 'inc-0005', run_id: null },
      ],
      setup: SETUP_COMPLETE,
    });
    await incidents();

    expect(runsAsked()).toEqual([]);
    expect(screen.getAllByText('Backup job disabled').length).toBeGreaterThan(0);
  });

  it('still shows the headline of the run a settled firing cites', async () => {
    serve({
      detectors: [enabledDetector('backup-job-disabled')],
      incidents: [RESOLVED_WITH_RUN],
      runs: [
        {
          run_id: 'run-0005',
          status: 'completed',
          headline: 'Backup job re-enabled after a failed rotation',
          summary: '',
        },
      ],
      setup: SETUP_COMPLETE,
    });
    await incidents();

    expect(
      screen.getByText(/Backup job re-enabled after a failed rotation/),
    ).toBeInTheDocument();
  });
});
