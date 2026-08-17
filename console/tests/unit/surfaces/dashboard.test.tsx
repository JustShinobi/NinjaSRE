import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EN } from '@/i18n/en';
import { areaByPath } from '@/shell/routes';
import { AttentionBlock } from '@/surfaces/attention';
import { Figure } from '@/surfaces/figure';
import { DashboardScreen, oldestAttention } from '@/surfaces/screens/dashboard';
import { surfaceContext } from '@/surfaces/context';
import { serveScenario, type Scenario } from '../support/dataset';

/**
 * The overview screen, against the seven numbered problems the design review
 * raised: a raw exception as the first thing read, an empty centre while setup
 * is incomplete, figures with no visible way out and no story connecting them,
 * nothing about the agent itself, vague quick actions, an inventory dressed up
 * as health, and a badge that shouts instead of explaining itself.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === 'ninjasre_session' ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

const FIXTURES_BASE = ['http:', '//fixtures.invalid'].join('');

afterEach(() => {
  vi.unstubAllGlobals();
});

async function dashboard(scenario: Scenario): Promise<void> {
  serveScenario(scenario);
  render(await DashboardScreen(await surfaceContext({})));
}

/**
 * `scenario`, with one run replaced by a raised exception naming an
 * environment variable — the sentence that used to be this page's headline.
 */
async function dashboardWithRaisedFailure(): Promise<void> {
  serveScenario('populated');
  const scenario = globalThis.fetch;
  vi.stubGlobal('fetch', (input: unknown, init?: RequestInit) => {
    const path = new URL(String(input), FIXTURES_BASE).pathname;
    if (path === '/v1/runs') {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            runs: [
              {
                run_id: 'run-uninvestigated',
                status: 'failed',
                trigger: 'alert',
                started_at: '2026-08-07T10:00:00.000Z',
                finished_at: '2026-08-07T10:01:00.000Z',
                summary:
                  "InvestigatorNotConfigured: Set NINJASRE_INVESTIGATOR to 'module:factory' — a callable returning the runner.",
              },
            ],
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      );
    }
    return scenario(input as Parameters<typeof fetch>[0], init);
  });
  render(await DashboardScreen(await surfaceContext({})));
}

