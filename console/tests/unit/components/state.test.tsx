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
        heading="Could not reach this source"
        dependency="prometheus.example.invalid"
        detail="refused the connection. The rest of this page is unaffected."
        retryLabel="Retry this panel"
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText('prometheus.example.invalid')).toBeInTheDocument();
  });

  it('says the rest of the page is unaffected, so the reader does not abandon it', () => {
    render(
      <ErrorState
        heading="Could not reach this source"
        dependency="prometheus.example.invalid"
        detail="refused the connection. The rest of this page is unaffected."
        retryLabel="Retry this panel"
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText(/rest of this page is unaffected/i)).toBeInTheDocument();
  });

  it('retries this panel only', async () => {
    const retried = vi.fn();
    render(
      <ErrorState
        heading="Could not reach this source"
        dependency="prometheus.example.invalid"
        detail="refused the connection. The rest of this page is unaffected."
        retryLabel="Retry this panel"
        onRetry={retried}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /retry this panel/i }));
    expect(retried).toHaveBeenCalledOnce();
  });

  it('is announced, because a panel that failed silently is a panel nobody notices', () => {
    render(
      <ErrorState
        heading="Could not reach this source"
        dependency="prometheus.example.invalid"
        detail="refused the connection. The rest of this page is unaffected."
        retryLabel="Retry this panel"
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('sets the dependency in monospace, because it is a name to be compared', () => {
    render(
      <ErrorState
        heading="Could not reach this source"
        dependency="prometheus.example.invalid"
        detail="refused the connection. The rest of this page is unaffected."
        retryLabel="Retry this panel"
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText('prometheus.example.invalid').className).toContain(
      'font-mono',
    );
  });
});

describe('the empty state as one control rather than two', () => {
  /**
   * Three specs report the same defect independently — Incidents, Approvals and
   * Memory each say their call to action appears twice in the accessibility
   * tree. None of them is wrong and none of them can fix it: the duplication is
   * here, and it was well meant. The action rendered as a `<button>` firing a
   * navigation, and the panel added a visually-hidden `<a>` beside it carrying
   * the identical label, so that anything reading edges rather than pressing
   * buttons still had a real link to follow.
   *
   * The result is that a screen reader announces the same action twice, once as
   * a button and once as a link. The fix is not to drop either one: it is to
   * notice that the action was always a navigation — `PanelEmpty.href` says so
   * outright — and let one anchor be both.
   */

  it('renders the action as a link when it has somewhere to go', () => {
    render(
      <EmptyState
        heading="No open incidents"
        body="A detector opens one when what it watches crosses its threshold."
        action={{ label: 'See what is being watched for', href: '/detectors' }}
      />,
    );

    const action = screen.getByRole('link', { name: 'See what is being watched for' });
    expect(action.getAttribute('href')).toBe('/detectors');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('announces that action exactly once', () => {
    render(
      <EmptyState
        heading="No open incidents"
        body="A detector opens one when what it watches crosses its threshold."
        action={{ label: 'See what is being watched for', href: '/detectors' }}
      />,
    );

    expect(screen.getAllByText('See what is being watched for')).toHaveLength(1);
  });

  it('keeps a handler action a button, because it goes nowhere to be linked to', () => {
    const chosen = vi.fn();
    render(
      <EmptyState
        heading="Nothing yet"
        body="Something would be here."
        action={{ label: 'Do the thing', onSelect: chosen }}
      />,
    );

    expect(screen.getByRole('button', { name: 'Do the thing' })).toBeInTheDocument();
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('still refuses an action with nothing written on it', () => {
    expect(() =>
      render(
        <EmptyState
          heading="No open incidents"
          body="Something would be here."
          action={{ label: '   ', href: '/detectors' }}
        />,
      ),
    ).toThrow(/no action/i);
  });
});

/**
 * A long explanation is left-aligned, even inside a centred well.
 *
 * Knowledge's empty state runs to four lines and names the two ways a document
 * can reach the corpus. Centred, every one of those lines begins at a different
 * x and the eye has to hunt for the start of each — the cost is small for one
 * line and real for four. The well stays centred; the sentence inside it does
 * not.
 */
it('left-aligns the body while keeping the well centred', () => {
  render(
    <EmptyState
      heading="Nothing has been ingested"
      body="Nothing here yet, and this console has no upload control to offer. A document reaches this corpus when the sync brings it in, or when an investigation proposes one and a reviewer approves it."
      action={{ label: 'Review what has been proposed', href: '/decisions' }}
    />,
  );

  const body = screen.getByText(/Nothing here yet/);
  expect(body.className).toContain('text-left');
  expect(body.className).toContain('max-w-prose');
});
