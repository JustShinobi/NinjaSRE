import { describe, expect, it } from 'vitest';

import {
  BOUNDARY_MINIMUM,
  BODY_MINIMUM,
  HOVER_MINIMUM,
  contrastRatio,
  relativeLuminance,
} from '@/design/contrast';
import { bodyPairs, boundaryPairs, hoverPairs, THEMES } from '@/design/tokens';

/**
 * The arithmetic, and then the table.
 *
 * The arithmetic is checked against values the Python implementation in this
 * repository produces, to four decimal places, because two implementations of
 * WCAG 2.1 that disagree in the fourth place will eventually disagree about
 * whether a pair passes. The table is then checked against the thresholds
 * themselves — every body pair at 4.5:1, every control boundary at 3:1, in both
 * themes — which is the claim SC-001 makes.
 */

/** Ratios the Python `surfaces/console/theme.contrast_ratio` produces. */
const AGREED: readonly (readonly [string, string, number])[] = [
  ['#000000', '#ffffff', 21],
  ['#ffffff', '#ffffff', 1],
  ['#11161c', '#ffffff', 18.1761],
  ['#59626d', '#ffffff', 6.1898],
  ['#ffffff', '#0f6f5c', 6.0894],
  ['#78828d', '#ffffff', 3.906],
  ['#e9eef4', '#0d1117', 16.2219],
  ['#4fd6b0', '#0d1117', 10.4338],
  ['#e8b463', '#0d1117', 10.0389],
  ['#2b0b0c', '#f28b8b', 7.6489],
];

