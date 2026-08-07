import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

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
 */

describe('the gallery route', () => {
  it('renders a section for every primitive in the registry', () => {
    render(<GalleryPage />);

    for (const name of galleryPrimitiveNames()) {
      expect(screen.getByRole('heading', { name }), name).toBeInTheDocument();
    }
  });

  it('says what it is, so nobody mistakes it for part of the console', () => {
    render(<GalleryPage />);

    expect(
      screen.getByRole('heading', { level: 1, name: 'Design system' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Not part of the console/)).toBeInTheDocument();
  });

  it('prints the measured ratio for every pair, computed rather than written down', () => {
    render(<GalleryPage />);
    const pair = bodyPairs('light')[0];

    expect(pair).toBeDefined();
    if (pair === undefined) return;
    const ratio = contrastRatio(pair.foreground, pair.background).toFixed(2);
    expect(screen.getAllByText(new RegExp(`${ratio}:1`)).length).toBeGreaterThan(0);
  });

  it('shows every step of the type scale by name', () => {
    render(<GalleryPage />);

    for (const name of Object.keys(TYPE_STEPS)) {
      expect(screen.getAllByText(new RegExp(`^${name} `)).length, name).toBeGreaterThan(
        0,
      );
    }
  });

  it('has no accessibility violation anywhere on the page', () => {
    const { container } = render(<GalleryPage />);
    const violations = audit(container);

    expect(violations, `\n${report(violations)}`).toEqual([]);
  });
});
