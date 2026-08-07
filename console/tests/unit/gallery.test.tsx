import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import * as primitives from '@/components';
import { GALLERY, galleryPrimitiveNames } from '@/gallery/registry';
import { ICON_NAMES } from '@/design/icons';
import * as icons from '@/design/icons';

import { audit, report } from './support/accessibility';

/**
 * The gallery is the contract, and this is what holds it to that.
 *
 * Two claims. Every primitive the library exports appears in the gallery — so a
 * component cannot be added without also being shown, screenshotted and
 * audited, and the failure names the one that was forgotten. And every entry in
 * the gallery passes the accessibility audit at the declared level, which is
 * the only way "the components are accessible" stops being an intention.
 */

/** Everything the barrel exports that is a component rather than a type. */
function exportedPrimitives(): readonly string[] {
  return Object.keys(primitives)
    .filter((name) => /^[A-Z]/.test(name))
    .sort();
}

describe('gallery coverage', () => {
  it('shows every primitive the library exports', () => {
    const shown = new Set(galleryPrimitiveNames());
    const missing = exportedPrimitives().filter((name) => !shown.has(name));

    expect(
      missing,
      'these primitives are exported and not in the gallery, so nothing screenshots or audits them',
    ).toEqual([]);
  });

  it('shows nothing the library does not export', () => {
    const exported = new Set(exportedPrimitives());
    const invented = galleryPrimitiveNames().filter((name) => !exported.has(name));

    expect(
      invented,
      'the gallery shows a primitive the library does not export',
    ).toEqual([]);
  });

  it('gives every primitive at least one specimen, with a summary', () => {
    for (const primitive of GALLERY) {
      expect(primitive.entries.length, primitive.name).toBeGreaterThan(0);
      expect(primitive.summary.length, primitive.name).toBeGreaterThan(20);
    }
  });

  it('gives every specimen an identifier of its own', () => {
    const ids = GALLERY.flatMap((primitive) =>
      primitive.entries.map((entry) => entry.id),
    );
    expect(new Set(ids).size, 'two specimens share an identifier').toBe(ids.length);
  });

  it('ships every icon it declares, and declares every icon it ships', () => {
    const exported = Object.keys(icons)
      .filter((name) => name.endsWith('Icon'))
      .sort();
    expect(exported).toEqual([...ICON_NAMES].sort());
  });
});

describe('the accessibility audit over every gallery entry', () => {
  for (const primitive of GALLERY) {
    for (const entry of primitive.entries) {
      it(`${primitive.name} · ${entry.label} has no violation`, () => {
        const { container } = render(<div>{entry.node}</div>);
        const violations = audit(container);

        expect(violations, `\n${report(violations)}`).toEqual([]);
      });
    }
  }
});

describe('the audit itself', () => {
  it('finds an unnamed control, so a clean run means something', () => {
    const { container } = render(
      <button type="button">
        <span aria-hidden="true">×</span>
      </button>,
    );
    expect(audit(container).map((violation) => violation.rule)).toContain(
      'interactive-element-has-a-name',
    );
  });

  it('finds a field with no label', () => {
    const { container } = render(<input type="text" placeholder="Node name" />);
    expect(audit(container).map((violation) => violation.rule)).toContain(
      'form-field-has-a-label',
    );
  });

  it('finds a reference that points at nothing', () => {
    const { container } = render(
      <button type="button" aria-describedby="not-here">
        Retry
      </button>,
    );
    expect(audit(container).map((violation) => violation.rule)).toContain(
      'references-point-at-something',
    );
  });

  it('finds a focusable element inside a hidden region', () => {
    const { container } = render(
      <div aria-hidden="true">
        <button type="button">Retry</button>
      </div>,
    );
    expect(audit(container).map((violation) => violation.rule)).toContain(
      'hidden-regions-hold-nothing-focusable',
    );
  });

  it('finds a positive tabindex', () => {
    const { container } = render(
      <button type="button" tabIndex={3}>
        Retry
      </button>,
    );
    expect(audit(container).map((violation) => violation.rule)).toContain(
      'no-positive-tabindex',
    );
  });

  it('finds a duplicated identifier', () => {
    const { container } = render(
      <div>
        <span id="twice">a</span>
        <span id="twice">b</span>
      </div>,
    );
    expect(audit(container).map((violation) => violation.rule)).toContain(
      'identifiers-are-unique',
    );
  });
});
