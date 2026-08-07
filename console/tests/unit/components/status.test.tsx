import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Badge, StatusDot } from '@/components/status';
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
