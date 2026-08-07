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
  sunken: '#f5f7f8',
  raised: '#ffffff',
  text: '#11161c',
  muted: '#59626d',
  accent: '#0f6f5c',
  'on-accent': '#ffffff',
  'accent-bg': '#e7f3f0',
  border: '#d5dade',
  'border-strong': '#78828d',
  success: '#136c46',
  'success-bg': '#e8f5ee',
  warning: '#8a5a00',
  'warning-bg': '#fdf4e3',
  danger: '#a11b21',
  'on-danger': '#ffffff',
  'danger-bg': '#fdecec',
  info: '#0a5ea8',
  'info-bg': '#eaf2fb',
};

const DARK: Readonly<Record<string, string>> = {
  surface: '#0d1117',
  sunken: '#0a0e13',
  raised: '#161c24',
  text: '#e9eef4',
  muted: '#9aa5b1',
  accent: '#4fd6b0',
  'on-accent': '#06231c',
  'accent-bg': '#0e2b25',
  border: '#242c36',
  'border-strong': '#8b96a3',
  success: '#5fd996',
  'success-bg': '#0f2a1e',
  warning: '#e8b463',
  'warning-bg': '#2c2110',
  danger: '#f28b8b',
  'on-danger': '#2b0b0c',
  'danger-bg': '#2e1416',
  info: '#77b6f5',
  'info-bg': '#0f2237',
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
    expect(typeStep('micro')).toMatchObject({ size: 11, line: 1.4, weight: 650 });
  });

  it('tracks uppercase micro outwards and headings inwards', () => {
    expect(typeStep('micro').tracking).toBe('0.06em');
    expect(typeStep('display').tracking).toBe('-0.03em');
    expect(typeStep('body').tracking).toBe('0em');
  });
});
