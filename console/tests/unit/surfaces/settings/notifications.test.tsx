import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { surfaceContext } from '@/surfaces/context';
import { NotificationsSettingsScreen } from '@/surfaces/settings/notifications';

/**
 * Notifications: the attention policy, as named controls instead of buried
 * schema — quiet hours, repeat suppression, the hourly ceiling.
 */

const BASE = ['http:', '//fixtures.invalid'].join('');

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === 'ninjasre_session' ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

const NODE = 'org-northwind';

const SINGLE_NODE = {
  kind: 'organisation',
  name: 'Northwind',
  node_id: NODE,
  parent_id: null,
};

const WRITER = {
  principal_id: 'user-operator',
  display_name: 'Avery Lockhart',
  email: 'avery.lockhart@example.invalid',
  kind: 'person',
  roles: ['owner'],
  permissions: ['config.read', 'config.write'],
  team_node_id: NODE,
  impersonated_by: null,
  impersonating: false,
};

const READER = { ...WRITER, principal_id: 'user-viewer', permissions: ['config.read'] };

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

const NOTIFICATION_POLICY = {
  quiet_hours_enabled: true,
  quiet_hours_start: 22,
  quiet_hours_end: 7,
  timezone: 'Pacific/Auckland',
  cooldown_seconds: 900,
  notifications_per_hour: 12,
};

const NOTIFICATION_FIELDS = [
  {
    path: 'surfaces.notification_policy.quiet_hours_enabled',
    label: 'Quiet hours enabled',
    type: 'boolean',
    help: 'Hold non-urgent notifications during the hours set below.',
    section: 'Notification policy',
    section_help: 'Every value here can only make the platform ceiling stricter.',
    value: true,
    provenance: NODE,
    set_here: true,
    locked_by: '',
    approval_gated: false,
    allowed_values: null,
    minimum: null,
    maximum: null,
    default: false,
  },
  {
    path: 'surfaces.notification_policy.notifications_per_hour',
    label: 'Notifications per hour',
    type: 'integer',
    help: 'The most notifications this team receives in an hour.',
    section: 'Notification policy',
    section_help: 'Every value here can only make the platform ceiling stricter.',
    value: 12,
    provenance: NODE,
    set_here: true,
    locked_by: '',
    approval_gated: false,
    allowed_values: null,
    minimum: 0,
    maximum: 20,
    default: 20,
  },
];

interface Stub {
  readonly principal?: unknown;
  readonly values?: unknown;
  readonly provenance?: Readonly<Record<string, string>>;
  readonly fields?: readonly unknown[];
}

function serveNotifications({
  principal = WRITER,
  values = { surfaces: { notification_policy: NOTIFICATION_POLICY } },
  provenance = {
    'surfaces.notification_policy.quiet_hours_enabled': NODE,
    'surfaces.notification_policy.notifications_per_hour': NODE,
  },
  fields = NOTIFICATION_FIELDS,
}: Stub = {}): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    if (path === '/auth/me') return Promise.resolve(respond(principal));
    if (path === '/v1/config')
      return Promise.resolve(respond({ nodes: [SINGLE_NODE] }));
    if (path === `/v1/config/${NODE}`) {
      return Promise.resolve(respond({ node_id: NODE, values, provenance }));
    }
    if (path === `/v1/config/${NODE}/fields`) {
      return Promise.resolve(respond({ fields }));
    }
    if (path === '/v1/setup/checklist') return Promise.resolve(respond({}, 404));
    return Promise.resolve(respond({}, 404));
  });
}

async function renderNotifications(): Promise<void> {
  render(await NotificationsSettingsScreen(await surfaceContext({})));
}

describe('the notification policy page', () => {
  it('shows every control with its effective value and origin', async () => {
    serveNotifications();

    await renderNotifications();

    const rows = screen.getAllByTestId('effective-field');
    const paths = rows.map((row) => row.getAttribute('data-path'));
    expect(paths).toContain('surfaces.notification_policy.quiet_hours_enabled');
    expect(paths).toContain('surfaces.notification_policy.timezone');
    expect(paths).toContain('surfaces.notification_policy.notifications_per_hour');
  });

  it('carries the existing contract note, translated rather than invented', async () => {
    serveNotifications();

    await renderNotifications();

    expect(screen.getByTestId('notifications-contract-note')).toHaveTextContent(
      /can only make the platform ceiling stricter/i,
    );
  });

  it('offers the editor to a viewer who may write configuration', async () => {
    serveNotifications();

    await renderNotifications();

    expect(screen.getByTestId('config-editor')).toBeInTheDocument();
    expect(screen.getAllByTestId('config-field').length).toBe(
      NOTIFICATION_FIELDS.length,
    );
  });

  it('leaves out the editor for a viewer who may not, keeping the read-only rows', async () => {
    serveNotifications({ principal: READER });

    await renderNotifications();

    expect(screen.queryByTestId('config-editor')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('effective-field').length).toBeGreaterThan(0);
  });

  it('shows the panel empty, drawing neither the table nor the editor, when no node resolves', async () => {
    // A deployment with no organisation tree yet and a viewer tied to none of
    // it — `resolveNode` returns `''`, and both the field catalogue and the
    // effective-configuration read are skipped rather than built into a path
    // with an empty brace in it.
    serveNotifications({
      principal: { ...WRITER, team_node_id: '' },
    });
    vi.stubGlobal('fetch', (input: unknown) => {
      const path = new URL(String(input), BASE).pathname;
      if (path === '/auth/me')
        return Promise.resolve(respond({ ...WRITER, team_node_id: '' }));
      if (path === '/v1/config') return Promise.resolve(respond({ nodes: [] }));
      if (path === '/v1/setup/checklist') return Promise.resolve(respond({}, 404));
      return Promise.resolve(respond({}, 404));
    });

    await renderNotifications();

    expect(screen.queryByTestId('effective-field')).not.toBeInTheDocument();
    expect(screen.queryByTestId('config-editor')).not.toBeInTheDocument();
  });
});
