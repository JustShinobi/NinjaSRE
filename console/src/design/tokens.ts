/**
 * The design system's vocabulary, as data.
 *
 * This module is the single input to three consumers — the runtime custom
 * properties, the Tailwind theme, and the contrast proof — so a value written
 * here reaches all three and a value written anywhere else reaches none of
 * them. That is the whole mechanism: colour is declared by role rather than by
 * hue, every scale is a closed set, and the lint rule rejects anything that is
 * not on one.
 *
 * The colour values are computed rather than chosen. Each pair below was
 * measured with the WCAG arithmetic in `contrast.ts` and reaches its threshold;
 * `tests/unit/design/contrast.test.ts` re-measures every one of them on every
 * run, so a value edited by eye fails before it is reviewed.
 */

/** The two themes. Both declare the same token names with different values. */
export const THEMES = ['light', 'dark'] as const;

export type Theme = (typeof THEMES)[number];

/**
 * The five roles a status is rendered in.
 *
 * Nothing maps a status to a hue. A status maps to a role and a role maps to a
 * token pair, so two screens cannot disagree about what "degraded" looks like
 * because neither of them decides.
 */
export const SEMANTIC_ROLES = [
  'success',
  'warning',
  'danger',
  'info',
  'neutral',
] as const;

export type SemanticRole = (typeof SEMANTIC_ROLES)[number];

/** Every colour token, by the job it does rather than by the colour it is. */
export const COLOUR_ROLES = [
  'surface',
  'sunken',
  'raised',
  'text',
  'muted',
  'accent',
  'on-accent',
  'accent-bg',
  'border',
  'border-strong',
  'success',
  'on-success',
  'success-bg',
  'warning',
  'on-warning',
  'warning-bg',
  'danger',
  'on-danger',
  'danger-bg',
  'info',
  'on-info',
  'info-bg',
  'neutral',
  'on-neutral',
  'neutral-bg',
] as const;

export type ColourRole = (typeof COLOUR_ROLES)[number];

/**
 * The light theme. Chosen for a bright office and a laptop at full daylight.
 *
 * `raised` equals `surface` here on purpose: light elevation is carried by the
 * shadow and the border, and a second near-white would read as a rendering
 * artefact rather than as depth. Dark elevation cannot use a shadow — there is
 * nothing for it to fall on — so there the two differ.
 */
const LIGHT: Readonly<Record<ColourRole, string>> = {
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
  'on-success': '#ffffff',
  'success-bg': '#e8f5ee',
  warning: '#8a5a00',
  'on-warning': '#ffffff',
  'warning-bg': '#fdf4e3',
  danger: '#a11b21',
  'on-danger': '#ffffff',
  'danger-bg': '#fdecec',
  info: '#0a5ea8',
  'on-info': '#ffffff',
  'info-bg': '#eaf2fb',
  neutral: '#59626d',
  'on-neutral': '#ffffff',
  'neutral-bg': '#f5f7f8',
};

/** The dark theme. The same names, and the same geometry, at different values. */
const DARK: Readonly<Record<ColourRole, string>> = {
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
  'on-success': '#0d1117',
  'success-bg': '#0f2a1e',
  warning: '#e8b463',
  'on-warning': '#0d1117',
  'warning-bg': '#2c2110',
  danger: '#f28b8b',
  'on-danger': '#2b0b0c',
  'danger-bg': '#2e1416',
  info: '#77b6f5',
  'on-info': '#0d1117',
  'info-bg': '#0f2237',
  neutral: '#9aa5b1',
  'on-neutral': '#0d1117',
  'neutral-bg': '#0a0e13',
};

const PALETTES: Readonly<Record<Theme, Readonly<Record<ColourRole, string>>>> = {
  light: LIGHT,
  dark: DARK,
};

/** The value `role` has in `theme`. */
export function colour(theme: Theme, role: ColourRole): string {
  return PALETTES[theme][role];
}

/** One foreground on one background, and what the pair is for. */
export interface Pair {
  readonly what: string;
  readonly foreground: string;
  readonly background: string;
}

/** The grounds a viewer reads text on. */
const GROUNDS = ['surface', 'sunken', 'raised'] as const;

/** Every pair carrying text, which has to reach 4.5:1. */
export function bodyPairs(theme: Theme): readonly Pair[] {
  const at = (role: ColourRole): string => colour(theme, role);
  const pairs: Pair[] = [];
  for (const ground of GROUNDS) {
    pairs.push({
      what: `text on ${ground}`,
      foreground: at('text'),
      background: at(ground),
    });
    pairs.push({
      what: `muted on ${ground}`,
      foreground: at('muted'),
      background: at(ground),
    });
    for (const role of SEMANTIC_ROLES) {
      pairs.push({
        what: `${role} on ${ground}`,
        foreground: at(role),
        background: at(ground),
      });
    }
    pairs.push({
      what: `accent on ${ground}`,
      foreground: at('accent'),
      background: at(ground),
    });
  }
  pairs.push({
    what: 'on-accent on accent',
    foreground: at('on-accent'),
    background: at('accent'),
  });
  pairs.push({
    what: 'accent on accent-bg',
    foreground: at('accent'),
    background: at('accent-bg'),
  });
  for (const role of SEMANTIC_ROLES) {
    pairs.push({
      what: `on-${role} on ${role}`,
      foreground: at(`on-${role}`),
      background: at(role),
    });
    pairs.push({
      what: `${role} on ${role}-bg`,
      foreground: at(role),
      background: at(`${role}-bg`),
    });
  }
  return pairs;
}

