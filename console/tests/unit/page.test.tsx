import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import RunsPage from '@/app/page';

function answering(status: number, body: unknown): typeof fetch {
  return vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('the investigations screen', () => {
  it('lists what the gateway reported, with each run in its own role', async () => {
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', '');
    vi.stubGlobal(
      'fetch',
      answering(200, {
        runs: [
          { run_id: 'run-0001', status: 'succeeded', summary: 'A volume filled.' },
          { run_id: 'run-0002', status: 'failed', summary: null },
        ],
      }),
    );

    render(await RunsPage());

    expect(screen.getAllByTestId('run')).toHaveLength(2);
    expect(screen.getAllByTestId('run')[0]).toHaveAttribute('data-role', 'success');
    expect(screen.getAllByTestId('run')[1]).toHaveAttribute('data-role', 'danger');
    expect(screen.getByText('A volume filled.')).toBeInTheDocument();
  });

  it('says the deployment is empty rather than that the gateway failed', async () => {
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', '');
    vi.stubGlobal('fetch', answering(200, { runs: [] }));

    render(await RunsPage());

    expect(screen.getByTestId('empty')).toBeInTheDocument();
    expect(screen.queryByTestId('failure')).not.toBeInTheDocument();
  });

  it('distinguishes a refused read from an empty deployment', async () => {
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', '');
    vi.stubGlobal('fetch', answering(503, { detail: 'down' }));

    render(await RunsPage());

    expect(screen.getByTestId('failure')).toHaveTextContent('503');
    expect(screen.queryByTestId('empty')).not.toBeInTheDocument();
  });

  it('survives a gateway it cannot reach at all', async () => {
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', '');
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('network'))),
    );

    render(await RunsPage());

    expect(screen.getByTestId('failure')).toHaveTextContent('could not be reached');
  });

  it('ignores a record that is not a run rather than rendering a hole', async () => {
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', '');
    vi.stubGlobal('fetch', answering(200, { runs: [{ nonsense: true }, 'text'] }));

    render(await RunsPage());

    expect(screen.queryAllByTestId('run')).toHaveLength(0);
  });

  it('treats a body with no runs list as nothing to show', async () => {
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', '');
    vi.stubGlobal('fetch', answering(200, {}));

    render(await RunsPage());

    expect(screen.getByTestId('empty')).toBeInTheDocument();
  });
});
