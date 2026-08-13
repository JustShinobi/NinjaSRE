import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { EstateStep, ESTATE_ENDPOINT } from '@/surfaces/first-run/estate';

/**
 * The estate step, against the three properties that make it a step rather than
 * a form.
 *
 * **A refused token is named, not summarised.** The privileges the cluster says
 * it does not hold are rendered one per line, each with the path it was needed
 * on and what stops working without it. A test asserting only that "something
 * red appeared" would pass against a generic failure, which is the exact
 * outcome this step exists to replace.
 *
 * **A gap that blocks nothing does not block.** The advisory list renders apart
 * and the verdict stays sufficient, because an operator whose token reads their
 * whole cluster must not be sent to widen it.
 *
 * **Confirming is unavailable until somebody has looked.** The preview is the
 * only thing that makes confirming an informed act, so the control is genuinely
 * disabled rather than merely discouraged — asserted by pressing it and finding
 * that no request was made.
 */

const LABELS = {
  integration: 'From {integration}.',
  check: 'Ask',
  checking: 'Asking',
  recheck: 'Ask again',
  sufficient: 'The token can read everything',
  insufficient: 'The token cannot read everything',
  missingRead: 'Missing:',
  missingAdvisory: 'Recommended and not held:',
  grantedAt: 'Granted at:',
  preview: 'Look',
  previewing: 'Looking',
  found: '{nodes} nodes, {guests} guests, {running} running, {zones} zones',
  unplaced: '{count} unplaced',
  incomplete: 'a floor rather than a total',
  confirm: 'Discover from now on',
  confirming: 'Registering',
  confirmed: 'Registered',
  needsPreview: 'Look first',
  refused: 'Refused:',
  unreachable: 'The deployment did not answer',
};

let calls: { url: string; body: unknown }[] = [];
let answers: Record<string, { status: number; payload: unknown }> = {};

function reply(action: string, payload: unknown, status = 200): void {
  answers[action] = { status, payload };
}

