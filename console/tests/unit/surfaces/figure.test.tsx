import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Figure } from '@/surfaces/figure';

/**
 * A row of figures has one bottom edge.
 *
 * The grid stretches its cells already; the tile inside each one was
 * content-height, so the figure carrying a four-line caption — "13 open
 * findings behind them; 0 of 0 detectors are switched on to raise one of them
 * into an incident" — grew sixty pixels past the three beside it and stepped
 * the row.
 *
 * The caption is not clamped to straighten it. That line is what makes the
 * number actionable, and hiding it to tidy an edge trades the point of the
 * component for the look of it.
 */
describe('a figure in a row of figures', () => {
  it('fills the height of the cell the grid gives it', () => {
    render(
      <Figure
        label="Degraded and unhealthy"
        value="13"
        context="13 open findings behind them; 0 of 0 detectors are switched on to raise one of them into an incident"
        href="/resources"
        drillLabel="Open resources"
      />,
    );

    const figure = screen.getByTestId('figure');
    expect(figure.className).toContain('h-full');
    expect(figure.firstElementChild?.className).toContain('h-full');
  });

  it('still refuses a number a reader cannot go and check', () => {
    expect(() =>
      render(
        <Figure
          label="Degraded"
          value="13"
          context="13 open findings behind them"
          href="  "
          drillLabel="Open resources"
        />,
      ),
    ).toThrow(/drill-down/i);
  });
});