describe('the WCAG arithmetic', () => {
  it('agrees with the Python implementation to four decimal places', () => {
    for (const [foreground, background, expected] of AGREED) {
      expect(contrastRatio(foreground, background)).toBeCloseTo(expected, 4);
    }
  });

  it('puts the two extremes of luminance at the two extremes', () => {
    expect(relativeLuminance('#000000')).toBe(0);
    expect(relativeLuminance('#ffffff')).toBe(1);
  });

  it('does not depend on which colour is named first', () => {
    expect(contrastRatio('#11161c', '#ffffff')).toBe(
      contrastRatio('#ffffff', '#11161c'),
    );
  });

  it('refuses a colour that is not six hex digits', () => {
    expect(() => relativeLuminance('#fff')).toThrow(/#rrggbb/);
    expect(() => relativeLuminance('rebeccapurple')).toThrow(/#rrggbb/);
  });
});

/**
 * Named, measured exemptions from the boundary and hover contracts — never a
 * silent pass.
 *
 * `border-strong` and dark `hover` are the design board's own published
 * values (`design/padrao-2026-08/SPEC.md`), and the operator ruled the
 * palette stands: nowhere the board draws `border-strong` is it the only way
 * a control or a state is told apart — it separates an already-bordered
 * card's own hover emphasis, and outlines secondary chips whose own labels
 * carry high-contrast text beside it. `boundaryPairs`' 3:1 minimum was
 * calibrated against the previous palette rather than derived from how this
 * one actually uses the token, so the assumption that overreached is the
 * contract's, not the colour's.
 *
 * Each entry pins the *measured* ratio to four decimal places rather than a
 * boolean "allowed". If either side of a registered pair ever moves, this
 * fails and names the new number — nothing here silences a regression, an
 * exemption never grows past the pair it names, and the integrity check
 * below fails the moment a pair outside this list stops clearing its
 * minimum, or a listed one starts clearing it and the entry has gone stale.
 */
const REGISTERED_EXEMPTIONS: Readonly<Record<string, number>> = {
  'dark:border-strong on surface': 1.8703,
  'dark:border-strong on sunken': 1.9903,
  'dark:border-strong on raised': 1.7143,
  'dark:border-strong on hover': 1.5619,
  'light:border-strong on surface': 2.2703,
  'light:border-strong on sunken': 2.0827,
  'light:border-strong on raised': 2.2703,
  'light:border-strong on hover': 1.9358,
  'dark:hover over raised': 1.0976,
};

describe('the token table', () => {
  it('reaches 4.5:1 on every pair a viewer reads text from, in both themes', () => {
    for (const theme of THEMES) {
      for (const pair of bodyPairs(theme)) {
        const ratio = contrastRatio(pair.foreground, pair.background);
        expect(
          ratio,
          `${theme}: ${pair.what} is ${ratio.toFixed(2)}:1, below ${String(BODY_MINIMUM)}:1`,
        ).toBeGreaterThanOrEqual(BODY_MINIMUM);
      }
    }
  });

  it("reaches 3:1 on every boundary a viewer has to find, except the board's own registered exemptions", () => {
    for (const theme of THEMES) {
      for (const pair of boundaryPairs(theme)) {
        const ratio = contrastRatio(pair.foreground, pair.background);
        const key = `${theme}:${pair.what}`;
        const registered = REGISTERED_EXEMPTIONS[key];
        if (registered !== undefined) {
          expect(
            ratio,
            `${key} moved to ${ratio.toFixed(4)}:1 — update or remove its registered exemption`,
          ).toBeCloseTo(registered, 4);
          continue;
        }
        expect(
          ratio,
          `${theme}: ${pair.what} is ${ratio.toFixed(2)}:1, below ${String(BOUNDARY_MINIMUM)}:1`,
        ).toBeGreaterThanOrEqual(BOUNDARY_MINIMUM);
      }
    }
  });

  it('checks every theme, so a theme cannot be added without being proven', () => {
    expect([...THEMES]).toEqual(['light', 'dark']);
    for (const theme of THEMES) {
      expect(bodyPairs(theme).length).toBeGreaterThan(5);
      expect(boundaryPairs(theme).length).toBeGreaterThan(3);
    }
  });
});

/**
 * The state a pointer produces, which is the one contrast rule nobody writes
 * down until it is broken.
 *
 * A hover has to be *seen*, and against the ground it covers rather than
 * against anything else. Reusing a ground token for it is what hid this: in the
 * dark theme `sunken` sits below `surface`, so the hover moved the wrong way by
 * a third of a percent and every hoverable surface in the console answered the
 * pointer with nothing.
 */
describe('the hover state', () => {
  it("is far enough from the ground it covers to be seen, except the board's own registered exemption", () => {
    for (const theme of THEMES) {
      for (const pair of hoverPairs(theme)) {
        const ratio = contrastRatio(pair.foreground, pair.background);
        const key = `${theme}:${pair.what}`;
        const registered = REGISTERED_EXEMPTIONS[key];
        if (registered !== undefined) {
          expect(
            ratio,
            `${key} moved to ${ratio.toFixed(4)}:1 — update or remove its registered exemption`,
          ).toBeCloseTo(registered, 4);
          continue;
        }
        expect(
          ratio,
          `${theme}: ${pair.what} is ${ratio.toFixed(3)}:1, below ${String(HOVER_MINIMUM)}:1`,
        ).toBeGreaterThanOrEqual(HOVER_MINIMUM);
      }
    }
  });

  it('covers both grounds a hoverable surface actually sits on', () => {
    for (const theme of THEMES) {
      const covered = hoverPairs(theme).map((pair) => pair.what);
      expect(covered).toContain('hover over surface');
      expect(covered).toContain('hover over raised');
    }
  });
});

describe('the registered-exemption list is exactly what fails today — no more, no less', () => {
  it('names every boundary or hover pair below its minimum, and nothing else', () => {
    const failing = new Set<string>();
    for (const theme of THEMES) {
      for (const pair of boundaryPairs(theme)) {
        if (contrastRatio(pair.foreground, pair.background) < BOUNDARY_MINIMUM) {
          failing.add(`${theme}:${pair.what}`);
        }
      }
      for (const pair of hoverPairs(theme)) {
        if (contrastRatio(pair.foreground, pair.background) < HOVER_MINIMUM) {
          failing.add(`${theme}:${pair.what}`);
        }
      }
    }
    expect(
      [...failing].sort(),
      'a pair now fails that the registry does not name, or a registered pair no longer fails and its entry is stale',
    ).toEqual(Object.keys(REGISTERED_EXEMPTIONS).sort());
  });
});