beforeEach(() => {
  calls = [];
  answers = {};
  vi.stubGlobal('fetch', (url: unknown, init: RequestInit) => {
    const raw = typeof init.body === 'string' ? init.body : '{}';
    const body: unknown = JSON.parse(raw);
    calls.push({ url: String(url), body });
    const action = String(Reflect.get(Object(body), 'action'));
    const answer = answers[action] ?? {
      status: 200,
      payload: { ok: true, result: {} },
    };
    return Promise.resolve(
      new Response(JSON.stringify(answer.payload), {
        status: answer.status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function draw(zones: Readonly<Record<string, string>> = {}): void {
  render(<EstateStep integration="proxmox" zones={zones} labels={LABELS} />);
}

it('names every privilege the cluster says the token does not hold', async () => {
  reply('report', {
    ok: true,
    reachable: true,
    result: {
      report: {
        privileges: {
          read_sufficient: false,
          missing_read: [
            'Sys.Syslog on / — without it, nothing can read the cluster log',
          ],
          missing_advisory: [],
          granted_at: 'Datacenter → Permissions',
        },
      },
    },
  });
  draw();

  await userEvent.click(screen.getByTestId('estate-check'));

  expect(screen.getByTestId('privilege-verdict')).toHaveTextContent(
    'The token cannot read everything',
  );
  expect(screen.getByTestId('privilege-gap')).toHaveTextContent(
    'Sys.Syslog on / — without it, nothing can read the cluster log',
  );
  expect(screen.getByTestId('privilege-granted-at')).toHaveTextContent(
    'Datacenter → Permissions',
  );
  expect(calls[0]?.url).toBe(ESTATE_ENDPOINT);
  expect(calls[0]?.body).toEqual({ action: 'report', integration: 'proxmox' });
});

it('shows a privilege nothing needs yet apart, and does not call the token broken', async () => {
  reply('report', {
    ok: true,
    reachable: true,
    result: {
      report: {
        privileges: {
          read_sufficient: true,
          missing_read: [],
          missing_advisory: ['SDN.Audit on / — without it, nothing can read the SDN'],
          granted_at: 'Datacenter → Permissions',
        },
      },
    },
  });
  draw();

  await userEvent.click(screen.getByTestId('estate-check'));

  expect(screen.getByTestId('privilege-verdict')).toHaveTextContent(
    'The token can read everything',
  );
  expect(screen.queryByTestId('privilege-missing')).toBeNull();
  expect(screen.getByTestId('privilege-advisory')).toHaveTextContent('SDN.Audit on /');
});

it('shows what a sweep would find, and says nothing was stored', async () => {
  reply('preview', {
    ok: true,
    reachable: true,
    result: {
      nodes: 2,
      guests: 57,
      running: 49,
      zones: 7,
      unplaced: 0,
      complete: true,
    },
  });
  draw({ '10.20.20.0/24': 'infra' });

  await userEvent.click(screen.getByTestId('estate-preview'));

  expect(screen.getByTestId('estate-counts')).toHaveTextContent(
    '2 nodes, 57 guests, 49 running, 7 zones',
  );
  expect(screen.queryByTestId('estate-unplaced')).toBeNull();
  expect(screen.queryByTestId('estate-incomplete')).toBeNull();
  expect(calls[0]?.body).toEqual({
    action: 'preview',
    integration: 'proxmox',
    zones: { '10.20.20.0/24': 'infra' },
  });
});

it('says how many fell outside every declared network rather than hiding them', async () => {
  reply('preview', {
    ok: true,
    reachable: true,
    result: {
      nodes: 2,
      guests: 57,
      running: 49,
      zones: 6,
      unplaced: 3,
      complete: false,
    },
  });
  draw();

  await userEvent.click(screen.getByTestId('estate-preview'));

  expect(screen.getByTestId('estate-unplaced')).toHaveTextContent('3 unplaced');
  expect(screen.getByTestId('estate-incomplete')).toHaveTextContent(
    'a floor rather than a total',
  );
});

it('cannot be confirmed before anybody has looked', async () => {
  draw();

  expect(screen.getByTestId('estate-needs-preview')).toBeInTheDocument();
  await userEvent.click(screen.getByTestId('estate-confirm'));

  expect(calls).toEqual([]);
  expect(screen.queryByTestId('estate-confirmed')).toBeNull();
});

it('registers the sweep once the counts have been read', async () => {
  reply('preview', {
    ok: true,
    reachable: true,
    result: {
      nodes: 2,
      guests: 57,
      running: 49,
      zones: 7,
      unplaced: 0,
      complete: true,
    },
  });
  reply('confirm', {
    ok: true,
    reachable: true,
    result: { job_id: 'estate.discovery:proxmox', interval_seconds: 300 },
  });
  draw();

  await userEvent.click(screen.getByTestId('estate-preview'));
  await userEvent.click(screen.getByTestId('estate-confirm'));

  expect(screen.getByTestId('estate-confirmed')).toHaveTextContent('Registered');
  expect(calls.map((call) => String(Reflect.get(Object(call.body), 'action')))).toEqual(
    ['preview', 'confirm'],
  );
});

it('forwards the deployment’s own words when it refuses', async () => {
  reply(
    'preview',
    {
      ok: false,
      reachable: true,
      reason: "No discovery source for 'proxmox' is composed in this deployment.",
      result: {},
    },
    404,
  );
  draw();

  await userEvent.click(screen.getByTestId('estate-preview'));

  expect(screen.getByTestId('estate-refused')).toHaveTextContent(
    'No discovery source for',
  );
  expect(screen.queryByTestId('estate-counts')).toBeNull();
  // Urgent for assistive technology, not routine status, and boxed rather
  // than a bare line — the same fix the model step and the credential form
  // both needed for the same reason: a refusal was carried by colour alone.
  expect(screen.getByTestId('estate-refused')).toHaveAttribute('role', 'alert');
});

it('says the deployment did not answer rather than blaming the cluster', async () => {
  reply('report', { ok: false, reachable: false }, 502);
  draw();

  await userEvent.click(screen.getByTestId('estate-check'));

  expect(screen.getByTestId('estate-unreachable')).toBeInTheDocument();
  expect(screen.queryByTestId('privilege-report')).toBeNull();
  expect(screen.getByTestId('estate-unreachable')).toHaveAttribute('role', 'alert');
});
