import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import * as icons from '@/design/icons';

/**
 * The icon module's export surface, pinned — independently of `ICON_NAMES`.
 *
 * `icons.test.tsx` proves every icon *behaves* the same way (renders at every
 * size, is decorative by default, inherits its colour, fetches nothing). It
 * never once compares the actual list of exported names against a fixed
 * expectation, so a redesign that quietly renamed or dropped an icon — the
 * one thing FR-022 forbids — would still pass every assertion in that file.
 * This is the test that would have caught it: the list below is written by
 * hand, once, before the redesign, and is not derived from `ICON_NAMES` (a
 * second copy of the same list proves nothing about whether the list is
 * right, only that it agrees with itself).
 *
 * It must read exactly the same — same names, same order, same prop shape —
 * before this feature's icon redesign and after it. The redesign changes
 * what each icon draws; it does not change what a caller imports.
 */

/** Every icon export, written once, in the order `icons.tsx` declares it today. */
const EXPECTED_ICON_NAMES = [
  'CheckIcon',
  'CloseIcon',
  'PlusIcon',
  'MinusIcon',
  'ChevronRightIcon',
  'ChevronLeftIcon',
  'ChevronDownIcon',
  'AlertTriangleIcon',
  'AlertCircleIcon',
  'InfoIcon',
  'ClockIcon',
  'SearchIcon',
  'RefreshIcon',
  'ServerIcon',
  'DatabaseIcon',
  'ActivityIcon',
  'ShieldIcon',
  'LayersIcon',
  'SettingsIcon',
  'BookIcon',
  'ArrowRightIcon',
  'CopyIcon',
  'TrashIcon',
  'InboxIcon',
  'GridIcon',
  'ListIcon',
  'SitemapIcon',
  'UsersIcon',
  'BrainIcon',
  'ClipboardIcon',
  'BellIcon',
  'ContrastIcon',
  'CompassIcon',
  'MenuIcon',
  // Added after the redesign, not renamed from anything: the board draws a
  // stop mark on "Parar automação" and the set had no glyph for stopping.
  'StopIcon',
  'PlayIcon',
] as const;

describe('the icon module export surface', () => {
  it('exports exactly these names, in this order, and no others', () => {
    // `ICON_NAMES` is the module's own manifest — checked against the
    // independent list above rather than used to build it.
    expect([...icons.ICON_NAMES]).toEqual(EXPECTED_ICON_NAMES);

    const actualExports = Object.keys(icons).filter(
      (key) =>
        key !== 'ICON_NAMES' &&
        typeof (icons as Record<string, unknown>)[key] === 'function',
    );
    expect(actualExports.sort()).toEqual([...EXPECTED_ICON_NAMES].sort());
  });

  it('gives every one of those names a callable component export', () => {
    for (const name of EXPECTED_ICON_NAMES) {
      const exported: unknown = Reflect.get(icons, name);
      expect(typeof exported, `${name} is not exported as a function`).toBe('function');
    }
  });

  it('accepts the same IconProps shape on every export — size, className, title', () => {
    for (const name of EXPECTED_ICON_NAMES) {
      const Icon = Reflect.get(icons, name) as (
        props: icons.IconProps,
      ) => React.ReactNode;
      // No props at all.
      const bare = render(<Icon />);
      expect(
        bare.container.querySelector('svg'),
        `${name} with no props`,
      ).not.toBeNull();
      bare.unmount();

      // Every declared size.
      for (const size of ['inline', 'nav', 'head', 'empty'] as const) {
        const sized = render(<Icon size={size} />);
        expect(
          sized.container.querySelector('svg')?.getAttribute('class'),
          `${name} at size "${size}"`,
        ).toContain(`icon-${size}`);
        sized.unmount();
      }

      // className passes through.
      const classed = render(<Icon className="probe-class" />);
      expect(
        classed.container.querySelector('svg')?.getAttribute('class'),
        `${name} with a className`,
      ).toContain('probe-class');
      classed.unmount();

      // title names the shape and switches it to an accessible role.
      const titled = render(<Icon title="a label" />);
      const svg = titled.container.querySelector('svg');
      expect(svg?.getAttribute('role'), `${name} with a title`).toBe('img');
      expect(svg?.getAttribute('aria-label'), `${name} with a title`).toBe('a label');
      titled.unmount();
    }
  });
});
