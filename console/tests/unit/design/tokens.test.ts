import { describe, expect, it } from 'vitest';

import {
  BORDER_WIDTHS,
  COLOUR_ROLES,
  colour,
  DURATIONS,
  FONT_STACKS,
  RADII,
  SEMANTIC_ROLES,
  SHELL,
  SPACING,
  THEMES,
  TYPE_STEPS,
  typeStep,
} from '@/design/tokens';

/**
 * The table is the design, so this is where the design is asserted.
 *
 * Every colour value below is the board's own (`design/padrao-2026-08/SPEC.md`),
 * compared byte for byte rather than by eye: a token that drifts by one digit
 * is a token whose measured contrast is no longer the measured contrast
 * anybody checked. Two of them — `border-strong` in both themes, and dark
 * `hover` against `raised` — do not clear this table's own contrast contract
 * as generally stated; the operator ruled the board stands regardless, on
 * the grounds that neither is ever the sole way a control or a state is told
 * apart on any artboard. `tests/unit/design/contrast.test.ts` carries both as
 * named, measured exemptions instead of the palette bending to fit the
 * contract — the full account is in this feature's own control file.
 *
 * The scales are asserted as *closed sets* — equality, not membership —
 * because a scale you may add a step to is a suggestion, and the whole point
 * of the closed set is that the lint rule has something finite to police.
 */

const LIGHT: Readonly<Record<string, string>> = {
  surface: '#ffffff',
  sunken: '#f2f6f4',
  raised: '#ffffff',
  hover: '#e9eeec',
  text: '#17211d',
  muted: '#55645e',
  accent: '#0a7452',
  'on-accent': '#ffffff',
  'accent-bg': '#e2f2ec',
  border: '#dde5e1',
  // The board's own hex. Reaches only ~1.9-2.3:1 against the four grounds —
  // below the 3:1 boundary minimum — and is a registered exemption in
  // contrast.test.ts rather than an adjusted value; see that file and this
  // feature's control document.
  'border-strong': '#9fb0a8',
  success: '#0a7452',
  'on-success': '#ffffff',
  'success-bg': '#e2f2ec',
  warning: '#8a5a12',
  'on-warning': '#ffffff',
  'warning-bg': '#f7efdd',
  danger: '#a51f1f',
  'on-danger': '#ffffff',
  'danger-bg': '#f9e9e9',
  info: '#0a5f8f',
  'on-info': '#ffffff',
  'info-bg': '#e4eff5',
  neutral: '#55645e',
  'on-neutral': '#ffffff',
  'neutral-bg': '#f2f5f4',
};

const DARK: Readonly<Record<string, string>> = {
  surface: '#101815',
  sunken: '#0a100e',
  raised: '#16211d',
  // The board's own hex. Falls a fraction short of HOVER_MINIMUM against
  // `raised` — a registered exemption in contrast.test.ts, not an adjusted
  // value; see that file and this feature's control document.
  hover: '#1c2925',
  text: '#e9f0ec',
  muted: '#9fb2aa',
  accent: '#3ad195',
  'on-accent': '#062018',
  'accent-bg': '#12271f',
  border: '#223029',
  // The board's own hex. Reaches only ~1.6-2.0:1 against the four grounds —
  // below the 3:1 boundary minimum — and is a registered exemption in
  // contrast.test.ts rather than an adjusted value; see that file and this
  // feature's control document.
  'border-strong': '#35493f',
  success: '#3ad195',
  'on-success': '#062018',
  'success-bg': '#12271f',
  warning: '#e0a84e',
  'on-warning': '#17211d',
  'warning-bg': '#2a2214',
  danger: '#ef7070',
  'on-danger': '#2a1616',
  'danger-bg': '#2a1616',
  info: '#6cb8e0',
  'on-info': '#062018',
  'info-bg': '#12242c',
  neutral: '#a3b2aa',
  'on-neutral': '#0d1311',
  'neutral-bg': '#0d1311',
};

describe('the colour tokens', () => {
  it('declares all 26 roles, and only those 26', () => {
    expect([...COLOUR_ROLES].sort()).toEqual(Object.keys(LIGHT).sort());
    expect([...COLOUR_ROLES].sort()).toEqual(Object.keys(DARK).sort());
    expect(COLOUR_ROLES.length).toBe(26);
  });

  it('carries the board value for every documented role, in light', () => {
    for (const [role, value] of Object.entries(LIGHT)) {
      expect(colour('light', role as (typeof COLOUR_ROLES)[number]), role).toBe(value);
    }
  });

  it('carries the board value for every documented role, in dark', () => {
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

  it('follows the accent family for success, in both themes', () => {
    expect(colour('dark', 'success')).toBe(colour('dark', 'accent'));
    expect(colour('light', 'success')).toBe(colour('light', 'accent'));
    expect(colour('dark', 'on-success')).toBe(colour('dark', 'on-accent'));
    expect(colour('light', 'on-success')).toBe(colour('light', 'on-accent'));
    expect(colour('dark', 'success-bg')).toBe(colour('dark', 'accent-bg'));
    expect(colour('light', 'success-bg')).toBe(colour('light', 'accent-bg'));
  });
});

describe('the scales', () => {
  it('spaces on a closed four-pixel set', () => {
    expect(Object.values(SPACING)).toEqual([4, 8, 12, 16, 24, 32, 48]);
  });

  it("rounds on the board's closed set — chip 6, control 8, card 12, panel 16", () => {
    expect(Object.values(RADII)).toEqual([6, 8, 12, 16]);
  });

  it('borders on a closed set', () => {
    expect(Object.values(BORDER_WIDTHS)).toEqual([1, 1.5, 2]);
  });

  it('animates on a closed set, and includes the three motion primitives', () => {
    expect(Object.values(DURATIONS)).toEqual([0, 120, 160, 200, 2000, 240, 1600]);
    expect(DURATIONS.pulse).toBe(2000);
    expect(DURATIONS.slide).toBe(240);
    expect(DURATIONS.shimmer).toBe(1600);
  });

  it("types H1 and KPI numbers at the board's weight and size", () => {
    expect(typeStep('title')).toMatchObject({ size: 26, weight: 700 });
    expect(typeStep('display')).toMatchObject({ size: 30, weight: 700 });
    expect(typeStep('body')).toMatchObject({ size: 14, line: 1.5 });
    expect(typeStep('meta').size).toBe(12.5);
    expect(typeStep('micro').size).toBe(11);
  });

  it('types on the eight documented steps', () => {
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
  });

  it("fixes the shell at the board's two measurements", () => {
    expect(SHELL.sidebar).toBe(232);
    expect(SHELL.topbar).toBe(60);
  });

  it('gives the display family to titles and KPI numbers, self-hosted', () => {
    expect(FONT_STACKS.display).toBe(
      "'Space Grotesk', ui-sans-serif, system-ui, sans-serif",
    );
    expect(FONT_STACKS.sans).toBe("'IBM Plex Sans', system-ui, sans-serif");
    expect(FONT_STACKS.mono).toBe(
      "'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace",
    );
  });
});