/** Render the populated dashboard with a deliberately mixed health summary. */
async function dashboardWithHealthSummary(summary: unknown): Promise<void> {
  serveScenario('populated');
  const scenario = globalThis.fetch;
  vi.stubGlobal('fetch', (input: unknown, init?: RequestInit) => {
    const path = new URL(String(input), FIXTURES_BASE).pathname;
    if (path === '/v1/estate/summary') {
      return Promise.resolve(
        new Response(JSON.stringify(summary), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    }
    return scenario(input as Parameters<typeof fetch>[0], init);
  });
  render(await DashboardScreen(await surfaceContext({})));
}

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

// --- 1. A raw exception is never this page's first reading ------------------------------

describe('what a failed run reads as', () => {
  it('never shows the deployment’s raised exception, in the band or in the feed', async () => {
    await dashboardWithRaisedFailure();

    expect(document.body.innerHTML).not.toContain('InvestigatorNotConfigured');
    expect(document.body.innerHTML).not.toContain('NINJASRE_INVESTIGATOR');
  });

  it('says what an operator can do about it, in words meant for them', async () => {
    await dashboardWithRaisedFailure();

    expect(screen.getByText(EN['failure.investigator.title'])).toBeInTheDocument();
  });

  it('sends the band to the pending setup step, not to the run', async () => {
    await dashboardWithRaisedFailure();

    const row = screen
      .getAllByTestId('attention-row')
      .find((candidate) => candidate.getAttribute('data-kind') === 'failure');
    if (row === undefined) {
      throw new Error('no attention row was drawn for the failed run');
    }
    // Not the model step by name: this failure is the deployment's own runtime,
    // never a configuration field, so the band sends somebody to the guided
    // setup itself rather than to a step that may already be finished.
    expect(within(row).getByRole('link')).toHaveAttribute('href', '/first-run');
  });
});

// --- 2. Setup incomplete dominates the page ----------------------------------------------

describe('the setup hero', () => {
  it('is the dominant thing on the page while steps remain', async () => {
    await dashboard('first-run');

    const hero = screen.getByTestId('setup-hero');
    expect(hero).toBeInTheDocument();
    expect(within(hero).getAllByTestId('setup-hero-step')).toHaveLength(7);
    // Exactly one step is where the deployment actually is.
    const current = within(hero)
      .getAllByTestId('setup-hero-step')
      .filter((step) => step.getAttribute('data-current') === 'true');
    expect(current).toHaveLength(1);
  });

  it('offers exactly one action: the next step', async () => {
    await dashboard('first-run');

    // 'first-run' holds a provider already configured (not yet verified), so
    // the next open step is choosing a model, not choosing a provider.
    const cta = screen.getByTestId('setup-hero-cta');
    expect(cta.getAttribute('href')).toBe('/first-run?step=model');
  });

  it('gives way once nothing is left to set up', async () => {
    await dashboard('populated');

    expect(screen.queryByTestId('setup-hero')).toBeNull();
  });
});

// --- 3. Every figure is clickable, visibly, and an alarming one explains itself -----------

describe('a summary figure’s visible drill-down', () => {
  it('carries a visible affordance, not only one a screen reader hears', () => {
    render(
      <Figure
        label="Resources watched"
        value="86"
        context="86 resources"
        href="/resources"
        drillLabel="See the list behind this figure"
      />,
    );

    const visible = screen.getByTestId('figure-drill');
    expect(visible.className).not.toMatch(/\bsr-only\b/);
  });
});

describe('the figures on a populated deployment', () => {
  it('explains the degraded count rather than leaving it to guess', async () => {
    await dashboard('populated');

    const degraded = screen
      .getAllByTestId('figure')
      .find(
        (figure) =>
          figure.getAttribute('data-figure') === EN['dashboard.stat.degraded'],
      );
    expect(degraded).toBeDefined();
    // 14 detectors watching, all live in the populated dataset — the fact
    // that bridges "14 unhealthy" and "Incidents: none".
    expect(degraded?.textContent).toMatch(/14 of 14/);
  });

  it('counts only degraded and unhealthy states, not unknown or stale observations', async () => {
    await dashboardWithHealthSummary({
      total: 10,
      problems: 4,
      by_health: { healthy: 4, degraded: 2, unhealthy: 2, unknown: 3, stale: 3 },
      by_kind: {},
    });

    const degraded = screen
      .getAllByTestId('figure')
      .find(
        (figure) =>
          figure.getAttribute('data-figure') === EN['dashboard.stat.degraded'],
      );
    expect(degraded).toBeDefined();
    if (degraded === undefined) throw new Error('the degraded figure was not rendered');
    expect(within(degraded).getByTestId('stat-value')).toHaveTextContent('4');
    expect(degraded).toHaveTextContent('4 open findings');
  });

  it('sends the problem figure to the resource list that contains both problem states', async () => {
    await dashboard('populated');

    const degraded = screen
      .getAllByTestId('figure')
      .find(
        (figure) =>
          figure.getAttribute('data-figure') === EN['dashboard.stat.degraded'],
      );
    expect(degraded).toHaveAttribute('href', '/resources?health=problem');
  });
});

// --- 4. At least one number is about the agent, not the estate ----------------------------

describe('an indicator of whether the agent itself is working', () => {
  it('shows a success rate figure, drawn from the runs the deployment recorded', async () => {
    await dashboard('populated');

    const figures = screen.getAllByTestId('figure');
    const successRate = figures.find(
      (figure) =>
        figure.getAttribute('data-figure') === EN['dashboard.stat.successRate'],
    );
    expect(successRate).toBeDefined();
    // 2 succeeded of 4 settled runs in the populated dataset.
    expect(successRate?.textContent).toContain('50');
  });
});

// --- 5. Quick actions name their destination and say what it does -------------------------

describe('quick actions', () => {
  it('names the destination screen and describes it, rather than a poetic aside', async () => {
    await dashboard('populated');

    const actions = screen.getAllByTestId('quick-action');
    // Two rather than three: Memory is Knowledge's own "Learned" tab now, so
    // pointing a second action at the same screen under a second name would
    // be the same destination offered twice.
    expect(actions).toHaveLength(2);
    for (const action of actions) {
      const href = action.getAttribute('href') ?? '';
      expect(areaByPath(href), `${href} is not an area`).toBeDefined();
    }
    expect(screen.getByText(EN['page.knowledge.title'])).toBeInTheDocument();
    expect(screen.getByText(EN['page.knowledge.context'])).toBeInTheDocument();
  });
});

// --- 6. "Estate health" is not an inventory with no state ----------------------------------

describe('the estate panel that used to be a plain inventory', () => {
  it('no longer has a catalogue entry, or a panel, of its own', async () => {
    expect('dashboard.estate.title' in EN).toBe(false);

    await dashboard('populated');

    // The by-kind inventory this card used to draw the counts from — an
    // English word every locale's fixture repeats, so this is a stand-in for
    // "no panel that used to be titled 'Estate health' is on the page".
    expect(screen.queryByText('Estate health')).toBeNull();
  });
});

// --- 7. The oldest badge explains itself instead of shouting ------------------------------

describe('the "needs you" band’s oldest badge', () => {
  it('is not drawn in shouting capitals', () => {
    render(
      <AttentionBlock
        heading="1 item needs you"
        oldest="Waiting longest: 2h 14m"
        rows={[
          {
            id: 'a-1',
            kind: 'approval',
            title: 'Reclaim 41 GiB on local-lvm',
            detail: 'awaiting decision',
            href: '/approvals?selected=a-1',
            since: '2h ago',
          },
        ]}
        openLabel="Open"
      />,
    );

    const badge = screen.getByText('Waiting longest: 2h 14m');
    expect(badge.className).not.toMatch(/\buppercase\b/);
  });

  it('chooses the oldest timestamp rather than the last source group', () => {
    const oldest = oldestAttention([
      {
        id: 'newer',
        kind: 'incident',
        title: 'Newer',
        detail: 'open',
        href: '/incidents/newer',
        since: '1h ago',
        at: '2026-08-07T11:00:00Z',
      },
      {
        id: 'older',
        kind: 'failure',
        title: 'Older',
        detail: 'failed',
        href: '/runs/older',
        since: '2d ago',
        at: '2026-08-05T11:00:00Z',
      },
    ]);

    expect(oldest?.id).toBe('older');
  });
});
