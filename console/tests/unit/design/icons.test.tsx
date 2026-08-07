import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import * as icons from '@/design/icons';
import { ICON_NAMES } from '@/design/icons';

import { only } from '../support/dom';

/**
 * One set, drawn here, fetched from nowhere.
 *
 * The two claims that matter are about what an icon is *not*. It is not a
 * network request — no font, no sprite, no CDN — which is why first paint
 * cannot be blocked on loading the set, and why the network audit has nothing
 * to catch. And it is not a carrier of meaning on its own: every icon is
 * hidden from assistive technology unless a caller explicitly names it.
 */

type IconComponent = (props: icons.IconProps) => ReactNode;

/** Every icon, as a component, by name. */
function everyIcon(): readonly (readonly [string, IconComponent])[] {
  return ICON_NAMES.map((name) => {
    const component: unknown = Reflect.get(icons, name);
    if (typeof component !== 'function') {
      throw new Error(`${name} is declared and not exported`);
    }
    return [name, component as IconComponent] as const;
  });
}

describe('the icon set', () => {
  it('draws every declared icon at every declared size', () => {
    for (const [name, Icon] of everyIcon()) {
      for (const size of ['inline', 'nav', 'head', 'empty'] as const) {
        const { container, unmount } = render(<Icon size={size} />);
        const svg = only(container, 'svg');

        expect(svg.getAttribute('class'), `${name} at ${size}`).toContain(
          `icon-${size}`,
        );
        expect(
          svg.querySelectorAll('path, circle, rect, ellipse').length,
          name,
        ).toBeGreaterThan(0);
        unmount();
      }
    }
  });

  it('is decorative by default, so it never says the label twice', () => {
    for (const [name, Icon] of everyIcon()) {
      const { container, unmount } = render(<Icon />);
      expect(only(container, 'svg').getAttribute('aria-hidden'), name).toBe('true');
      unmount();
    }
  });

  it('takes a name when a caller says the shape is the whole message', () => {
    const { container } = render(<icons.CheckIcon title="Verified" />);
    const svg = only(container, 'svg');

    expect(svg.getAttribute('role')).toBe('img');
    expect(svg.getAttribute('aria-label')).toBe('Verified');
    expect(svg.hasAttribute('aria-hidden')).toBe(false);
  });

  it('inherits its colour rather than carrying one', () => {
    for (const [name, Icon] of everyIcon()) {
      const { container, unmount } = render(<Icon />);
      const svg = only(container, 'svg');

      expect(svg.getAttribute('stroke'), name).toBe('currentColor');
      expect(svg.getAttribute('fill'), name).toBe('none');
      unmount();
    }
  });

  it('fetches nothing, so first paint cannot be blocked on the set', () => {
    for (const [name, Icon] of everyIcon()) {
      const { container, unmount } = render(<Icon />);
      const markup = container.innerHTML;

      expect(markup, name).not.toContain('<image');
      expect(markup, name).not.toContain('url(');
      expect(markup, name).not.toContain('xlink:href');
      unmount();
    }
  });
});
