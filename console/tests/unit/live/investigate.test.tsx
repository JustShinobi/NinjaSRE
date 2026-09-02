import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { InvestigateLauncher } from '@/live/investigate';
import {
  EMPTY_BRIEFING,
  LAUNCHER_ENDPOINT,
  type LauncherBriefing,
} from '@/shell/launcher';

/**
 * The launcher, as the board draws it: a centred modal whose suggestions come
 * from where the environment already is — never invented — and whose footer
 * says what starting one actually sets off.
 *
 * The degradation is the claim worth holding: with no recurring subject and
 * no unhealthy band, only the always-true audit offer appears. A launcher
 * that fabricated a suggestion would be this console inventing an incident.
 *
 * The briefing is asked for when the drawer opens, not carried by the frame:
 * three gateway reads for a drawer most page views never open were three
 * reads on every render of every screen. Until it arrives the drawer is the
 * same drawer with the empty briefing, which it already renders honestly.
 */

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: () => undefined }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

/** A courier that answers `briefing` at once. */
function briefed(briefing: LauncherBriefing): () => Promise<LauncherBriefing> {
  return () => Promise.resolve(briefing);
}

function launcher(
  overrides: Partial<Parameters<typeof InvestigateLauncher>[0]> = {},
): void {
  render(
    <InvestigateLauncher
      open
      locale="pt-BR"
      onClose={() => undefined}
      deploymentName="HAL9000"
      posture="propose"
      askBriefing={briefed(EMPTY_BRIEFING)}
      {...overrides}
    />,
  );
}

describe('the suggestions block', () => {
  it('offers all three when the environment supports all three', async () => {
    launcher({
      askBriefing: briefed({
        teamName: 'Platform',
        recurring: { subject: 'RedisExporterDown', count: 8 },
        unhealthy: 14,
      }),
    });

    expect(await screen.findByText(/RedisExporterDown/)).toBeInTheDocument();
    const offered = screen
      .getAllByTestId('investigate-suggestion')
      .map((each) => each.getAttribute('data-suggestion'));
    expect(offered).toEqual(['recurring', 'unhealthy', 'audit']);
    expect(screen.getByText(/8 disparos/)).toBeInTheDocument();
    expect(screen.getByText(/14 recursos/)).toBeInTheDocument();
  });

  it('degrades honestly to the audit alone when there is no data for the others', () => {
    launcher();

    const offered = screen
      .getAllByTestId('investigate-suggestion')
      .map((each) => each.getAttribute('data-suggestion'));
    expect(offered).toEqual(['audit']);
    expect(screen.getByText(/HAL9000/)).toBeInTheDocument();
  });

  it('fills the objective with the clicked suggestion', async () => {
    launcher();

    await userEvent.click(screen.getByTestId('investigate-suggestion'));
    expect(screen.getByLabelText(/investigado/i)).toHaveValue(
      'Auditar a saúde geral do cluster HAL9000',
    );
  });
});

describe('the shortcut and the footer', () => {
  it('starts on Ctrl+Enter once an objective is given', async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((_: unknown, init: RequestInit) => {
        calls.push(typeof init.body === 'string' ? init.body : '');
        return Promise.resolve(
          new Response(JSON.stringify({ runId: 'run-7' }), { status: 200 }),
        );
      }),
    );
    const went: string[] = [];
    launcher({ navigate: (href) => went.push(href) });

    const field = screen.getByLabelText(/investigado/i);
    await userEvent.type(field, 'o primário está inalcançável');
    await userEvent.keyboard('{Control>}{Enter}{/Control}');

    expect(calls.length).toBe(1);
    expect(went).toEqual(['/runs/run-7']);
  });

  it('says what will run, with the team and the posture, above the two controls', async () => {
    launcher({
      askBriefing: briefed({ teamName: 'Platform', recurring: null, unhealthy: 0 }),
    });

    expect(
      await screen.findByText(/Vai rodar com o time Platform/),
    ).toBeInTheDocument();
    expect(screen.getByTestId('investigate-team')).toHaveTextContent(
      'Vai rodar com o time Platform',
    );
    expect(screen.getByTestId('investigate-team')).toHaveTextContent('apenas propõe');
    expect(screen.getByText(/6 estágios/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Cancelar/ })).toBeInTheDocument();
    expect(screen.getByTestId('start-investigation')).toHaveTextContent('Investigar');
  });

  it('says only the posture when the tree never named the team', () => {
    launcher();

    expect(screen.getByTestId('investigate-team')).toHaveTextContent('apenas propõe');
    expect(screen.getByTestId('investigate-team')).not.toHaveTextContent('o time');
  });
});

describe('where the briefing comes from', () => {
  it('asks the courier once when it opens, and shows the answer when it arrives', async () => {
    let answer: (briefing: LauncherBriefing) => void = () => undefined;
    const fetching = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          answer = (briefing) => {
            resolve(new Response(JSON.stringify(briefing), { status: 200 }));
          };
        }),
    );
    vi.stubGlobal('fetch', fetching);
    render(
      <InvestigateLauncher
        open
        locale="pt-BR"
        onClose={() => undefined}
        deploymentName="HAL9000"
        posture="propose"
      />,
    );

    // Asked once, at the courier, uncached — and the drawer is already on
    // screen with the honest floor while the answer is in flight.
    expect(fetching).toHaveBeenCalledTimes(1);
    const [address, init] = fetching.mock.calls[0] as unknown as [string, RequestInit];
    expect(address).toBe(LAUNCHER_ENDPOINT);
    expect(init.cache).toBe('no-store');
    expect(
      screen
        .getAllByTestId('investigate-suggestion')
        .map((each) => each.getAttribute('data-suggestion')),
    ).toEqual(['audit']);
    expect(screen.getByTestId('investigate-team')).not.toHaveTextContent('o time');

    answer({
      teamName: 'Platform',
      recurring: { subject: 'RedisExporterDown', count: 8 },
      unhealthy: 14,
    });

    expect(await screen.findByText(/RedisExporterDown/)).toBeInTheDocument();
    expect(screen.getByTestId('investigate-team')).toHaveTextContent(
      'Vai rodar com o time Platform',
    );
    expect(fetching).toHaveBeenCalledTimes(1);
  });

  it('asks nothing while closed', () => {
    const fetching = vi.fn(() => Promise.reject(new Error('should not be asked')));
    vi.stubGlobal('fetch', fetching);
    render(
      <InvestigateLauncher
        open={false}
        locale="pt-BR"
        onClose={() => undefined}
        deploymentName="HAL9000"
      />,
    );

    expect(fetching).not.toHaveBeenCalled();
  });

  it('keeps the empty briefing when the courier refuses', async () => {
    const fetching = vi.fn(() => Promise.resolve(new Response('{}', { status: 401 })));
    vi.stubGlobal('fetch', fetching);
    render(
      <InvestigateLauncher
        open
        locale="pt-BR"
        onClose={() => undefined}
        deploymentName="HAL9000"
        posture="propose"
      />,
    );

    await vi.waitFor(() => {
      expect(fetching.mock.results.length).toBe(1);
    });
    await Promise.resolve();

    expect(
      screen
        .getAllByTestId('investigate-suggestion')
        .map((each) => each.getAttribute('data-suggestion')),
    ).toEqual(['audit']);
    expect(screen.getByTestId('investigate-team')).toHaveTextContent('apenas propõe');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
