import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  Button,
  BUTTON_VARIANTS,
  IconButton,
  Link,
  CONTROL_STATES,
} from '@/components/action';
import { TrashIcon } from '@/design/icons';

import { only } from '../support/dom';
import { geometryClasses } from '../support/geometry';

/**
 * The three ways a console asks somebody to do something.
 *
 * Two claims here are load-bearing rather than cosmetic. A destructive action
 * has to be distinguishable from an accented one *by more than its colour*,
 * because the operator about to delete a recovery point at three in the morning
 * may be the one in twelve who cannot separate the two hues. And an icon-only
 * control has to carry a name, because to a screen reader an unnamed one is a
 * button called "button".
 */

describe('Button', () => {
  it('renders every declared variant', () => {
    for (const variant of BUTTON_VARIANTS) {
      const { unmount } = render(<Button variant={variant}>Retry</Button>);
      // A regex, not an equality: the destructive variant deliberately adds to
      // its own accessible name, and that addition is the point of it.
      expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument();
      unmount();
    }
  });

  it('changes no geometry between states, so nothing moves under the pointer', () => {
    const geometries = CONTROL_STATES.map((state) => {
      const { container, unmount } = render(<Button state={state}>Retry</Button>);
      const classes = geometryClasses(only(container, 'button'));
      unmount();
      return classes;
    });

    for (const classes of geometries) {
      expect(classes).toEqual(geometries[0]);
    }
  });

  it('marks a destructive action in words as well as in colour', () => {
    render(<Button variant="destructive">Delete snapshot</Button>);
    const button = screen.getByRole('button', { name: /Delete snapshot/ });

    expect(button).toHaveAttribute('data-variant', 'destructive');
    // The accessible name carries it, so it survives a viewer who cannot see
    // that the button is red.
    expect(button).toHaveAccessibleName(/destructive/i);
  });

  it('is not the same colour as the accented variant', () => {
    const { container: accent, unmount } = render(
      <Button variant="primary">Go</Button>,
    );
    const primaryClasses = only(accent, 'button').className;
    unmount();

    const { container: danger } = render(<Button variant="destructive">Go</Button>);
    expect(only(danger, 'button').className).not.toBe(primaryClasses);
  });

  it('reports that it is working without losing its accessible name', () => {
    render(<Button state="loading">Save</Button>);
    const button = screen.getByRole('button', { name: /Save/ });

    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
  });

  it('is operable from the keyboard alone', async () => {
    const pressed = vi.fn();
    render(<Button onClick={pressed}>Approve</Button>);

    await userEvent.tab();
    expect(screen.getByRole('button')).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    expect(pressed).toHaveBeenCalledOnce();
  });

  it('refuses to act while disabled', async () => {
    const pressed = vi.fn();
    render(
      <Button state="disabled" onClick={pressed}>
        Approve
      </Button>,
    );

    await userEvent.click(screen.getByRole('button'));
    expect(pressed).not.toHaveBeenCalled();
  });
});

describe('IconButton', () => {
  it('carries an accessible name even though it shows no words', () => {
    render(<IconButton label="Delete this backup" icon={<TrashIcon />} />);
    expect(
      screen.getByRole('button', { name: 'Delete this backup' }),
    ).toBeInTheDocument();
  });

  it('hides the icon from assistive technology, so the name is not said twice', () => {
    const { container } = render(<IconButton label="Delete" icon={<TrashIcon />} />);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('changes no geometry between states', () => {
    const geometries = CONTROL_STATES.map((state) => {
      const { container, unmount } = render(
        <IconButton label="Delete" icon={<TrashIcon />} state={state} />,
      );
      const classes = geometryClasses(only(container, 'button'));
      unmount();
      return classes;
    });
    for (const classes of geometries) {
      expect(classes).toEqual(geometries[0]);
    }
  });
});

describe('Link', () => {
  it('is a link, not a button dressed as one', () => {
    render(<Link href="/runs">Investigations</Link>);
    expect(screen.getByRole('link', { name: 'Investigations' })).toHaveAttribute(
      'href',
      '/runs',
    );
  });

  it('says out loud when it leaves the deployment', () => {
    render(
      <Link href="/docs" external>
        Documentation
      </Link>,
    );
    const link = screen.getByRole('link');

    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'));
    expect(link).toHaveAccessibleName(/opens in a new tab/i);
  });
});
