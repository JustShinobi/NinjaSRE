import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { SchedulesDestinationsScreen } from '@/surfaces/settings/schedules-destinations';

import {
  principalHolding,
  serveScenario,
  serveScenarioExcept,
} from '../support/dataset';

/**
 * Schedules & destinations: the investigations that run on a clock, and
 * where an alert ends up once it has one.
 *
 * The reproduction this file exists to hold: the empty state used to tell an
 * operator "connect a chat or notification integration in the catalogue"
 * and then send the button that follows it to the raw configuration editor —
 * two different answers to "where do I fix this" on the same screen. Every
 * assertion in "the CTA defect, closed" is a fact this file first watched
 * fail against the pre-fix screen, and now proves against the fixed one.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

async function page(
  scenario: 'populated' | 'empty' = 'populated',
  principal?: unknown,
): Promise<void> {
  serveScenario(scenario, principal);
  render(await SchedulesDestinationsScreen(await surfaceContext({})));
}

/** The row for `destinationId`, narrowed by failing the test rather than by asserting. */
function requireDestinationRow(destinationId: string): HTMLElement {
  const row = screen
    .getAllByTestId('destination')
    .find((candidate) => candidate.getAttribute('data-destination') === destinationId);
  if (row === undefined) throw new Error(`no destination row for ${destinationId}`);
  return row;
}

describe('the page itself', () => {
  it('carries the Settings header, addressed as settings-schedules-destinations', async () => {
    await page();

    expect(screen.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-schedules-destinations',
    );
    expect(screen.getByTestId('page-header')).toHaveTextContent(
      'Schedules & destinations',
    );
  });
});

describe('the destinations declared', () => {
  it('declare their events, their channel, their detail and their masking policy', async () => {
    await page();

    const destination = requireDestinationRow('chat-incidents');
    expect(destination).toHaveTextContent('slack');
    expect(destination).toHaveTextContent('summary_with_link');
    expect(within(destination).getByTestId('destination-events')).toHaveTextContent(
      'investigation_concluded',
    );
    expect(within(destination).getByTestId('destination-masking')).toHaveTextContent(
      'standard',
    );
  });
});

describe('a delivery that did not arrive', () => {
  it('is visible with its reason and carries the control that sends it again', async () => {
    await page();

    const failed = screen.getByTestId('failed-delivery');
    expect(failed).toHaveTextContent('channel_not_found');
    expect(screen.getByTestId('resend-action')).toHaveTextContent('Send again');
  });

  it('is shown no re-send control for a reader who may not change any of it', async () => {
    await page('populated', principalHolding(['config.read']));

    expect(screen.queryByTestId('resend-action')).toBeNull();
  });
});

describe('a destination whose channel this deployment does not carry', () => {
  it('appears degraded, with the reason and a link to the credential that would fix it', async () => {
    await page();

    const degraded = requireDestinationRow('oncall-teams');

    const reason = within(degraded).getByTestId('destination-unusable');
    expect(reason).toHaveTextContent("No configured channel carries 'microsoft_teams'");

    const link = within(degraded).getByTestId('destination-credential-link');
    expect(link).toHaveAttribute('href', '/integrations/microsoft_teams');
  });

  it('leaves a healthy destination with no such link at all', async () => {
    await page();

    const healthy = requireDestinationRow('chat-incidents');
    expect(within(healthy).queryByTestId('destination-credential-link')).toBeNull();
    expect(within(healthy).queryByTestId('destination-unusable')).toBeNull();
  });
});

