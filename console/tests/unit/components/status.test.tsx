import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  AccountStateChip,
  Badge,
  CheckChip,
  PrincipalKindChip,
  StatusDot,
  TokenGroupStateChip,
} from '@/components/status';
import { RESOURCE_STATUSES, RUN_STATUSES, statusPresentation } from '@/design/status';

/**
 * Status, shown twice: once in colour and once in something else.
 *
 * These two components are where the "never colour alone" requirement is
 * actually kept, so the tests are about absence as much as presence — a badge
 * with no text and a dot with no shape both fail here, because both are a
 * status that some viewers do not have.
 */

const EVERY_STATUS = [...RUN_STATUSES, ...RESOURCE_STATUSES, 'invented-by-a-provider'];

describe('Badge', () => {
  it('always says the status in words', () => {
    for (const status of EVERY_STATUS) {
      const { unmount } = render(<Badge status={status} />);
      expect(screen.getByText(statusPresentation(status).label)).toBeInTheDocument();
      unmount();
    }
  });

  it('always carries a shape as well as a colour', () => {
    for (const status of EVERY_STATUS) {
      const { container, unmount } = render(<Badge status={status} />);
      const shape = container.querySelector('[data-shape]');
      expect(shape, status).not.toBeNull();
      expect(shape).toHaveAttribute('data-shape', statusPresentation(status).shape);
      unmount();
    }
  });

  it('gives a status nobody declared its raw text and the neutral role', () => {
    const { container } = render(<Badge status="quiesced" />);
    expect(screen.getByText('quiesced')).toBeInTheDocument();
    expect(container.querySelector('[data-role]')).toHaveAttribute(
      'data-role',
      'neutral',
    );
  });

  it('says nothing was reported rather than rendering an empty chip', () => {
    render(<Badge status="" />);
    expect(screen.getByText('unreported')).toBeInTheDocument();
  });
});

describe('StatusDot', () => {
  it('is never announced on its own, because it is never on its own', () => {
    render(<StatusDot status="healthy" />);
    // Decorative: the label beside it is what a screen reader says. A dot that
    // announced itself would say "healthy" twice on every row.
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('carries an accessible name when a caller says it stands alone', () => {
    render(<StatusDot status="degraded" standalone />);
    expect(screen.getByRole('img', { name: /degraded/ })).toBeInTheDocument();
  });

  it('draws a different shape for each of the two neutral states', () => {
    const { container: unknown, unmount } = render(<StatusDot status="unknown" />);
    const first = unknown.firstElementChild?.getAttribute('data-shape');
    unmount();
    const { container: stale } = render(<StatusDot status="stale" />);
    expect(stale.firstElementChild?.getAttribute('data-shape')).not.toBe(first);
  });
});

describe('CheckChip', () => {
  // Every state the preflight actually reports, each with its own role and
  // shape — never the five-word credential vocabulary, which is a different
  // claim about a different kind of thing.
  const CASES: readonly {
    readonly status: 'passed' | 'degraded' | 'failed' | 'skipped';
    readonly role: string;
    readonly shape: string;
  }[] = [
    { status: 'passed', role: 'success', shape: 'filled-circle' },
    { status: 'degraded', role: 'warning', shape: 'triangle' },
    { status: 'failed', role: 'danger', shape: 'square' },
    { status: 'skipped', role: 'neutral', shape: 'dash' },
  ];

  it.each(CASES)(
    'draws $status with the $role role and the $shape shape',
    ({ status, role, shape }) => {
      const { container } = render(<CheckChip name="Tool calling" status={status} />);
      const chip = container.firstElementChild;
      expect(chip).toHaveAttribute('data-role', role);
      expect(chip).toHaveAttribute('data-check-status', status);
      expect(chip?.querySelector('[data-shape]')).toHaveAttribute('data-shape', shape);
    },
  );

  it('names the check, never a canonical credential word', () => {
    render(<CheckChip name="Structured output" status="failed" />);
    expect(screen.getByText('Structured output')).toBeInTheDocument();
  });
});

describe('PrincipalKindChip', () => {
  it('names a service account by what it is, never the transport word', () => {
    render(<PrincipalKindChip locale="en" kind="service_account" />);
    expect(screen.getByText('Service account')).toBeInTheDocument();
    expect(screen.queryByText('SERVICE_ACCOUNT')).toBeNull();
    expect(screen.queryByText('service_account')).toBeNull();
  });

  it('names a person by what they are, never the raw record kind', () => {
    render(<PrincipalKindChip locale="en" kind="user" />);
    expect(screen.getByText('Person')).toBeInTheDocument();
    expect(screen.queryByText('user')).toBeNull();
  });

  it('shows a kind this catalogue has never heard of rather than hiding it', () => {
    render(<PrincipalKindChip locale="en" kind="robot" />);
    expect(screen.getByText('robot')).toBeInTheDocument();
  });
});

describe('AccountStateChip', () => {
  it('says a live account is active, never the health word healthy', () => {
    render(<AccountStateChip locale="en" active />);
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.queryByText('healthy')).toBeNull();
    expect(screen.queryByText(/HEALTHY/i)).toBeNull();
  });

  it('says a disabled account is suspended, never disabled', () => {
    render(<AccountStateChip locale="en" active={false} />);
    expect(screen.getByText('Suspended')).toBeInTheDocument();
    expect(screen.queryByText('disabled')).toBeNull();
  });
});

describe('TokenGroupStateChip', () => {
  it('says a group with a recorded last use is in use, never healthy', () => {
    render(<TokenGroupStateChip locale="en" everUsed />);
    expect(screen.getByText('In use')).toBeInTheDocument();
    expect(screen.queryByText(/HEALTHY/i)).toBeNull();
  });

  it('says a group with no recorded use was never used', () => {
    render(<TokenGroupStateChip locale="en" everUsed={false} />);
    expect(screen.getByText('Never used')).toBeInTheDocument();
  });
});