/**
 * Every pair a viewer has to *find* rather than read, which has to reach 3:1.
 *
 * `border` is deliberately absent. It separates table rows and card edges,
 * where WCAG 1.4.11 does not apply; collapsing it into `border-strong` would
 * either make every table line heavy or make every control boundary
 * non-compliant, so there are two tokens and only one of them is here.
 */
export function boundaryPairs(theme: Theme): readonly Pair[] {
  const at = (role: ColourRole): string => colour(theme, role);
  const pairs: Pair[] = [];
  for (const ground of GROUNDS) {
    pairs.push({
      what: `border-strong on ${ground}`,
      foreground: at('border-strong'),
      background: at(ground),
    });
    pairs.push({
      what: `accent ring on ${ground}`,
      foreground: at('accent'),
      background: at(ground),
    });
  }
  for (const role of SEMANTIC_ROLES) {
    pairs.push({
      what: `${role} boundary on ${role}-bg`,
      foreground: at(role),
      background: at(`${role}-bg`),
    });
  }
  return pairs;
}

/**
 * Spacing, on a four-pixel base.
 *
 * Seven steps and no eighth. Card padding is `4`, page gutter and grid gap are
 * `5`, a section break is `6`; those three decisions are why the set has the
 * shape it has rather than doubling all the way up.
 */
export const SPACING = {
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 24,
  6: 32,
  7: 48,
} as const;

/** Corner radii: badge, control, card, panel. */
export const RADII = {
  1: 4,
  2: 6,
  3: 10,
  4: 14,
} as const;

/**
 * Border widths.
 *
 * `1` separates and bounds; `1.5` is the hollow status shape, which needs to
 * read as a ring rather than as a smudge at eight pixels across; `2` is the
 * focus ring and the emphasis border on a consequential card.
 */
export const BORDER_WIDTHS = {
  1: 1,
  2: 1.5,
  3: 2,
} as const;

/**
 * Durations, in milliseconds.
 *
 * `none` is a member of the scale rather than an absence, because reduced
 * motion is satisfied by *removal* and a component that switches to a shorter
 * duration has not satisfied it.
 */
export const DURATIONS = {
  none: 0,
  hover: 120,
  overlay: 160,
  toast: 200,
} as const;

/** One step of the type scale. */
export interface TypeStep {
  readonly size: number;
  readonly line: number;
  readonly weight: number;
  readonly tracking: string;
}

/**
 * The type scale.
 *
 * `micro` tracks outwards because uppercase at eleven pixels closes up, and the
 * headings track inwards because large type at default tracking reads loose.
 */
export const TYPE_STEPS: Readonly<Record<string, TypeStep>> = {
  display: { size: 34, line: 1.15, weight: 680, tracking: '-0.03em' },
  title: { size: 26, line: 1.25, weight: 650, tracking: '-0.02em' },
  section: { size: 20, line: 1.3, weight: 650, tracking: '-0.01em' },
  strong: { size: 16, line: 1.45, weight: 600, tracking: '-0.01em' },
  body: { size: 14, line: 1.5, weight: 400, tracking: '0em' },
  small: { size: 13, line: 1.5, weight: 400, tracking: '0em' },
  meta: { size: 12, line: 1.45, weight: 400, tracking: '0em' },
  micro: { size: 11, line: 1.4, weight: 650, tracking: '0.06em' },
};

export type TypeName = keyof typeof TYPE_STEPS;

/** The step called `name`. */
export function typeStep(name: string): TypeStep {
  const step = TYPE_STEPS[name];
  if (step === undefined) {
    throw new Error(`${name} is not a step of the type scale`);
  }
  return step;
}

/**
 * The two elevations, per theme.
 *
 * Two and no more: depth beyond two levels reads as decoration. Dark needs
 * heavier shadows because there is less ground for them to fall on.
 */
export const SHADOWS: Readonly<Record<Theme, Readonly<Record<string, string>>>> = {
  light: {
    1: '0 1px 2px rgba(17, 22, 28, 0.06)',
    2: '0 2px 8px rgba(17, 22, 28, 0.08)',
  },
  dark: {
    1: '0 1px 2px rgba(0, 0, 0, 0.4)',
    2: '0 2px 10px rgba(0, 0, 0, 0.5)',
  },
};

/**
 * The two families, both from the operating system.
 *
 * No font is fetched from anywhere: Article X's "the operator owns their data"
 * is not compatible with a font host that learns every page an operator opens.
 * Identifiers are monospace always — a proportional font makes `local-lvm` and
 * `local-1vm` look alike, and those are compared character by character.
 */
export const FONT_STACKS = {
  sans: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  mono: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
} as const;

/**
 * The measure cap.
 *
 * Past this width a line of prose stops being scannable, and an operations
 * console is read by scanning rather than by reading.
 */
export const CONTENT_WIDTH = 1360;

/** The two densities, and the control height each gives a control. */
export const DENSITIES = ['comfortable', 'compact'] as const;

export type Density = (typeof DENSITIES)[number];

/**
 * What a density changes, which is spacing and control height and nothing else.
 *
 * Stated as a multiplier over the spacing scale plus an explicit control
 * height, so that "compact changed a colour" is a thing a test can rule out
 * rather than a thing a reviewer has to notice.
 */
export const DENSITY_METRICS: Readonly<
  Record<
    Density,
    { readonly gap: number; readonly control: number; readonly row: number }
  >
> = {
  comfortable: { gap: SPACING[4], control: 34, row: SPACING[3] },
  compact: { gap: SPACING[3], control: 28, row: SPACING[2] },
};
