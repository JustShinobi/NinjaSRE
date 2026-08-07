import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Card, StatTile } from '@/components/surface';
import { ServerIcon } from '@/design/icons';

import { only } from '../support/dom';
import { geometryClasses } from '../support/geometry';

describe('Card', () => {
  it('names itself, so a panel error can say which panel failed', () => {
    render(
      <Card title="Attention">
        <p>Three things need a person.</p>
      </Card>,
    );
    expect(screen.getByRole('region', { name: 'Attention' })).toBeInTheDocument();
  });

  it('declares an empty state, a loading state and an error state', () => {
    const { rerender } = render(<Card title="Estate" state="loading" />);
    expect(screen.getByRole('status')).toHaveTextContent(/loading/i);

    rerender(<Card title="Estate" state="empty" emptyMessage="No resources yet." />);
    expect(screen.getByText('No resources yet.')).toBeInTheDocument();

    rerender(<Card title="Estate" state="error" errorMessage="Prometheus refused." />);
    expect(screen.getByRole('alert')).toHaveTextContent('Prometheus refused.');
  });

  it('reserves the same box whatever it is showing', () => {
    const boxes = (['ready', 'loading', 'empty', 'error'] as const).map((state) => {
      const { container, unmount } = render(
        <Card title="Estate" state={state} emptyMessage="none" errorMessage="down">
          <p>content</p>
        </Card>,
      );
      const classes = geometryClasses(only(container, 'section'));
      unmount();
      return classes;
    });
    for (const box of boxes) {
      expect(box).toEqual(boxes[0]);
    }
  });
});

describe('StatTile', () => {
  it('refuses to render a figure with no context line', () => {
    // The rule from the design document: a tile with no drill-down may not be
    // rendered, and the context line is what carries it. A component that
    // shipped without one would be a number nobody can act on.
    expect(() =>
      render(<StatTile label="Healthy" value="85" context="" icon={<ServerIcon />} />),
    ).toThrow(/context/i);
  });

  it('renders the label, the figure and the context together', () => {
    render(
      <StatTile
        label="Resources watched"
        value="92"
        context="2 nodes · 82 CT · 2 VM"
        icon={<ServerIcon />}
      />,
    );

    expect(screen.getByText('Resources watched')).toBeInTheDocument();
    expect(screen.getByText('92')).toBeInTheDocument();
    expect(screen.getByText('2 nodes · 82 CT · 2 VM')).toBeInTheDocument();
  });

  it('reserves the figure box while it is loading, so nothing jumps', () => {
    const { container: loading, unmount } = render(
      <StatTile
        label="Healthy"
        value="85"
        context="↓ 4 since yesterday"
        state="loading"
      />,
    );
    const skeleton = geometryClasses(only(loading, '[data-testid="stat-value"]'));
    unmount();

    const { container: ready } = render(
      <StatTile label="Healthy" value="85" context="↓ 4 since yesterday" />,
    );
    expect(geometryClasses(only(ready, '[data-testid="stat-value"]'))).toEqual(
      skeleton,
    );
  });

  it('sets numbers in tabular figures so a column of them lines up', () => {
    const { container } = render(
      <StatTile label="Healthy" value="85" context="steady" />,
    );
    expect(only(container, '[data-testid="stat-value"]').className).toContain(
      'tabular-nums',
    );
  });
});
