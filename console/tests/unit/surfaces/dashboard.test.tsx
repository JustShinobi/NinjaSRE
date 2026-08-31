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

/** `hours` before the real clock, as an ISO instant -- so a fixture that
 * needs to sit inside `subjectsInWindow`'s trailing 48h stays inside it
 * whenever the suite runs, rather than decaying out of the window the
 * day after whichever date it was written against. */
function hoursAgo(hours: number): string {
  return new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
}

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
function emptyCollectionResponse(key: string): Response {
  return new Response(JSON.stringify({ [key]: [] }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

/** Whether `path` is one this file isolates away from the "populated" baseline
 * so an incidents-only override is not diluted by that scenario's own
 * pending approvals, proposals and runs. */
function isolatedEmptyPath(path: string): string | null {
  if (path === '/v1/approvals') return 'approvals';
  if (path === '/v1/proposals') return 'proposals';
  if (path === '/v1/runs') return 'runs';
  return null;
}

async function dashboardWithFinishedIncidents(): Promise<void> {
  serveScenario('populated');
  const scenario = globalThis.fetch;
  vi.stubGlobal('fetch', (input: unknown, init?: RequestInit) => {
    const path = new URL(String(input), FIXTURES_BASE).pathname;
    const isolated = isolatedEmptyPath(path);
    if (isolated !== null) {
      return Promise.resolve(emptyCollectionResponse(isolated));
    }
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
async function dashboardWithLiveIncidents(
  options: { isolate?: boolean } = {},
): Promise<void> {
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
    opened_at: hoursAgo(1),
    ...over,
  });
  const incidents = [
    firing({ incident_id: 'a', public_id: 'a', summary: 'nobody has picked up' }),
    firing({
      incident_id: 'b',
      public_id: 'b',
      state: 'awaiting_human',
      summary: 'asked a person',
      opened_at: hoursAgo(2),
    }),
    firing({
      incident_id: 'c',
      public_id: 'c',
      state: 'investigating',
      summary: 'agent is reading',
      opened_at: hoursAgo(3),
    }),
    firing({
      incident_id: 'd',
      public_id: 'd',
      state: 'remediating',
      correlation_key: 'detector:b:resource:two',
      summary: 'agent is changing',
      opened_at: hoursAgo(4),
    }),
    firing({
      incident_id: 'e',
      public_id: 'e',
      state: 'resolved',
      correlation_key: 'detector:b:resource:two',
      summary: 'over',
      opened_at: hoursAgo(5),
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
    // `isolate` neutralises the "populated" scenario's own pending
    // approvals, proposals and runs -- the header's "blocked on you" count
    // reads all four sources together, and the incidents override above
    // *replaces* what the fixture would otherwise serve rather than adding
    // to it, so a test asserting the incidents' own contribution has to
    // silence the other three or it is comparing against a number this
    // function never controlled in the first place.
    if (options.isolate === true) {
      const isolated = isolatedEmptyPath(address.pathname);
      if (isolated !== null) {
        return Promise.resolve(emptyCollectionResponse(isolated));
      }
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

  // 050-painel-vivo narrowed the visible "needs you" band to pending
  // remediation decisions only, so the translated failure message this
  // checked for -- previously drawn as an attention row -- has no surface
  // left to render on. Skipped, not deleted; see the note beside the other
  // failed-run test below and this feature's control file.
  it.skip('says what an operator can do about it, in words meant for them -- no surface for this in the redesigned band; see 050-painel-vivo/controle.md', () => {
    expect(EN['failure.investigator.title']).toBeTruthy();
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
  // 050-painel-vivo moved the degraded KPI from a client computation over
  // `/v1/estate/summary` and `/v1/detectors` to GET /v1/overview's own
  // `degraded` field, read verbatim by KpiTiles (FR-019: no client
  // recomputation of a number the endpoint already answers). The claims
  // these three tests held -- the "N of M detectors" legend, degraded vs.
  // unhealthy counting only the two problem states, the drill-down href --
  // are the gateway's own aggregation and the tile's own rendering now, not
  // this screen's: tests/contract/gateway/test_overview_routes.py and
  // kpi-tiles.test.tsx ("names the no-detector case on the degraded tile,
  // with a link to configuration"). Skipped, not deleted, because a screen
  // that stubs `/v1/estate/summary`/`/v1/detectors` no longer changes what
  // this KPI shows -- only stubbing `/v1/overview` itself would, which is
  // exactly the property FR-019 asks for.
  it.skip('explains the degraded count rather than leaving it to guess -- moved to GET /v1/overview; see kpi-tiles.test.tsx and test_overview_routes.py', () => {
    // Intentionally left unimplemented: the computation this asserted no
    // longer lives in this screen.
  });

  it.skip('counts only degraded and unhealthy states, not unknown or stale observations -- moved to GET /v1/overview; see test_overview_routes.py', () => {
    // Intentionally left unimplemented: the computation this asserted no
    // longer lives in this screen.
  });

  it.skip("sends the problem figure to the resource list that contains both problem states -- the href is KpiTiles' own now; see kpi-tiles.test.tsx", () => {
    // Intentionally left unimplemented: the href this asserted is declared
    // inside kpi-tiles.tsx, not derived here.
  });
});

// --- 4. At least one number is about the agent, not the estate ----------------------------

describe('an indicator of whether the agent itself is working', () => {
  // 050-painel-vivo moved the success-rate KPI from a client computation
  // over the runs listing to GET /v1/overview's own `success_rate` field.
  // The three claims these tests held -- the settled/succeeded arithmetic,
  // the unmeasured em dash, the drill-down href when nothing has failed --
  // are the gateway's own aggregation and the tile's own rendering now:
  // tests/contract/gateway/test_overview_routes.py and kpi-tiles.test.tsx
  // ("says a rate with nothing to measure is unmeasured, never a fabricated
  // zero"). Skipped, not deleted, for the same reason as the degraded KPI
  // above: stubbing the runs listing no longer changes what this tile
  // shows, which is the point of reading only the overview.
  it.skip('shows a success rate figure, drawn from the runs the deployment recorded -- moved to GET /v1/overview; see kpi-tiles.test.tsx and test_overview_routes.py', () => {
    // Intentionally left unimplemented: the computation this asserted no
    // longer lives in this screen.
  });

  it.skip('shows no rate at all when nothing has settled yet -- moved to GET /v1/overview; see kpi-tiles.test.tsx', () => {
    // Intentionally left unimplemented: the null-value case this asserted
    // is KpiTiles' own rendering now, exercised directly with a null value.
  });

  it.skip('sends the drill-down at /runs, not /runs?status=failed, when nothing failed -- KpiTiles links successRate to /runs unconditionally; see kpi-tiles.tsx', () => {
    // Intentionally left unimplemented: the conditional href this asserted
    // does not exist in the new tile, which the control file names as a
    // simplification the artboard itself does not distinguish either.
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
    // The fixture also isolates away the "populated" scenario's own
    // pending approvals, proposals and runs (see isolatedEmptyPath), so the
    // count read here is the incidents' own contribution alone: zero, for
    // three incidents that have all ended.
    await dashboardWithFinishedIncidents();

    expect(screen.getByTestId('run-band-blocked-count')).toHaveTextContent('0');
  });

  it('tells the narrative that a self-resolved incident ended well', async () => {
    // The same comparison, a second time: because `closed` never matched, the
    // success branch of the activity feed was unreachable and an incident that
    // resolved itself was drawn in the same red as a live outage. 050-painel-vivo
    // gives this its own 'resolution' kind (a filled circle) rather than the
    // danger-coloured 'incident' square its opening earns.
    await dashboardWithFinishedIncidents();

    const entries = screen.queryAllByTestId('activity-feed-entry');
    const resolved = entries.find((entry) =>
      entry.textContent.includes('cleared upstream'),
    );
    expect(resolved).toBeDefined();
    expect(resolved?.getAttribute('data-kind')).toBe('resolution');
    expect(resolved?.querySelector('[class*="bg-danger"]')).toBeNull();
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
    // Isolated the same way the test above is: with the "populated"
    // scenario's own approvals, proposals and runs silenced, the count is
    // the incidents' own contribution alone.
    await dashboardWithLiveIncidents({ isolate: true });

    // Two of the five fired incidents need a person (`open`, `awaiting_human`);
    // the other two (`investigating`, `remediating`) are the agent's own
    // work and must add nothing.
    expect(screen.getByTestId('run-band-blocked-count')).toHaveTextContent('2');
  });

  it('folds what keeps happening into one row per cause, windowed to the last 48h', async () => {
    // 050-painel-vivo replaced the flat IncidentGroupList disclosure on this
    // screen with SubjectStrip, windowed to SUBJECT_WINDOW_HOURS -- the same
    // five firings/two causes claim, read off the new component's own rows.
    await dashboardWithLiveIncidents();

    const panel = screen.getByTestId('recurring-problems');
    const rows = within(panel).getAllByTestId('subject-row');
    expect(rows).toHaveLength(2);
    expect(
      rows.map((row) => within(row).getByTestId('subject-count').textContent).sort(),
    ).toEqual(['2×', '3×']);
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

  it('shows five KPI tiles, two of them about the agent rather than the estate', async () => {
    // 050-painel-vivo replaced the client-computed <Figure> grid with
    // KpiTiles reading GET /v1/overview -- five named tiles rather than a
    // count, since which five is the claim (selfResolved and successRate are
    // the two the reference design leads with and this page, until then,
    // never asked).
    await dashboardWithLiveIncidents();

    const tiles = screen.getAllByTestId('kpi-tile');
    expect(tiles).toHaveLength(5);
    const kinds = tiles.map((tile) => tile.getAttribute('data-kpi'));
    expect(kinds.sort()).toEqual(
      ['watched', 'degraded', 'selfResolved', 'successRate', 'timeToCause'].sort(),
    );
  });

  // 050-painel-vivo moved the "closed on their own" KPI from a client
  // computation over the incidents listing to GET /v1/overview's own
  // `self_resolved` field. The 67%/"2 of 3" arithmetic this asserted is the
  // gateway's own aggregation now: tests/contract/gateway/test_overview_routes.py
  // and kpi-tiles.test.tsx ("shows the watched count and its breakdown...").
  it.skip('counts an incident that closed itself as one nobody had to touch -- moved to GET /v1/overview; see kpi-tiles.test.tsx and test_overview_routes.py', () => {
    // Intentionally left unimplemented: the computation this asserted no
    // longer lives in this screen.
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
