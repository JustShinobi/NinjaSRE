import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RISK_CLASSES, RiskLadder } from '@/surfaces/risk-ladder';

/**
 * The escalation is drawn, because drawing it is the screen's whole job.
 *
 * "What would happen, by class of action" listed trivial, low, moderate, high
 * and critical at one size, one weight and one chip colour, in lowercase
 * monospace. A reader had to get through five near-identical entries to learn
 * the one thing the screen exists to say — that these are rungs of a ladder,
 * and that the deployment's posture sits somewhere along them.
 *
 * Filled rungs rather than colour alone: roughly one man in twelve cannot
 * separate the hues this palette uses for success and danger, and a ladder
 * carried by hue is a ladder those readers do not have.
 */
describe('the risk ladder', () => {
  it('fills one rung per step up to the class it is drawing', () => {
    render(<RiskLadder riskClass="moderate" label="Moderate" />);

    const rungs = screen.getAllByTestId('risk-rung');
    expect(rungs).toHaveLength(RISK_CLASSES.length);
    expect(
      rungs.filter((rung) => rung.getAttribute('data-filled') === 'true'),
    ).toHaveLength(3);
  });

  it('fills every rung at the top of the scale and one at the bottom', () => {
    const { unmount } = render(<RiskLadder riskClass="critical" label="Critical" />);
    expect(
      screen
        .getAllByTestId('risk-rung')
        .filter((rung) => rung.getAttribute('data-filled') === 'true'),
    ).toHaveLength(5);
    unmount();

    render(<RiskLadder riskClass="trivial" label="Trivial" />);
    expect(
      screen
        .getAllByTestId('risk-rung')
        .filter((rung) => rung.getAttribute('data-filled') === 'true'),
    ).toHaveLength(1);
  });

  it('names the class in words, never in its own spelling', () => {
    render(<RiskLadder riskClass="moderate" label="Moderate" />);
    expect(screen.getByTestId('risk-class')).toHaveTextContent('Moderate');
    expect(screen.getByTestId('risk-class').className).not.toContain('font-mono');
  });

  it('carries a class the scale has never met without pretending to place it', () => {
    render(<RiskLadder riskClass="apocalyptic" label="Apocalyptic" />);

    // No rungs: an unplaceable class drawn at the bottom of the ladder would be
    // a guess rendered as a measurement.
    expect(screen.queryAllByTestId('risk-rung')).toHaveLength(0);
    expect(screen.getByTestId('risk-class')).toHaveTextContent('Apocalyptic');
  });

  it('states the rung it is on for a reader who cannot see the drawing', () => {
    render(<RiskLadder riskClass="high" label="High" />);
    expect(screen.getByTestId('risk-ladder')).toHaveAttribute('aria-label', '4 of 5');
  });
});
