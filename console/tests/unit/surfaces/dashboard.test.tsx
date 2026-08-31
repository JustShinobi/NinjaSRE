import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AGENT_INCIDENT_STATES, HUMAN_INCIDENT_STATES } from '@/design/status';
import { EN } from '@/i18n/en';
import { areaByPath } from '@/shell/routes';
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

/**
 * Render the dashboard over incidents the deployment has already finished
 * with, spelled the way the store actually spells them.
 *
 * Every state below is a member of the store's enumeration. `closed` is not,
 * which is the whole point: the screen used to drop an incident only when its
 * state equalled that word, so the drop never happened.
 */
async function dashboardWithFinishedIncidents(): Promise<void> {
  serveScenario('populated');
  const scenario = globalThis.fetch;
  vi.stubGlobal('fetch', (input: unknown, init?: RequestInit) => {
    const path = new URL(String(input), FIXTURES_BASE).pathname;
    if (path === '/v1/incidents') {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            incidents: [
              {
                incident_id: 'inc-resolved',
                public_id: 'resolved',
                title: 'ProxmoxGuestStopped cleared upstream',
                summary: 'The guest came back and the condition cleared.',
                state: 'resolved',
                severity: 'critical',
                origin: 'detector',
                detector: 'alertmanager',
                opened_at: '2026-08-07T09:00:00.000Z',
                closed_at: '2026-08-07T09:04:00.000Z',
                self_resolved: true,
              },
              {
                incident_id: 'inc-suppressed',
                public_id: 'suppressed',
                title: 'CronJobStale during the maintenance window',
                summary: 'A suppression rule covered it.',
                state: 'suppressed',
                severity: 'critical',
                origin: 'detector',
                detector: 'alertmanager',
                opened_at: '2026-08-07T08:00:00.000Z',
                closed_at: '2026-08-07T08:01:00.000Z',
              },
              {
                incident_id: 'inc-shut',
                public_id: 'shut',
                title: 'RestoreDrillStale shut by an operator',
                summary: 'Closed with nothing done.',
                state: 'closed_without_action',
                severity: 'critical',
                origin: 'detector',
                detector: 'alertmanager',
                opened_at: '2026-08-07T07:00:00.000Z',
                closed_at: '2026-08-07T07:02:00.000Z',
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

/**
 * Render the dashboard over live incidents in all four live states, plus a
 * cause that fired three times.
 */
async function dashboardWithLiveIncidents(): Promise<void> {
  serveScenario('populated');
  const scenario = globalThis.fetch;
  const firing = (over: Record<string, unknown>): Record<string, unknown> => ({
    incident_id: 'inc',
    public_id: 'inc',
    correlation_key: 'detector:a:resource:one',
    title: 'A condition',
    summary: '',
    state: 'open',
    severity: 'critical',
    detector: 'alertmanager',
    subjects: ['one'],
    opened_at: '2026-08-26T09:00:00.000Z',
    ...over,
  });
  const incidents = [
    firing({ incident_id: 'a', public_id: 'a', summary: 'nobody has picked up' }),
    firing({
      incident_id: 'b',
      public_id: 'b',
      state: 'awaiting_human',
      summary: 'asked a person',
      opened_at: '2026-08-26T08:00:00.000Z',
    }),
    firing({
      incident_id: 'c',
      public_id: 'c',
      state: 'investigating',
      summary: 'agent is reading',
      opened_at: '2026-08-26T07:00:00.000Z',
    }),
    firing({
      incident_id: 'd',
      public_id: 'd',
      state: 'remediating',
      correlation_key: 'detector:b:resource:two',
      summary: 'agent is changing',
      opened_at: '2026-08-26T06:00:00.000Z',
    }),
    firing({
      incident_id: 'e',
      public_id: 'e',
      state: 'resolved',
      correlation_key: 'detector:b:resource:two',
      summary: 'over',
      opened_at: '2026-08-26T05:00:00.000Z',
    }),
  ];
  vi.stubGlobal('fetch', (input: unknown, init?: RequestInit) => {
    const address = new URL(String(input), FIXTURES_BASE);
    if (address.pathname === '/v1/incidents') {
      const wanted = address.searchParams.getAll('state');
      const served =
        wanted.length === 0
          ? incidents
          : incidents.filter((one) => wanted.includes(String(one.state)));
      return Promise.resolve(
        new Response(JSON.stringify({ incidents: served }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    }
    return scenario(input as Parameters<typeof fetch>[0], init);
  });
  render(await DashboardScreen(await surfaceContext({})));
}

/** Render the dashboard over three incidents that ended, two of them on their own. */
async function dashboardWithClosedIncidents(): Promise<void> {
  serveScenario('populated');
  const scenario = globalThis.fetch;
  const closed = [
    { state: 'resolved', self_resolved: true },
    { state: 'resolved', self_resolved: true },
    { state: 'closed_without_action', self_resolved: false },
  ].map((over, index) => ({
    incident_id: `inc-${String(index)}`,
    public_id: `inc-${String(index)}`,
    correlation_key: `detector:a:resource:${String(index)}`,
    title: 'A condition',
    summary: '',
    severity: 'critical',
    detector: 'alertmanager',
    subjects: [],
    opened_at: '2026-08-26T06:00:00.000Z',
    closed_at: '2026-08-26T07:00:00.000Z',
    ...over,
  }));
  vi.stubGlobal('fetch', (input: unknown, init?: RequestInit) => {
    const address = new URL(String(input), FIXTURES_BASE);
    if (address.pathname === '/v1/incidents') {
      const wanted = address.searchParams.getAll('state');
      return Promise.resolve(
        new Response(
          JSON.stringify({
            incidents: wanted.length === 0 ? closed : [],
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      );
    }
    return scenario(input as Parameters<typeof fetch>[0], init);
  });
  render(await DashboardScreen(await surfaceContext({})));
}

/** Render the dashboard with a run list every one of which settled clean. */
async function dashboardWithNothingButCleanFinishes(): Promise<void> {
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
                run_id: 'run-clean-1',
                status: 'completed',
                trigger: 'alert',
                started_at: '2026-08-07T10:00:00.000Z',
                finished_at: '2026-08-07T10:01:00.000Z',
                summary: 'Nothing was wrong; the alert cleared on its own.',
              },
              {
                run_id: 'run-clean-2',
                status: 'completed',
                trigger: 'manual',
                started_at: '2026-08-07T09:00:00.000Z',
                finished_at: '2026-08-07T09:01:00.000Z',
                summary: 'A second investigation, also concluded cleanly.',
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

  // 050-painel-vivo narrowed the visible "needs you" band to pending
  // remediation decisions only (Main.dc.html draws nothing else there), so
  // a failed run's own row -- and the link to /first-run this test checks
  // -- has no home in the redesigned band. Named in this feature's control
  // file as a capability with no explicit replacement, rather than silently
  // dropped: skipped, not deleted, so whoever decides where it belongs next
  // finds the test rather than rediscovering the gap from a bug report.
  it.skip('sends the band to the pending setup step, not to the run -- no surface for this in the redesigned band; see 050-painel-vivo/controle.md', () => {
    // Intentionally left unimplemented pending a decision on where a
    // systemic run failure should now be surfaced.
  });
});

// --- 2. Setup incomplete dominates the page ----------------------------------------------

describe('the setup hero', () => {
  it('is the dominant thing on the page while steps remain', async () => {
    await dashboard('first-run');

    const hero = screen.getByTestId('setup-hero');
    expect(hero).toBeInTheDocument();
    // Five — the deployment's own checklist (`setup.steps`), not the seven
    // wizard screens: the row count has to be the same list `outstanding()`
    // counts, or the pending number beside it stops matching what is drawn.
    expect(within(hero).getAllByTestId('setup-hero-step')).toHaveLength(5);
    // Exactly one step is where the deployment actually is.
    const current = within(hero)
      .getAllByTestId('setup-hero-step')
      .filter((step) => step.getAttribute('data-current') === 'true');
    expect(current).toHaveLength(1);
  });

  it('the number of rows drawn as not-done is the number the card states as remaining', async () => {
    // Not a stated number compared to another stated number: a stated
    // number compared to what a person could actually count in the list.
    await dashboard('first-run');

    const hero = screen.getByTestId('setup-hero');
    const notDone = within(hero)
      .getAllByTestId('setup-hero-step')
      .filter((step) => step.getAttribute('data-done') === 'false');
    const stated = /(\d+)\s+of\s+\d+/.exec(
      within(hero).getByTestId('setup-hero-progress').textContent,
    );
    expect(stated?.[1]).toBeDefined();
    expect(notDone).toHaveLength(Number(stated?.[1]));
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
    // 5 succeeded (by role) of 7 settled runs in the populated dataset. The
    // degraded run (run-0102) counts here too: the persistence store has no
    // status word of its own for "finished, but the answer came from
    // incomplete evidence" — it writes `completed` the same as a clean
    // finish — so the run status this figure reads from carries no signal
    // to withhold it on.
    expect(successRate?.textContent).toContain('71');
  });

  it('shows no rate at all when nothing has settled yet', async () => {
    // A deployment with no runs is where this page starts, not an edge case
    // to tolerate — dividing zero by zero is not "0%", it is a figure with
    // nothing behind it, and the em dash says so instead of a false number.
    await dashboard('empty');

    const figures = screen.getAllByTestId('figure');
    const successRate = figures.find(
      (figure) =>
        figure.getAttribute('data-figure') === EN['dashboard.stat.successRate'],
    );
    expect(successRate).toBeDefined();
    expect(successRate?.textContent).toContain('—');
    expect(successRate?.getAttribute('href')).toBe('/runs');
  });

  it('sends the drill-down at /runs, not /runs?status=failed, when nothing failed', async () => {
    // The failed-only filter is a shortcut to the runs that need attention.
    // A deployment with none owes the operator the ordinary list, not a
    // filtered one that would show nothing.
    await dashboardWithNothingButCleanFinishes();

    const figures = screen.getAllByTestId('figure');
    const successRate = figures.find(
      (figure) =>
        figure.getAttribute('data-figure') === EN['dashboard.stat.successRate'],
    );
    expect(successRate?.textContent).toContain('100');
    expect(successRate?.getAttribute('href')).toBe('/runs');
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

// --- 7. What is waiting on a person is counted correctly, even though the
//        band that used to list every kind of it now shows only decisions --

describe('the header\'s "blocked on you" count', () => {
  // 050-painel-vivo narrowed the visible band from a general "waiting on a
  // person" list (approvals, proposals, incidents, failed runs together) to
  // the inline decision band Main.dc.html draws -- pending remediations
  // only. The header count above the run band is the one place the broader
  // figure survives, reading the same underlying list these tests always
  // checked; what moved is that a row is no longer drawn for a kind the
  // decision band cannot render a decision control for, so these tests now
  // check the count rather than a row's text. The "oldest badge shouts"
  // case this section covered before is retired outright: the per-card
  // "since" replaced a single badge for the whole band, and there is
  // nothing left to test about capitalisation of a rendering that no
  // longer exists.
  //
  // A failed run that raised a configuration exception (`InvestigatorNotConfigured`)
  // used to get its own row here, pointed at `/first-run`. That specific
  // sentence has no home in the redesigned Painel and is named, not
  // silently dropped, in this feature's control file -- a future feature
  // owns deciding whether it needs one.

  it('does not count an incident that has already ended as one waiting on a person', async () => {
    // The regression this replaces: the screen dropped an incident only when
    // its state equalled `closed`, a word the store's enumeration does not
    // contain, so nothing was ever dropped and three finished incidents were
    // counted as three things waiting on a person.
    //
    // The three finished incidents this fixture serves must add zero to the
    // count -- checked as a delta against the "populated" scenario's own
    // baseline (its pending approvals, proposals and any failed run,
    // unrelated to what this test is about) rather than against zero
    // outright, because the fixture is shared and its baseline is not this
    // test's concern.
    await dashboardWithFinishedIncidents();
    const withFinishedIncidents = Number(
      screen.getByTestId('run-band-blocked-count').textContent,
    );

    await dashboard('populated');
    const baseline = Number(screen.getByTestId('run-band-blocked-count').textContent);

    expect(withFinishedIncidents).toBe(baseline);
  });

  it('tells the narrative that a self-resolved incident ended well', async () => {
    // The same comparison, a second time: because `closed` never matched, the
    // success branch of the activity feed was unreachable and an incident that
    // resolved itself was drawn in the same red as a live outage.
    await dashboardWithFinishedIncidents();

    const entries = screen.queryAllByTestId('activity-entry');
    const resolved = entries.find((entry) =>
      entry.textContent.includes('cleared upstream'),
    );
    expect(resolved).toBeDefined();
    expect(resolved?.querySelector('[class*="danger"]')).toBeNull();
  });

  it('asks for live incidents by name rather than hoping they are recent', async () => {
    // The listing answers with the fifty most recently *opened* incidents. On
    // an estate that closes a lot, an incident still open from Tuesday is
    // pushed off that page by Thursday's closures and vanishes from the one
    // screen whose job is to say what needs a person. So the screen names the
    // states it wants instead of filtering a page it hoped would contain them.
    const asked: string[] = [];
    serveScenario('populated');
    const scenario = globalThis.fetch;
    vi.stubGlobal('fetch', (input: unknown, init?: RequestInit) => {
      const address = new URL(String(input), FIXTURES_BASE);
      if (address.pathname === '/v1/incidents') {
        asked.push(address.search);
      }
      return scenario(input as Parameters<typeof fetch>[0], init);
    });
    render(await DashboardScreen(await surfaceContext({})));

    // Two narrowed reads, because they answer two questions: what is blocked
    // on a person, and what the agent is holding. Neither may be derived by
    // filtering a page of the fifty most recently opened.
    const blocked = asked.find((search) =>
      HUMAN_INCIDENT_STATES.every((state) => search.includes(`state=${state}`)),
    );
    const held = asked.find((search) =>
      AGENT_INCIDENT_STATES.every((state) => search.includes(`state=${state}`)),
    );
    expect(blocked).toBeDefined();
    expect(held).toBeDefined();
    expect(blocked).not.toBe(held);

    // The band's read carries neither what the agent is holding nor anything
    // terminal. Either would put the screen back to counting the product's own
    // work as the operator's backlog.
    for (const state of AGENT_INCIDENT_STATES) {
      expect(blocked).not.toContain(`state=${state}`);
    }
    for (const state of ['resolved', 'suppressed', 'closed_without_action']) {
      expect(blocked).not.toContain(`state=${state}`);
      expect(held).not.toContain(`state=${state}`);
    }
  });

  it('does not put what the agent is holding into what is waiting on you', async () => {
    // The distinction the screen never drew. An incident being investigated or
    // remediated is the agent's, and a product whose claim is that it works
    // without you must not use its first screen to count its own work as your
    // backlog. Only what nothing has picked up, or what stopped to ask a
    // person, counts toward "blocked on you" -- checked by count, since the
    // redesigned band no longer draws a row per incident (see the header
    // count section above for why).
    await dashboardWithLiveIncidents();
    const withLiveIncidents = Number(screen.getByTestId('run-band-blocked-count').textContent);

    await dashboard('populated');
    const baseline = Number(screen.getByTestId('run-band-blocked-count').textContent);

    // Two of the five fired incidents need a person (`open`, `awaiting_human`);
    // the other two (`investigating`, `remediating`) are the agent's own work
    // and must add nothing -- checked as a delta against the "populated"
    // baseline for the same reason the test above is.
    expect(withLiveIncidents - baseline).toBe(2);
  });

  it('folds what keeps happening into one row per cause', async () => {
    await dashboardWithLiveIncidents();

    const panel = screen.getByTestId('recurring-problems');
    const groups = within(panel).getAllByTestId('incident-group');
    // Five firings, two causes.
    expect(groups).toHaveLength(2);
    expect(groups.map((group) => group.getAttribute('data-count')).sort()).toEqual([
      '2',
      '3',
    ]);
  });

  it('counts only what the agent is holding, whatever the deployment answers with', async () => {
    // The narrowing is asked for in the query and held again here. A read is a
    // request, not a guarantee: a deployment that ignores the parameter — the
    // mock data plane does — would otherwise have this figure report every
    // open incident as one the agent had picked up, which is the same
    // overstatement in the opposite direction to the one this screen just
    // stopped making.
    await dashboardWithLiveIncidents();

    // One `investigating`, one `remediating`, out of five incidents served.
    expect(screen.getByTestId('run-band-followed-count')).toHaveTextContent('2');
  });

  it('leads with what is running before what needs a decision', async () => {
    await dashboardWithLiveIncidents();

    const band = screen.getByTestId('run-band');
    const decisions = screen.getByTestId('attention-decision-band');
    // The run band is the first thing on the page. `compareDocumentPosition`
    // says so structurally rather than by reading class names, so a later
    // layout change cannot quietly put the decision band back on top.
    expect(band.compareDocumentPosition(decisions)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it('shows five figures, and two of them are about the agent', async () => {
    await dashboardWithLiveIncidents();

    const figures = screen.getAllByTestId('figure');
    expect(figures).toHaveLength(5);
    const labels = figures.map((figure) => figure.getAttribute('data-figure'));
    expect(labels).toContain(EN['dashboard.stat.unattended']);
    // Four of the five count things. The fifth says how long an answer takes,
    // which is what somebody deciding whether to wait for the agent asks and
    // no tile on this page answered until it was added.
    expect(labels).toContain(EN['dashboard.stat.successRate']);
    expect(labels).toContain(EN['dashboard.stat.timeToCause']);
    // The two the band and the feed now answer better than a tile could.
    expect(labels).not.toContain(EN['dashboard.stat.healthy']);
    expect(labels).not.toContain(EN['dashboard.stat.runs']);
  });

  it('counts an incident that closed itself as one nobody had to touch', async () => {
    await dashboardWithClosedIncidents();

    const figure = screen
      .getAllByTestId('figure')
      .find(
        (one) => one.getAttribute('data-figure') === EN['dashboard.stat.unattended'],
      );
    expect(figure).toBeDefined();
    // Two of the three terminal incidents carry `self_resolved`.
    expect(figure).toHaveTextContent('67%');
    expect(figure).toHaveTextContent('2 of 3 incidents closed themselves');
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
