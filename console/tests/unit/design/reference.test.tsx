import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { Reference } from '@/design/reference';

/**
 * Reference content, out of the operator's way until it is asked for.
 *
 * A webhook payload, "not covered, and why", a conceptual explanation — none
 * of it belongs between an operator and the form they opened the screen for.
 * This is the one shape that content takes: a title and a one-line summary,
 * both visible with nothing expanded, and the rest behind one control.
 */

describe('a reference block', () => {
  it('shows the title and the summary with nothing expanded', () => {
    render(
      <Reference title="Not covered, and why" summary="9 vendors, for two reasons.">
        <p>The long version.</p>
      </Reference>,
    );

    expect(screen.getByText('Not covered, and why')).toBeInTheDocument();
    expect(screen.getByText('9 vendors, for two reasons.')).toBeInTheDocument();
    expect(screen.queryByText('The long version.')).not.toBeInTheDocument();
  });

  it('is collapsed by default, and says so', () => {
    render(
      <Reference title="Payload" summary="What the webhook sends.">
        <p>Body</p>
      </Reference>,
    );

    expect(screen.getByTestId('reference')).toHaveAttribute('data-expanded', 'false');
  });

  it('reveals the body once expanded, and only then', async () => {
    render(
      <Reference title="Payload" summary="What the webhook sends.">
        <p>The full schema.</p>
      </Reference>,
    );

    await userEvent.click(screen.getByRole('button', { expanded: false }));

    expect(screen.getByText('The full schema.')).toBeInTheDocument();
    expect(screen.getByTestId('reference')).toHaveAttribute('data-expanded', 'true');
  });

  it('collapses again on a second press', async () => {
    render(
      <Reference title="Payload" summary="What the webhook sends.">
        <p>The full schema.</p>
      </Reference>,
    );

    const toggle = screen.getByRole('button');
    await userEvent.click(toggle);
    await userEvent.click(toggle);

    expect(screen.queryByText('The full schema.')).not.toBeInTheDocument();
  });
});
