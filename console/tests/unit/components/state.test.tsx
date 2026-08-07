import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { EmptyState, ErrorState } from '@/components/state';

/**
 * The highest-leverage components in the library.
 *
 * A fresh deployment that looks broken is indistinguishable from one that is,
 * and eight empty tables is what that looks like. So an empty state requires
 * all four of its parts — icon, heading, a sentence saying what would be here
 * and how to get it, and an action — and the requirement is enforced by
 * refusing to render rather than by a note in a document.
 */

describe('EmptyState', () => {
  it('renders its four parts', () => {
    render(
      <EmptyState
        heading="No resources yet"
        body="Connect an infrastructure source and the estate populates itself within a minute."
        action={{ label: 'Connect Proxmox', onSelect: vi.fn() }}
      />,
    );

    expect(
      screen.getByRole('heading', { name: 'No resources yet' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/populates itself/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Connect Proxmox' })).toBeInTheDocument();
  });

  it('refuses to render an action with nothing written on it', () => {
    // The type already rules out a missing action. What it cannot rule out is
    // an action whose label came from an empty string somewhere upstream, which
    // renders as a blank button and is the same dead end.
    expect(() =>
      render(
        <EmptyState
          heading="No resources yet"
          body="Connect an infrastructure source."
          action={{ label: '  ', onSelect: vi.fn() }}
        />,
      ),
    ).toThrow(/action/i);
  });

  it('refuses to render without a sentence saying what would be here', () => {
    expect(() =>
      render(
        <EmptyState
          heading="No resources yet"
          body=""
          action={{ label: 'Go', onSelect: vi.fn() }}
        />,
      ),
    ).toThrow(/body/i);
  });

  it('runs the action from the keyboard', async () => {
    const chosen = vi.fn();
    render(
      <EmptyState
        heading="No resources yet"
        body="Connect an infrastructure source."
        action={{ label: 'Connect Proxmox', onSelect: chosen }}
      />,
    );

    await userEvent.tab();
    await userEvent.keyboard('{Enter}');
    expect(chosen).toHaveBeenCalledOnce();
  });
});

describe('ErrorState', () => {
  it('names the dependency that failed', () => {
    render(
      <ErrorState
        dependency="prometheus.example.invalid"
        detail="refused the connection"
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText('prometheus.example.invalid')).toBeInTheDocument();
  });

  it('says the rest of the page is unaffected, so the reader does not abandon it', () => {
    render(
      <ErrorState
        dependency="prometheus.example.invalid"
        detail="refused the connection"
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText(/rest of this page is unaffected/i)).toBeInTheDocument();
  });

  it('retries this panel only', async () => {
    const retried = vi.fn();
    render(
      <ErrorState
        dependency="prometheus.example.invalid"
        detail="refused the connection"
        onRetry={retried}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /retry this panel/i }));
    expect(retried).toHaveBeenCalledOnce();
  });

  it('is announced, because a panel that failed silently is a panel nobody notices', () => {
    render(
      <ErrorState
        dependency="prometheus.example.invalid"
        detail="refused the connection"
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('sets the dependency in monospace, because it is a name to be compared', () => {
    render(
      <ErrorState
        dependency="prometheus.example.invalid"
        detail="refused the connection"
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText('prometheus.example.invalid').className).toContain(
      'font-mono',
    );
  });
});
