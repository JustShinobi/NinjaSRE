import { act, within } from '@testing-library/react';
import { createRoot, type Root } from 'react-dom/client';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import GalleryPage from '@/app/gallery/page';
import { contrastRatio } from '@/design/contrast';
import { galleryPrimitiveNames } from '@/gallery/registry';
import { bodyPairs, TYPE_STEPS } from '@/design/tokens';

import { audit, report } from './support/accessibility';

/**
 * The gallery route, rendered whole.
 *
 * The registry test proves every primitive is registered; this proves the route
 * actually renders them, which is a different claim — a registry the page
 * silently drops half of would pass the first and fail nobody. It is also where
 * the accessibility audit meets the composition rather than the specimens: two
 * components that are each fine can still produce a duplicated identifier when
 * they land on one page.
 *
 * Rendered **once for the file**, mounted by hand rather than through the
 * testing library, because the library's per-test cleanup would tear it down
 * between assertions and every one of them would pay for the whole page again.
 * The page is the largest thing this console renders and it has no state any of
 * these tests change; five renders of it were five copies of one second, and the
 * first of them was close enough to the runner's timeout to fail on a loaded
 * machine.
 */

let container: HTMLElement;
let root: Root;

beforeAll(() => {
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => {
    root.render(<GalleryPage />);
  });
});

afterAll(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe('the gallery route', () => {
  it('renders a section for every primitive in the registry', () => {
    // One pass over the headings rather than one query per primitive: an
    // accessible-name query walks the whole tree, and thirty of them over the
    // largest page in the console is most of what this file used to cost.
    const headings = new Set(
      [...container.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((heading) =>
        heading.textContent.trim(),
      ),
    );

    const missing = galleryPrimitiveNames().filter((name) => !headings.has(name));
    expect(missing, `the gallery renders no section for ${missing.join(', ')}`).toEqual(
      [],
    );
  });

  it('says what it is, so nobody mistakes it for part of the console', () => {
    expect(
      within(container).getByRole('heading', { level: 1, name: 'Design system' }),
    ).toBeInTheDocument();
    expect(within(container).getByText(/Not part of the console/)).toBeInTheDocument();
  });

  it('prints the measured ratio for every pair, computed rather than written down', () => {
    const pair = bodyPairs('light')[0];

    expect(pair).toBeDefined();
    if (pair === undefined) return;
    const ratio = contrastRatio(pair.foreground, pair.background).toFixed(2);
    expect(
      within(container).getAllByText(new RegExp(`${ratio}:1`)).length,
    ).toBeGreaterThan(0);
  });

  it('shows every step of the type scale by name', () => {
    for (const name of Object.keys(TYPE_STEPS)) {
      expect(
        within(container).getAllByText(new RegExp(`^${name} `)).length,
        name,
      ).toBeGreaterThan(0);
    }
  });

  it('has no accessibility violation anywhere on the page', () => {
    const violations = audit(container);

    expect(violations, `\n${report(violations)}`).toEqual([]);
  });
});