describe('the CTA defect, closed', () => {
  it('lands the empty state on the catalogue, filtered to communication — never on the schema editor', async () => {
    // The reproduction: a deployment with no channel that can carry a
    // message at all — the destinations panel renders its `empty` state
    // rather than the `<ul>` (see `Panel`), so the way back is found on the
    // panel itself. Before the fix, this same state's button carried
    // `href="/configuration"` while the sentence above it said "in the
    // catalogue" — two different answers to the same question.
    await page('empty');

    const cta = screen.getByTestId('way-back');
    expect(cta).toHaveAttribute('href', '/integrations?category=communication');
    expect(cta.getAttribute('href')).not.toBe('/configuration');
  });

  it('names the catalogue in the body the deployment itself wrote', async () => {
    await page('empty');

    expect(
      screen.getByText(/Connect a chat or notification integration in the catalogue/),
    ).toBeInTheDocument();
  });

  it('carries no view= narrowing — the one filter that would hide exactly what the operator needs to see', async () => {
    await page('empty');

    const cta = screen.getByTestId('way-back');
    expect(cta.getAttribute('href')).not.toContain('view=');
  });
});

describe('scheduled investigations with none set up yet', () => {
  it('names what is missing, why, and links to the form that fixes it', async () => {
    await page('empty', principalHolding(['config.read', 'schedule.manage']));

    const notice = screen.getByTestId('schedules-empty');
    expect(notice).toHaveTextContent('No scheduled investigations');
    expect(screen.getByRole('link', { name: 'Create one below' })).toHaveAttribute(
      'href',
      '#schedule-create',
    );
  });

  it('still shows the create form, rather than hiding it behind the notice', async () => {
    await page('empty', principalHolding(['config.read', 'schedule.manage']));

    expect(screen.getByTestId('create-schedule')).toBeInTheDocument();
  });
});

describe('scheduled investigations with something already on the calendar', () => {
  it('does not show the empty notice once a schedule exists', async () => {
    await page('populated', principalHolding(['config.read', 'schedule.manage']));

    expect(screen.queryByTestId('schedules-empty')).toBeNull();
    expect(screen.getAllByTestId('schedule').length).toBeGreaterThan(0);
  });

  it('shows a readable frequency preset selector beside the raw cron field, in the create form', async () => {
    await page('populated', principalHolding(['config.read', 'schedule.manage']));

    const createForm = within(screen.getByTestId('create-schedule'));
    expect(createForm.getByLabelText('Frequency')).toBeInTheDocument();
    expect(createForm.getByLabelText('Cron')).toBeInTheDocument();
  });
});

describe('a viewer who may not manage schedules', () => {
  it('renders no schedules panel at all, rather than one it cannot use', async () => {
    await page('populated', principalHolding(['config.read']));

    expect(screen.queryByTestId('schedules-empty')).toBeNull();
    expect(screen.queryByTestId('create-schedule')).toBeNull();
    // The rest of the page — destinations — still renders for this viewer.
    expect(screen.getByTestId('destinations')).toBeInTheDocument();
  });
});

describe('a column whose read the deployment refused', () => {
  it('fails alone, leaving destinations standing', async () => {
    serveScenarioExcept('populated', ['/v1/transit/deliveries']);
    render(await SchedulesDestinationsScreen(await surfaceContext({})));

    expect(screen.getByTestId('destinations')).toBeInTheDocument();
  });
});

/** A base for parsing a path-only address. Never contacted, and built rather
 * than written — the same convention `support/dataset.ts` uses. */
const FIXTURE_BASE = ['http:', '//fixtures.invalid'].join('');

/** The node the shared dataset's own populated principal resolves to. */
const CONFIG_NODE = 'org-northwind';

interface ListFieldStub {
  readonly path: string;
}

/** One array field, drawn as an editable, reorderable `ObjectList`. */
function listField(path: string): unknown {
  return {
    path,
    label: path,
    type: 'array',
    section: 'Destinations',
    value: [],
    provenance: '',
    set_here: false,
    item_fields: [
      {
        path: 'name',
        label: 'Name',
        type: 'string',
        help: '',
        allowed_values: null,
        minimum: null,
        maximum: null,
        default: '',
      },
    ],
  };
}

/**
 * `serveScenario('populated')`, with the configuration-service reads the two
 * advanced sections below make answered directly — the shared dataset
 * carries no `surfaces.*`/`transit.*` fields yet.
 */
