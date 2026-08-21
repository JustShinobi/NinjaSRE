import { describe, expect, it } from 'vitest';

import {
  BOUNDARY_MINIMUM,
  BODY_MINIMUM,
  contrastRatio,
  relativeLuminance,
} from '@/design/contrast';
import { bodyPairs, boundaryPairs, THEMES } from '@/design/tokens';

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

  it('reaches 3:1 on every boundary a viewer has to find, in both themes', () => {
    for (const theme of THEMES) {
      for (const pair of boundaryPairs(theme)) {
        const ratio = contrastRatio(pair.foreground, pair.background);
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
