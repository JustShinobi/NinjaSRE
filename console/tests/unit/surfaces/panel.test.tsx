import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Panel } from '@/surfaces/panel';

const refresh = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh }),
}));

/**
 * A dashboard is six independent questions, and one unanswerable question must
 * not blank the other five.
 *
 * The assertion is deliberately made against a *rendered* failure rather than a
 * rejected read: a read that rejects is caught where it is made and becomes a
 * state, which is the easy half. The half that takes a page down is a component
 * that throws while React is drawing it, and the only thing that contains that
 * is a boundary around each panel rather than one around the page.
 */

const EMPTY = {
  heading: 'No resources yet',
  body: 'Connect an infrastructure source and the estate populates itself.',
  actionLabel: 'Connect a source',
  href: '/configuration',
} as const;

const LABELS = {
  loading: 'Loading the estate…',
  errorHeading: 'Could not reach the estate',
  errorDetail: 'refused the request. The rest of this page is unaffected.',
  retry: 'Retry this panel',
} as const;

function Exploding(): ReactNode {
  throw new Error('the metrics source is unreachable');
}

let noise: { mockRestore: () => void };

beforeEach(() => {
  refresh.mockClear();
  // React reports a caught render error on the console. The report is correct
  // and this file is about what happens *after* it.
  noise = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  noise.mockRestore();
});

describe('a panel that fails', () => {
  function renderPair(): void {
    render(
      <>
        <Panel title="Metrics" state="ready" empty={EMPTY} labels={LABELS}>
          <Exploding />
        </Panel>
        <Panel title="Incidents" state="ready" empty={EMPTY} labels={LABELS}>
          <p>Three incidents are open.</p>
        </Panel>
      </>,
    );
  }

  it('shows its own error and its own retry while its sibling still renders', () => {
    renderPair();

    const failed = screen.getByRole('alert');
    expect(failed).toHaveTextContent(LABELS.errorHeading);
    expect(screen.getByRole('button', { name: LABELS.retry })).toBeInTheDocument();

    // The whole point: the other panel is untouched.
    expect(screen.getByText('Three incidents are open.')).toBeInTheDocument();
  });

  it('marks the failed panel and only the failed panel', () => {
    renderPair();

    const states = screen
      .getAllByTestId('panel')
      .map((element) => element.getAttribute('data-state'));
    expect(states).toEqual(['error', 'ready']);
  });

  it('retries that panel alone rather than reloading the document', async () => {
    renderPair();

    await userEvent.click(screen.getByRole('button', { name: LABELS.retry }));

    expect(refresh).toHaveBeenCalledTimes(1);
  });
});

describe('a panel that is handed a state', () => {
  function renderState(state: 'loading' | 'empty' | 'error'): void {
    render(
      <Panel
        title="Estate"
        state={state}
        empty={EMPTY}
        labels={LABELS}
        dependency="estate.inventory"
      >
        <p>Ninety-two resources.</p>
      </Panel>,
    );
  }

  it('reserves the layout while it loads rather than collapsing', () => {
    renderState('loading');

    expect(screen.getByRole('status')).toHaveAccessibleName(LABELS.loading);
    expect(screen.queryByText('Ninety-two resources.')).toBeNull();
  });

  it('says what would be here and how to get it', () => {
    renderState('empty');

    expect(screen.getByRole('heading', { name: EMPTY.heading })).toBeInTheDocument();
    expect(screen.getByText(EMPTY.body)).toBeInTheDocument();
    expect(screen.getByTestId('way-back')).toHaveAttribute('href', EMPTY.href);
  });

  it('names the dependency that failed', () => {
    renderState('error');

    expect(screen.getByRole('alert')).toHaveTextContent('estate.inventory');
  });
});
