import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DetectorControls } from '@/surfaces/detector-controls';
import type { Viewer } from '@/session/viewer';

/**
 * Turning a detector on, and the dry run the enable flow always offers first.
 *
 * Enabling a detector decides what starts paging somebody, so the control
 * never goes straight from off to on: it asks the deployment what the
 * detector would have concluded against the signals already stored, and only
 * once that answer is on the screen does a control to actually enable it
 * exist. Disabling needs none of that — it only narrows what can happen.
 */

let sent: { operation: string; detectorId: string }[] = [];

const DRY_RUN = {
  detector_id: 'datastore-near-full',
  would_fire: true,
  fired: false,
  observations: [
    {
      detector: 'datastore-near-full',
      subject: 'datastore-pve02',
      verdict: 'firing',
      detail: '94% full',
      evidence: {},
      observed_at: '2026-08-11T00:00:00+00:00',
    },
  ],
};

function answerWith(answer: unknown, status = 200): void {
  vi.stubGlobal('fetch', (_url: unknown, init: RequestInit) => {
    const body: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    sent.push({
      operation: String(Reflect.get(Object(body), 'operation')),
      detectorId: String(Reflect.get(Object(body), 'detectorId')),
    });
    return Promise.resolve(
      new Response(JSON.stringify({ ok: status < 400, reachable: true, answer }), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  sent = [];
  answerWith(DRY_RUN);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const LABELS = {
  dryRun: 'Preview what this would fire on',
  dryRunning: 'Checking…',
  wouldFire: 'This would fire against what is stored now.',
  wouldNotFire: 'This would not fire against what is stored now.',
  observations: 'What it would conclude now',
  noObservations: 'Nothing is observed for this detector yet.',
  enable: 'Enable',
  enabling: 'Enabling…',
  disable: 'Disable',
  disabling: 'Disabling…',
  cancel: 'Cancel',
  failed: 'The deployment refused this.',
  unreachable: 'The deployment could not be reached.',
};

function viewer(permissions: readonly string[]): Viewer {
  return {
    principalId: 'user-under-test',
    displayName: 'Avery Lockhart',
    email: null,
    roles: [],
    permissions: [...permissions],
    teamNodeId: 'team-platform',
    impersonating: false,
    impersonatedBy: null,
  };
}

function controls(
  enabled: boolean,
  permissions: readonly string[] = ['incident.manage'],
): void {
  render(
    <DetectorControls
      detectorId="datastore-near-full"
      enabled={enabled}
      viewer={viewer(permissions)}
      labels={LABELS}
    />,
  );
}

describe('a viewer without the permission', () => {
  it('sees no control at all, enabled or not', () => {
    const off = render(
      <DetectorControls
        detectorId="datastore-near-full"
        enabled={false}
        viewer={viewer(['incident.read'])}
        labels={LABELS}
      />,
    );
    expect(off.container.firstChild).toBeNull();

    const on = render(
      <DetectorControls
        detectorId="datastore-near-full"
        enabled
        viewer={viewer(['incident.read'])}
        labels={LABELS}
      />,
    );
    expect(on.container.firstChild).toBeNull();
    expect(sent).toHaveLength(0);
  });
});

describe('enabling a detector', () => {
  it('offers the dry run and shows what it would have fired on, before anything is enabled', async () => {
    controls(false);

    expect(screen.queryByTestId('enable-detector')).toBeNull();
    await userEvent.click(screen.getByTestId('dry-run-detector'));

    expect(sent).toEqual([{ operation: 'dry-run', detectorId: 'datastore-near-full' }]);
    const preview = await screen.findByTestId('detector-dry-run');
    expect(preview).toHaveTextContent(LABELS.wouldFire);
    const observation = screen.getByTestId('detector-dry-run-observation');
    expect(observation).toHaveTextContent('datastore-pve02');

    // Still nothing enabled: only the preview happened.
    expect(sent).toHaveLength(1);
  });

  it('enables only after the preview, and sends the enable write second', async () => {
    controls(false);

    await userEvent.click(screen.getByTestId('dry-run-detector'));
    await screen.findByTestId('detector-dry-run');
    await userEvent.click(screen.getByTestId('enable-detector'));

    expect(sent.map((each) => each.operation)).toEqual(['dry-run', 'enable']);
    expect(await screen.findByTestId('disable-detector')).toBeInTheDocument();
  });

  it('says what it would not fire on just as plainly', async () => {
    answerWith({ ...DRY_RUN, would_fire: false, observations: [] });
    controls(false);

    await userEvent.click(screen.getByTestId('dry-run-detector'));

    const preview = await screen.findByTestId('detector-dry-run');
    expect(preview).toHaveTextContent(LABELS.wouldNotFire);
    expect(preview).toHaveTextContent(LABELS.noObservations);
  });

  it('cancels the preview without enabling anything', async () => {
    controls(false);

    await userEvent.click(screen.getByTestId('dry-run-detector'));
    await screen.findByTestId('detector-dry-run');
    await userEvent.click(screen.getByTestId('cancel-detector-preview'));

    expect(screen.queryByTestId('detector-dry-run')).toBeNull();
    expect(sent).toHaveLength(1);
  });

  it('reports the deployment’s own refusal of the preview', async () => {
    controls(false);
    answerWith({}, 400);

    await userEvent.click(screen.getByTestId('dry-run-detector'));

    expect(await screen.findByTestId('detector-control-failure')).toHaveTextContent(
      LABELS.failed,
    );
  });

  it('says it could not be reached, which is a different machine to look at', async () => {
    controls(false);
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.click(screen.getByTestId('dry-run-detector'));

    expect(await screen.findByTestId('detector-control-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});

describe('disabling a detector', () => {
  it('is one control and one write, with no preview in front of it', async () => {
    answerWith({ detector_id: 'datastore-near-full', enabled: false });
    controls(true);

    expect(screen.queryByTestId('dry-run-detector')).toBeNull();
    await userEvent.click(screen.getByTestId('disable-detector'));

    expect(sent).toEqual([{ operation: 'disable', detectorId: 'datastore-near-full' }]);
    expect(await screen.findByTestId('dry-run-detector')).toBeInTheDocument();
  });

  it('reports a refusal without changing the badge', async () => {
    controls(true);
    answerWith({}, 403);

    await userEvent.click(screen.getByTestId('disable-detector'));

    expect(await screen.findByTestId('detector-control-failure')).toHaveTextContent(
      LABELS.failed,
    );
    expect(screen.getByTestId('disable-detector')).toBeInTheDocument();
  });
});
