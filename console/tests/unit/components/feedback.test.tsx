import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ProgressBar, Skeleton, Spinner, Toast, Tooltip } from '@/components/feedback';

import { only } from '../support/dom';
import { geometryClasses } from '../support/geometry';

/**
 * The components that say "wait", "here is how far", and "that happened".
 *
 * Two properties are asserted rather than assumed. Motion is removed under
 * reduced motion rather than shortened, which is checked by looking at what the
 * component asks for rather than at what a browser does with it. And a skeleton
 * reserves the exact box the real content will take, because a skeleton that
 * changes the layout when the data arrives is the shift it existed to prevent.
 */

describe('Spinner', () => {
  it('says what it is waiting for, rather than spinning silently', () => {
    render(<Spinner label="Loading the estate" />);
    expect(
      screen.getByRole('status', { name: 'Loading the estate' }),
    ).toBeInTheDocument();
  });

  it('animates through a class the reduced-motion rule can reach', () => {
    const { container } = render(<Spinner label="Loading" />);
    const animated = container.querySelector('[data-animated]');

    expect(animated).not.toBeNull();
    // `animate-spin`, not a duration written into the component: the global
    // reduced-motion rule sets every animation to `--dur-none`, and a component
    // that carried its own inline duration would escape it.
    expect(animated?.className).toContain('animate-spin');
    expect(animated?.className).not.toMatch(/duration-\d/);
  });
});

describe('Skeleton', () => {
  it('reserves exactly the box the real content will take', () => {
    const { container: placeholder, unmount } = render(<Skeleton width="title" />);
    const reserved = geometryClasses(only(placeholder, 'span'));
    unmount();

    const { container: real } = render(<Skeleton width="title" loaded />);
    expect(geometryClasses(only(real, 'span'))).toEqual(reserved);
  });

  it('is invisible to a screen reader, which has nothing to read yet', () => {
    const { container } = render(<Skeleton width="title" />);
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('ProgressBar', () => {
  it('shows the number beside the bar, because a bar alone is not a reading', () => {
    render(<ProgressBar label="local-lvm" value={94.96} />);

    expect(screen.getByText('94.96%')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'local-lvm' })).toHaveAttribute(
      'aria-valuenow',
      '94.96',
    );
  });

  it('changes role as it crosses each threshold, and says which', () => {
    for (const [value, role] of [
      [12, 'accent'],
      [82, 'warning'],
      [96, 'danger'],
    ] as const) {
      const { container, unmount } = render(
        <ProgressBar label="local-lvm" value={value} />,
      );
      expect(container.querySelector('[data-role]')).toHaveAttribute('data-role', role);
      unmount();
    }
  });

  it('is visible at zero, so an empty bar is still a bar', () => {
    const { container } = render(<ProgressBar label="local-lvm" value={0} />);
    expect(only(container, '[data-testid="meter"]').className).toContain('edge');
  });
});

describe('Toast', () => {
  it('is announced without stealing focus', () => {
    render(<Toast role="success" message="Reclaimed 41 GiB." onDismiss={vi.fn()} />);
    const toast = screen.getByRole('status');

    expect(toast).toHaveTextContent('Reclaimed 41 GiB.');
    expect(toast).toHaveAttribute('aria-live', 'polite');
  });

  it('announces a failure assertively, because a failure that waits is missed', () => {
    render(<Toast role="danger" message="The reclaim failed." onDismiss={vi.fn()} />);
    expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'assertive');
  });

  it('can be dismissed, and says where the outcome is recorded', () => {
    render(
      <Toast
        role="success"
        message="Reclaimed 41 GiB."
        recordedAt={{ href: '/audit', label: 'the audit trail' }}
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument();
    // Never the only record: a toast a viewer missed must still be findable.
    expect(screen.getByRole('link', { name: /the audit trail/ })).toHaveAttribute(
      'href',
      '/audit',
    );
  });
});

describe('Tooltip', () => {
  it('describes the control it belongs to rather than replacing its name', async () => {
    render(
      <Tooltip text="The last successful sweep">
        <button type="button">Last swept</button>
      </Tooltip>,
    );

    const control = screen.getByRole('button', { name: 'Last swept' });
    await userEvent.hover(control);

    expect(control).toHaveAccessibleDescription('The last successful sweep');
  });

  it('appears on focus as well as on hover, so a keyboard reaches it', async () => {
    render(
      <Tooltip text="The last successful sweep">
        <button type="button">Last swept</button>
      </Tooltip>,
    );

    await userEvent.tab();
    expect(screen.getByRole('tooltip')).toHaveTextContent('The last successful sweep');
  });

  it('goes away on escape, without taking the page with it', async () => {
    render(
      <Tooltip text="The last successful sweep">
        <button type="button">Last swept</button>
      </Tooltip>,
    );

    await userEvent.tab();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
});
