import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { RuleSimulator, SIMULATE_ENDPOINT } from '@/surfaces/simulation';

/**
 * Nothing that decides behaviour is saved without its effect having been seen.
 *
 * The same guarantee the configuration editor's preview carries, and the reason
 * it is a *lock* rather than a suggestion: a rule is the thing that decides
 * whether an alert becomes an investigation, and "I meant to check" is not a
 * property anybody can rely on at three in the morning.
 *
 * The bypass attempt is the second half and the more important one. An operator
 * who simulates, then edits the payload, has not seen the effect of what they
 * are now about to save — so the button locks again.
 */

const LABELS = {
  source: 'Receiver',
  payload: 'Payload',
  simulate: 'Simulate',
  simulating: 'Simulating…',
  save: 'Save',
  needsSimulation: 'Simulate this payload before saving, so the effect is seen first.',
  rule: 'Rule',
  team: 'Team',
  action: 'Action:',
  failed: 'The deployment refused the simulation.',
  unreachable: 'The deployment could not be reached.',
  malformed: 'That is not valid JSON.',
};

function answered(body: unknown, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status }))),
  );
}

beforeEach(() => {
  answered({
    rule_id: 'quiet-grafana',
    team: 'team-platform',
    action: 'discard',
    reason: 'noisy',
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function simulator(): void {
  render(<RuleSimulator sources={['alertmanager', 'grafana']} labels={LABELS} />);
}

describe('simulating a rule before saving it', () => {
  it('starts with save locked and says why', () => {
    simulator();

    expect(screen.getByTestId('simulate-save')).toBeDisabled();
    expect(screen.getByTestId('simulate-pending')).toHaveTextContent(
      LABELS.needsSimulation,
    );
  });

  it('shows the rule, the team and the action the deployment answered', async () => {
    simulator();

    await userEvent.type(screen.getByTestId('simulate-payload'), '{{"a": 1}');
    await userEvent.click(screen.getByTestId('simulate'));

    expect(screen.getByTestId('simulate-rule')).toHaveTextContent('quiet-grafana');
    expect(screen.getByTestId('simulate-team')).toHaveTextContent('team-platform');
    expect(screen.getByTestId('simulate-action')).toHaveTextContent('discard');
    expect(screen.getByTestId('simulate-reason')).toHaveTextContent('noisy');
  });

  it('asks the deployment rather than working the answer out here', async () => {
    const calls = vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ rule_id: 'r', team: 't', action: 'investigate' }),
        ),
      ),
    );
    vi.stubGlobal('fetch', calls);
    simulator();

    await userEvent.click(screen.getByTestId('simulate'));

    expect(calls).toHaveBeenCalledWith(SIMULATE_ENDPOINT, expect.anything());
  });

  it('unlocks save once an answer has been seen', async () => {
    simulator();

    await userEvent.click(screen.getByTestId('simulate'));

    expect(screen.getByTestId('simulate-save')).toBeEnabled();
  });

  it('locks save again when the payload changes under it', async () => {
    // The bypass attempt: simulate something harmless, then edit, then save.
    simulator();
    await userEvent.click(screen.getByTestId('simulate'));
    expect(screen.getByTestId('simulate-save')).toBeEnabled();

    await userEvent.type(screen.getByTestId('simulate-payload'), '{{"changed": true}');

    expect(screen.getByTestId('simulate-save')).toBeDisabled();
    expect(screen.getByTestId('simulate-pending')).toBeInTheDocument();
  });

  it('locks save again when the receiver changes under it', async () => {
    simulator();
    await userEvent.click(screen.getByTestId('simulate'));

    await userEvent.selectOptions(screen.getByTestId('simulate-source'), 'grafana');

    expect(screen.getByTestId('simulate-save')).toBeDisabled();
  });

  it('says what is wrong with a payload that is not JSON, and asks nothing', async () => {
    const calls = vi.fn();
    vi.stubGlobal('fetch', calls as unknown);
    simulator();

    await userEvent.type(screen.getByTestId('simulate-payload'), 'not json');
    await userEvent.click(screen.getByTestId('simulate'));

    expect(screen.getByTestId('simulate-failure')).toHaveTextContent(LABELS.malformed);
    expect(calls).not.toHaveBeenCalled();
    expect(screen.getByTestId('simulate-save')).toBeDisabled();
  });

  it('leaves save locked when the deployment refuses the simulation', async () => {
    answered({}, 400);
    simulator();

    await userEvent.click(screen.getByTestId('simulate'));

    expect(screen.getByTestId('simulate-failure')).toHaveTextContent(LABELS.failed);
    expect(screen.getByTestId('simulate-save')).toBeDisabled();
  });

  it('leaves save locked when the deployment cannot be reached', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('no route'))),
    );
    simulator();

    await userEvent.click(screen.getByTestId('simulate'));

    expect(screen.getByTestId('simulate-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
    expect(screen.getByTestId('simulate-save')).toBeDisabled();
  });
});
