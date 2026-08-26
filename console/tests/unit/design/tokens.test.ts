import { describe, expect, it } from 'vitest';

import {
  BORDER_WIDTHS,
  COLOUR_ROLES,
  colour,
  DURATIONS,
  RADII,
  SEMANTIC_ROLES,
  SPACING,
  THEMES,
  TYPE_STEPS,
  typeStep,
} from '@/design/tokens';

/**
 * The table is the design, so this is where the design is asserted.
 *
 * Every colour value below is the one the design document publishes, compared
 * byte for byte rather than by eye: a token that drifts by one digit is a token
 * whose measured contrast is no longer the measured contrast anybody checked.
 *
 * The scales are asserted as *closed sets* — equality, not membership — because
 * a scale you may add a step to is a suggestion, and the whole point of the
 * closed set is that the lint rule has something finite to police.
 */

const LIGHT: Readonly<Record<string, string>> = {
  surface: '#ffffff',
  sunken: '#f2f5f4',
  raised: '#ffffff',
  text: '#1a2420',
  muted: '#4c5a55',
  accent: '#0a7452',
  'on-accent': '#ffffff',
  'accent-bg': '#e2f2ec',
  border: '#d8e0dd',
  'border-strong': '#6d7c76',
  success: '#0a7452',
  'success-bg': '#e2f2ec',
  warning: '#8a5a12',
  'warning-bg': '#f7efdd',
  danger: '#a51f1f',
  'on-danger': '#ffffff',
  'danger-bg': '#f9e9e9',
  info: '#0a5f8f',
  'info-bg': '#e4eff5',
};

const DARK: Readonly<Record<string, string>> = {
  surface: '#141b18',
  sunken: '#0d1311',
  raised: '#1a2320',
  text: '#e4ebe8',
  muted: '#a3b2ac',
  accent: '#3ad195',
  'on-accent': '#062018',
  'accent-bg': '#12271f',
  border: '#24302b',
  'border-strong': '#8b9a94',
  success: '#3ad195',
  'success-bg': '#12271f',
  warning: '#e0a84e',
  'warning-bg': '#2a2214',
  danger: '#ef7070',
  'on-danger': '#2a0d0d',
  'danger-bg': '#2a1616',
  info: '#6cb8e0',
  'info-bg': '#12242c',
};

describe('the colour tokens', () => {
  it('carries the published value for every documented role, in light', () => {
    for (const [role, value] of Object.entries(LIGHT)) {
      expect(colour('light', role as (typeof COLOUR_ROLES)[number]), role).toBe(value);
    }
  });

  it('carries the published value for every documented role, in dark', () => {
    for (const [role, value] of Object.entries(DARK)) {
      expect(colour('dark', role as (typeof COLOUR_ROLES)[number]), role).toBe(value);
    }
  });

  it('defines every role in both themes, so a screen written against tokens works in both', () => {
    for (const theme of THEMES) {
      for (const role of COLOUR_ROLES) {
        expect(colour(theme, role), `${theme}/${role}`).toMatch(/^#[0-9a-f]{6}$/);
      }
    }
  });

  it('gives every semantic role a foreground, a tint and a fill', () => {
    expect([...SEMANTIC_ROLES]).toEqual([
      'success',
      'warning',
      'danger',
      'info',
      'neutral',
    ]);
    for (const theme of THEMES) {
      for (const role of SEMANTIC_ROLES) {
        expect(colour(theme, role)).toMatch(/^#/);
        expect(colour(theme, `on-${role}`)).toMatch(/^#/);
        expect(colour(theme, `${role}-bg`)).toMatch(/^#/);
      }
    }
  });
});

describe('the scales', () => {
  it('spaces on a closed four-pixel set', () => {
    expect(Object.values(SPACING)).toEqual([4, 8, 12, 16, 24, 32, 48]);
  });

  it('rounds on a closed set', () => {
    expect(Object.values(RADII)).toEqual([4, 6, 10, 14]);
  });

  it('borders on a closed set', () => {
    expect(Object.values(BORDER_WIDTHS)).toEqual([1, 1.5, 2]);
  });

  it('animates on a closed set, and includes the removal reduced motion needs', () => {
    expect(Object.values(DURATIONS)).toEqual([0, 120, 160, 200]);
  });

  it('types on the eight documented steps, each with its size, line and weight', () => {
    expect(Object.keys(TYPE_STEPS)).toEqual([
      'display',
      'title',
      'section',
      'strong',
      'body',
      'small',
      'meta',
      'micro',
    ]);
    expect(typeStep('display')).toMatchObject({ size: 34, line: 1.15, weight: 680 });
    expect(typeStep('title')).toMatchObject({ size: 26, line: 1.25, weight: 650 });
    expect(typeStep('section')).toMatchObject({ size: 20, line: 1.3, weight: 650 });
    expect(typeStep('strong')).toMatchObject({ size: 16, line: 1.45, weight: 600 });
    expect(typeStep('body')).toMatchObject({ size: 14, line: 1.5, weight: 400 });
    expect(typeStep('small')).toMatchObject({ size: 13, line: 1.5, weight: 400 });
    expect(typeStep('meta')).toMatchObject({ size: 12, line: 1.45, weight: 400 });
    expect(typeStep('micro')).toMatchObject({ size: 12, line: 1.4, weight: 600 });
  });

  it('leaves labels untracked and tracks headings inwards', () => {
    // `micro` was 11px of capitals tracked to 0.06em. Capitals plus tracking
    // is what an administrative console of a decade ago used to say "this is
    // a label", and it costs scanning speed: a reader matches word shapes,
    // and capitals give every word the same one.
    expect(typeStep('micro').tracking).toBe('0em');
    expect(typeStep('display').tracking).toBe('-0.03em');
    expect(typeStep('body').tracking).toBe('0em');
  });
});
