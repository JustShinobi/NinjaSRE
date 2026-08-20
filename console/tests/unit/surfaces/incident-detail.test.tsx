import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { IncidentDetailScreen } from '@/surfaces/screens/incident-detail';

/**
 * The M6 rewrite, exercised at both ends of what an incident can carry.
 *
 * One incident has never been investigated: no run attached, no subject, no
 * proposal — every card on the page has to say so by name rather than render
 * blank. The other has an investigation that is still running (no report
 * delivered yet) and a decision already made on its proposal, which is the
 * combination the happy-path fixture used by the cross-screen suite does not
 * reach — that one incident is always fully investigated and always awaiting
 * a decision, so the "still running" chip, a real duration and cost, a
 * singular step count, and a decided (not pending) proposal have nowhere else
 * to be proved.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

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

function serve(byPath: Readonly<Record<string, unknown>>): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const url = new URL(String(input), BASE);
    const body = byPath[url.pathname + url.search] ?? byPath[url.pathname];
    return Promise.resolve(
      new Response(JSON.stringify(body ?? {}), {
        status: body === undefined ? 404 : 200,
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

async function renderIncident(incidentId: string): Promise<void> {
  render(await IncidentDetailScreen(await surfaceContext({}), incidentId));
}

describe('an incident nothing has ever investigated', () => {
  beforeEach(() => {
    serve({
      '/auth/me': PRINCIPAL,
      '/v1/incidents/inc-bare-01': {
        incident: {
          incident_id: 'inc-bare-01',
          title: 'anchor is not responding',
          summary: 'an alert opened this incident about anchor',
          state: 'resolved',
          severity: 'high',
          origin: 'alert',
          detector: '',
          subjects: [],
          opened_at: '2026-08-07T12:00:00+00:00',
          closed_at: null,
          run_id: null,
        },
        subjects: [],
        observations: [],
        timeline: [
          {
            at: '2026-08-07T12:00:00+00:00',
            kind: 'opened',
            actor: 'user-lagoon',
            cause: 'an alert opened this incident about anchor',
            detail: 'alertmanager delivered an alert about 1 target(s)',
          },
        ],
        actions: [],
        investigation: null,
      },
    });
  });

  it('names the pendency in every card instead of rendering blank', async () => {
    await renderIncident('inc-bare-01');

    // Header: title over the raw id, the incident's own state, and "no
    // investigation" rather than a chip claiming one that never started.
    expect(screen.getByTestId('incident-title')).toHaveTextContent(
      'anchor is not responding',
    );
    const chips = screen.getAllByTestId('incident-chip');
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveTextContent('Resolved');
    expect(chips[1]).toHaveTextContent('No investigation');

    // The subtitle still says something for every fact, even the ones this
    // incident does not carry — "not recorded" rather than an empty span.
    expect(screen.getByTestId('subtitle-rule')).toHaveTextContent('Not recorded');
    expect(screen.getByTestId('subtitle-source')).toHaveTextContent('Alertmanager');
    expect(screen.getByTestId('subtitle-host')).toHaveTextContent('Not recorded');

    const panels = screen.getAllByTestId('panel');
    expect(panels).toHaveLength(3);
    for (const panel of panels) {
      expect(panel).toHaveAttribute('data-state', 'empty');
    }

    // Never a blank card: each one names what is missing.
    expect(screen.getByText('No investigation has run')).toBeInTheDocument();
    expect(screen.getByText('No run to trace yet')).toBeInTheDocument();
    expect(screen.getByText('Nothing proposed yet')).toBeInTheDocument();

    // Rendering the empty state must not itself invent numbers or a link.
    expect(screen.queryByTestId('investigation-summary')).not.toBeInTheDocument();
    expect(screen.queryByTestId('investigation-step')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Open the full run' }),
    ).not.toBeInTheDocument();
  });
});

describe('an incident whose investigation is still running', () => {
  beforeEach(() => {
    serve({
      '/auth/me': PRINCIPAL,
      '/v1/incidents/inc-running-01': {
        incident: {
          incident_id: 'inc-running-01',
          title: 'cedar is down',
          summary: 'the blackbox probe against cedar has failed',
          state: 'investigating',
          severity: 'critical',
          origin: 'human',
          detector: 'InstanceDown',
          subjects: ['cedar'],
          opened_at: '2026-08-07T06:00:00+00:00',
          closed_at: null,
          run_id: 'run-cedar-1',
        },
        subjects: [],
        observations: [],
        timeline: [
          {
            at: '2026-08-07T06:00:01+00:00',
            kind: 'alert_received',
            actor: 'system:observation',
            cause: 'InstanceDown fired for cedar',
            detail: '',
          },
          {
            at: '2026-08-07T06:00:02+00:00',
            kind: 'hypotheses_drawn',
            actor: 'system:observation',
            cause: 'considered before any integration was queried',
            detail: 'node reboot; network partition; probe agent crashed',
          },
          {
            at: '2026-08-07T06:00:03+00:00',
            kind: 'evidence',
            actor: 'system:observation',
            cause: 'cedar has not answered its own probe',
            detail: '',
            query: '',
            result: '',
          },
          {
            at: '2026-08-07T06:00:04+00:00',
            kind: 'diagnosis',
            actor: 'system:observation',
            cause: 'cedar is down: it stopped responding to its own probe',
            detail: '',
          },
        ],
        actions: [],
        investigation: { step_count: 1, duration_ms: 5000, cost: 0.5 },
      },
      '/v1/estate/resources/cedar': {
        resource: {
          resource_id: 'cedar',
          kind: 'container',
          display_name: 'cedar',
          health: 'unhealthy',
          stored_health: 'unhealthy',
          is_stale: false,
          source: 'demo',
          attributes: { zone: 'lab', criticality: 'high' },
        },
      },
      '/v1/approvals?run_id=run-cedar-1': {
        approvals: [
          {
            approval_id: 'apr-cedar-1',
            run_id: 'run-cedar-1',
            action: 'proxmox.start_guest',
            side_effect_level: 'write_reversible',
            summary: 'Start cedar again.',
            requested_at: '2026-08-07T06:01:00+00:00',
            expires_at: '2026-08-07T07:01:00+00:00',
            state: 'approved',
            arguments: {},
            decided_at: '2026-08-07T06:05:00+00:00',
            decided_by: 'user-operator',
            reason: null,
            rollback_plan: null,
          },
        ],
      },
    });
  });

  it('reports a real duration and cost, and has not delivered a report yet', async () => {
    await renderIncident('inc-running-01');

    const chips = screen.getAllByTestId('incident-chip');
    expect(chips[0]).toHaveTextContent('Investigating');
    expect(chips[1]).toHaveTextContent('Investigation running');

    expect(screen.getByTestId('subtitle-source')).toHaveTextContent('a person');

    const summary = screen.getByTestId('investigation-summary');
    expect(within(summary).getByTestId('summary-steps')).toHaveTextContent('1 step');
    expect(within(summary).getByTestId('summary-duration')).not.toHaveTextContent(
      'Not recorded',
    );
    expect(within(summary).getByTestId('summary-cost')).not.toHaveTextContent(
      'Not recorded',
    );

    // No delivery step landed yet: only four of the five kinds appear.
    const kinds = screen
      .getAllByTestId('investigation-step')
      .map((step) => step.getAttribute('data-kind'));
    expect(kinds).toEqual(['receipt', 'hypotheses', 'evidence', 'diagnosis']);

    // An evidence step with no query or result recorded still says so.
    expect(screen.getByTestId('evidence-query')).toHaveTextContent('Not recorded');
    expect(screen.getByTestId('evidence-result')).toHaveTextContent('Not recorded');

    // A decision already made shows as decided, not "awaiting".
    const card = screen.getByTestId('proposed-action');
    expect(within(card).getByTestId('decision-state')).toHaveTextContent('Approved');

    // This proposal carries no blast radius of its own, and the card says so
    // rather than counting the incident's subjects. The two are different
    // questions: how far the *action* reaches is not how many things the
    // incident is about, and answering the second while appearing to answer
    // the first is the failure this states plainly instead.
    expect(within(card).getByTestId('radius-resources')).toHaveTextContent(
      'Not recorded',
    );
    expect(within(card).getByTestId('radius-zone')).toHaveTextContent('lab');
    expect(within(card).getByTestId('radius-criticality')).toHaveTextContent('high');

    expect(screen.getByRole('link', { name: 'Open the full run' })).toHaveAttribute(
      'href',
      '/runs/run-cedar-1',
    );
  });
});

describe('what the proposed-action card is allowed to claim', () => {
  const incident = () => ({
    incident_id: 'inc-claim-01',
    title: 'birch is unreachable',
    summary: 'the probe against birch has failed',
    state: 'investigating',
    severity: 'critical',
    origin: 'alert',
    detector: 'InstanceDown',
    subjects: ['birch', 'cedar', 'anchor'],
    opened_at: '2026-08-07T06:00:00+00:00',
    closed_at: null,
    run_id: 'run-birch-1',
  });

  const timelineOf = (kinds: readonly string[]) =>
    kinds.map((kind, index) => ({
      at: `2026-08-07T06:00:0${String(index + 1)}+00:00`,
      kind,
      actor: 'system:observation',
      cause: `a ${kind} step`,
      detail: '',
      query: '',
      result: '',
    }));

  function seed(kinds: readonly string[], blastRadiusCount: number | null): void {
    const body = incident();
    serve({
      '/auth/me': PRINCIPAL,
      '/v1/incidents/inc-claim-01': {
        incident: body,
        subjects: [],
        observations: [],
        timeline: timelineOf(kinds),
        actions: [],
        investigation: { step_count: kinds.length, duration_ms: 5000, cost: 0.5 },
      },
      '/v1/estate/resources/birch': {
        resource: {
          resource_id: 'birch',
          kind: 'container',
          display_name: 'birch',
          health: 'unhealthy',
          stored_health: 'unhealthy',
          is_stale: false,
          source: 'demo',
          attributes: { zone: 'apps', criticality: 'medium' },
        },
      },
      '/v1/approvals?run_id=run-birch-1': {
        approvals: [
          {
            approval_id: 'apr-birch-1',
            run_id: 'run-birch-1',
            action: 'proxmox.start_guest',
            side_effect_level: 'write_reversible',
            summary: 'Start birch again.',
            requested_at: '2026-08-07T06:01:00+00:00',
            expires_at: '2026-08-07T07:01:00+00:00',
            state: 'pending',
            arguments: {},
            decided_at: null,
            decided_by: null,
            reason: null,
            rollback_plan: null,
            blast_radius_count: blastRadiusCount,
          },
        ],
      },
    });
  }

  it('shows the action own reach when the proposal carries one', async () => {
    // Three subjects on the incident, two resources in the action's reach.
    // The card must report the second, so a screen that quietly counted
    // subjects would read "3 resources" here and fail.
    seed(['alert_received', 'hypotheses_drawn', 'evidence', 'diagnosis'], 2);
    await renderIncident('inc-claim-01');

    const card = screen.getByTestId('proposed-action');
    expect(within(card).getByTestId('radius-resources')).toHaveTextContent(
      '2 resources',
    );
  });

  it('does not offer a proposal when no conclusion was ever supported', async () => {
    // The same pending approval is served, and the timeline stops at the
    // hypotheses. A conclusion with nothing under it is recorded as a
    // hypothesis rather than a diagnosis, so the absence of a diagnosis step
    // is what "nothing was ever supported" looks like from here — and a
    // proposal raised over that must not be offered for decision.
    seed(['alert_received', 'hypotheses_drawn', 'evidence'], 2);
    await renderIncident('inc-claim-01');

    expect(screen.queryByTestId('proposed-action')).not.toBeInTheDocument();
    expect(screen.queryByTestId('decision-control')).not.toBeInTheDocument();
    expect(screen.getByText('Nothing proposed yet')).toBeInTheDocument();
  });
});
