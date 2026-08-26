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
  'hover',
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
  sunken: '#f2f5f4',
  raised: '#ffffff',
  hover: '#e9eeec',
  text: '#1a2420',
  muted: '#4c5a55',
  accent: '#0a7452',
  'on-accent': '#ffffff',
  'accent-bg': '#e2f2ec',
  border: '#d8e0dd',
  'border-strong': '#6d7c76',
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
  neutral: '#4c5a55',
  'on-neutral': '#ffffff',
  'neutral-bg': '#f2f5f4',
};

/** The dark theme. The same names, and the same geometry, at different values. */
const DARK: Readonly<Record<ColourRole, string>> = {
  surface: '#141b18',
  sunken: '#0d1311',
  raised: '#1a2320',
  hover: '#222d29',
  text: '#e4ebe8',
  muted: '#a3b2ac',
  accent: '#3ad195',
  'on-accent': '#062018',
  'accent-bg': '#12271f',
  border: '#24302b',
  'border-strong': '#8b9a94',
  success: '#3ad195',
  'on-success': '#062018',
  'success-bg': '#12271f',
  warning: '#e0a84e',
  'on-warning': '#241a08',
  'warning-bg': '#2a2214',
  danger: '#ef7070',
  'on-danger': '#2a0d0d',
  'danger-bg': '#2a1616',
  info: '#6cb8e0',
  'on-info': '#08202b',
  'info-bg': '#12242c',
  neutral: '#a3b2ac',
  'on-neutral': '#0d1311',
  'neutral-bg': '#0d1311',
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

/**
 * The grounds a viewer reads text on.
 *
 * `hover` is one of them. A hovered row still carries its own text, its state
 * colours and its focus ring, so a hover ground that was only checked for being
 * *visible* could still be one nobody can read once the pointer is on it.
 */
const GROUNDS = ['surface', 'sunken', 'raised', 'hover'] as const;

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
 * Every hover against the ground it covers, which has to reach `HOVER_MINIMUM`.
 *
 * Two grounds rather than three: a hoverable surface in this console sits on
 * `surface` (navigation entries, table rows, the tree, secondary buttons) or on
 * `raised` (the attention list, the notification centre). Nothing hoverable
 * sits on `sunken` — that is the page ground, behind the panels — so a pair for
 * it would be a number nobody could act on.
 */
export function hoverPairs(theme: Theme): readonly Pair[] {
  const at = (role: ColourRole): string => colour(theme, role);
  return [
    {
      what: 'hover over surface',
      foreground: at('hover'),
      background: at('surface'),
    },
    {
      what: 'hover over raised',
      foreground: at('hover'),
      background: at('raised'),
    },
  ];
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
  /**
   * A mark that says the thing behind it is happening now.
   *
   * An order of magnitude slower than every other step, and deliberately so:
   * the other four are a response to something a person just did, and this one
   * is not a response at all. At the toast's two hundred milliseconds it reads
   * as an alarm blinking; at this it reads as breathing, which is the whole
   * difference between "look at me" and "I am still here".
   */
  pulse: 2400,
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
 * `micro` is the label step: column headers, section headings, the words above
 * a group of navigation entries. It used to be eleven pixels of capitals
 * tracked out to 0.06em, which is a decade-old administrative-console idiom
 * and a measurable cost — a reader recognises a word by its silhouette, and
 * capitals flatten every word to the same rectangle. Twelve pixels, sentence
 * case, no tracking: the label reads as a label because it is smaller and
 * quieter than what it labels, not because it is shouting.
 *
 * The headings still track inwards, because large type at default tracking
 * reads loose.
 */
export const TYPE_STEPS: Readonly<Record<string, TypeStep>> = {
  display: { size: 34, line: 1.15, weight: 680, tracking: '-0.03em' },
  title: { size: 26, line: 1.25, weight: 650, tracking: '-0.02em' },
  section: { size: 20, line: 1.3, weight: 650, tracking: '-0.01em' },
  strong: { size: 16, line: 1.45, weight: 600, tracking: '-0.01em' },
  body: { size: 14, line: 1.5, weight: 400, tracking: '0em' },
  small: { size: 13, line: 1.5, weight: 400, tracking: '0em' },
  meta: { size: 12, line: 1.45, weight: 400, tracking: '0em' },
  micro: { size: 12, line: 1.4, weight: 600, tracking: '0em' },
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

/**
 * The application shell's two fixed measurements.
 *
 * Neither is on the spacing scale and neither should be. A sidebar is as wide as
 * its longest label plus its icon plus its gutters, and a utility bar is as tall
 * as one control with air around it; both are measured from the design rather
 * than derived from a step. They are tokens so that a component names them
 * instead of writing them, which is the same rule everything else here follows.
 */
export const SHELL = {
  sidebar: 236,
  topbar: 52,
} as const;

/**
 * How wide a list column is, by what it holds.
 *
 * A table of rows lays out fixed, so a column with no declared width takes an
 * equal share of whatever is going. On a Full HD screen that gave a status
 * badge and a duration four hundred pixels each and clipped the one column
 * that says what the row is about — so every row on the screen read
 * "Proxmox node pve01 backup synchron…" and the reader had to open each one to
 * tell them apart.
 *
 * Named by content rather than by number, and measured from the widest thing
 * each actually holds: a status badge, a timestamp phrased as "29 minutes
 * ago", a short opaque identifier. The column carrying the row's subject
 * declares nothing and takes the rest, which is the whole point of the scale.
 *
 * Not on the spacing scale, for the reason `SHELL` is not: a column is as wide
 * as its content, which is a measurement rather than a step.
 */
export const COLUMN_WIDTHS = {
  /** A severity or trigger word: "critical", "Alert". */
  word: 112,
  /** A status badge with its shape and its label: "COMPLETED". */
  badge: 144,
  /** A short opaque identifier, monospaced: "#8711ce98". */
  identifier: 144,
  /** A relative instant: "29 minutes ago". */
  instant: 160,
  /** A number and its unit, right-aligned: "18s", "36,842". */
  measure: 112,
} as const;

/** Which content a column holds, and therefore how wide it is. */
export type ColumnWidth = keyof typeof COLUMN_WIDTHS;

/**
 * The width below which the sidebar becomes a drawer.
 *
 * Declared here and used by the browser suite, so "the documented breakpoint" is
 * a number two things read rather than a number in a sentence.
 */
export const SIDEBAR_BREAKPOINT = 768;

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