function serveWithDestinationsConfig(
  fields: readonly ListFieldStub[],
  principal?: unknown,
): void {
  serveScenario('populated', principal);
  const base = globalThis.fetch;
  vi.stubGlobal('fetch', async (input: unknown, init?: RequestInit) => {
    const path = new URL(String(input), FIXTURE_BASE).pathname;
    if (path === `/v1/config/${CONFIG_NODE}/fields`) {
      return new Response(
        JSON.stringify({ fields: fields.map((f) => listField(f.path)) }),
        {
          status: 200,
          headers: { 'content-type': 'application/json' },
        },
      );
    }
    return base(input as string, init);
  });
}

describe('the advanced transit-routing section', () => {
  it('is collapsed on arrival and draws rules and destinations as editable, reorderable lists', async () => {
    serveWithDestinationsConfig([
      { path: 'transit.rules' },
      { path: 'transit.destinations' },
    ]);

    render(await SchedulesDestinationsScreen(await surfaceContext({})));

    const details = screen.getByTestId('advanced-config-transit');
    expect(details.tagName).toBe('DETAILS');
    expect((details as HTMLDetailsElement).open).toBe(false);

    for (const path of ['transit.rules', 'transit.destinations']) {
      const field = details.querySelector(
        `[data-testid="config-field"][data-path="${path}"]`,
      );
      expect(field).not.toBeNull();
      expect(field?.querySelector('[data-testid="object-list"]')).toBeInTheDocument();
    }
  });

  it('offers no editor to a viewer who may not write configuration', async () => {
    serveWithDestinationsConfig(
      [{ path: 'transit.rules' }],
      principalHolding(['config.read']),
    );

    render(await SchedulesDestinationsScreen(await surfaceContext({})));

    const details = screen.getByTestId('advanced-config-transit');
    expect(within(details).queryByTestId('ask-preview')).toBeNull();
  });
});

describe('the advanced surfaces-destinations section', () => {
  it('draws channels, report destinations and notification sinks as editable, reorderable lists', async () => {
    serveWithDestinationsConfig([
      { path: 'surfaces.channels' },
      { path: 'surfaces.report_destinations' },
      { path: 'surfaces.notification_sinks' },
    ]);

    render(await SchedulesDestinationsScreen(await surfaceContext({})));

    const details = screen.getByTestId('advanced-config-surfaces-destinations');
    expect(details.tagName).toBe('DETAILS');
    expect((details as HTMLDetailsElement).open).toBe(false);

    for (const path of [
      'surfaces.channels',
      'surfaces.report_destinations',
      'surfaces.notification_sinks',
    ]) {
      const field = details.querySelector(
        `[data-testid="config-field"][data-path="${path}"]`,
      );
      expect(field).not.toBeNull();
      expect(field?.querySelector('[data-testid="object-list"]')).toBeInTheDocument();
    }
  });

  it('never draws a control for surfaces.notification_policy or surfaces.console fields — those belong to other pages', async () => {
    serveScenario('populated');
    const base = globalThis.fetch;
    vi.stubGlobal('fetch', async (input: unknown, init?: RequestInit) => {
      const path = new URL(String(input), FIXTURE_BASE).pathname;
      if (path === `/v1/config/${CONFIG_NODE}/fields`) {
        return new Response(
          JSON.stringify({
            fields: [
              listField('surfaces.channels'),
              {
                path: 'surfaces.notification_policy.timezone',
                label: 'Timezone',
                type: 'string',
                section: 'Notifications',
                value: 'UTC',
                provenance: '',
                set_here: false,
              },
              {
                path: 'surfaces.console.tutorial_dismissed',
                label: 'Tutorial dismissed',
                type: 'boolean',
                section: 'Console',
                value: false,
                provenance: '',
                set_here: false,
              },
            ],
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        );
      }
      return base(input as string, init);
    });

    render(await SchedulesDestinationsScreen(await surfaceContext({})));

    const details = screen.getByTestId('advanced-config-surfaces-destinations');
    const paths = [...details.querySelectorAll('[data-testid="config-field"]')].map(
      (field) => field.getAttribute('data-path'),
    );
    expect(paths).toEqual(['surfaces.channels']);
  });
});
