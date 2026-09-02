import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { InvestigateLauncher } from '@/live/investigate';

/**
 * The launcher, as the board draws it: a centred modal whose suggestions come
 * from where the environment already is — never invented — and whose footer
 * says what starting one actually sets off.
 *
 * The degradation is the claim worth holding: with no recurring subject and
 * no unhealthy band, only the always-true audit offer appears. A launcher
 * that fabricated a suggestion would be this console inventing an incident.
 */

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: () => undefined }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

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
      {...overrides}
    />,
  );
}

describe('the suggestions block', () => {
  it('offers all three when the environment supports all three', () => {
    launcher({
      briefing: {
        teamName: 'Platform',
        recurring: { subject: 'RedisExporterDown', count: 8 },
        unhealthy: 14,
      },
    });

    const offered = screen
      .getAllByTestId('investigate-suggestion')
      .map((each) => each.getAttribute('data-suggestion'));
    expect(offered).toEqual(['recurring', 'unhealthy', 'audit']);
    expect(screen.getByText(/RedisExporterDown/)).toBeInTheDocument();
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

  it('says what will run, with the team and the posture, above the two controls', () => {
    launcher({
      briefing: { teamName: 'Platform', recurring: null, unhealthy: 0 },
    });

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
