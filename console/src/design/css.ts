/**
 * The token table, rendered as the custom properties a browser reads.
 *
 * This is the second of the table's three consumers. It exists as a function
 * rather than as a stylesheet because a stylesheet is a second copy: somebody
 * edits the table, forgets the sheet, and the two disagree in a way that only
 * shows up as a colour nobody chose. Rendering it means there is nothing to
 * forget.
 *
 * The third consumer is the Tailwind theme in `app/globals.css`, which cannot
 * be generated — Tailwind reads CSS at build time, before any of this runs. It
 * is held to the table by `tests/unit/design/css.test.ts` instead, in both
 * directions: a utility pointing at a token nobody declares fails, and a token
 * no utility exposes fails too, because a token a component cannot reach is a
 * token somebody will work around with a literal.
 */

import {
  COLUMN_WIDTHS,
  BORDER_WIDTHS,
  colour,
  CONTENT_WIDTH,
  COLOUR_ROLES,
  DENSITY_METRICS,
  DURATIONS,
  FONT_STACKS,
  RADII,
  READING_WIDTH,
  SCROLL_HEIGHTS,
  SHADOWS,
  SHELL,
  SPACING,
  type Theme,
  TYPE_STEPS,
} from './tokens';

/**
 * Icon sizes, in pixels.
 *
 * Four, matched to where an icon appears rather than to a doubling scale: an
 * icon beside body text, an icon in the navigation, an icon in a page header,
 * an icon in an empty state.
 */
export const ICON_SIZES = {
  inline: 13,
  nav: 15,
  head: 19,
  empty: 20,
} as const;

/** One custom property, on its own line so a colour can never share one. */
function declaration(name: string, value: string): string {
  return `  --${name}: ${value};`;
}

/** The scales, which do not change with the theme. */
function scaleDeclarations(): readonly string[] {
  const lines: string[] = [];
  for (const [step, value] of Object.entries(SPACING)) {
    lines.push(declaration(`space-${step}`, `${String(value)}px`));
  }
  for (const [step, value] of Object.entries(RADII)) {
    lines.push(declaration(`corner-${step}`, `${String(value)}px`));
  }
  for (const [step, value] of Object.entries(BORDER_WIDTHS)) {
    lines.push(declaration(`stroke-${step}`, `${String(value)}px`));
  }
  for (const [name, value] of Object.entries(DURATIONS)) {
    lines.push(declaration(`dur-${name}`, `${String(value)}ms`));
  }
  for (const [name, value] of Object.entries(ICON_SIZES)) {
    lines.push(declaration(`icon-${name}`, `${String(value)}px`));
  }
  for (const [name, step] of Object.entries(TYPE_STEPS)) {
    lines.push(declaration(`size-${name}`, `${String(step.size)}px`));
    lines.push(declaration(`line-${name}`, String(step.line)));
    lines.push(declaration(`weight-${name}`, String(step.weight)));
    lines.push(declaration(`track-${name}`, step.tracking));
  }
  for (const [name, value] of Object.entries(SHELL)) {
    lines.push(declaration(`shell-${name}`, `${String(value)}px`));
  }
  for (const [name, value] of Object.entries(COLUMN_WIDTHS)) {
    lines.push(declaration(`column-${name}`, `${String(value)}px`));
  }
  for (const [name, value] of Object.entries(SCROLL_HEIGHTS)) {
    lines.push(declaration(`scroll-${name}`, `${String(value)}px`));
  }
  lines.push(declaration('width-page', `${String(CONTENT_WIDTH)}px`));
  lines.push(declaration('width-reading', `${String(READING_WIDTH)}px`));
  lines.push(declaration('family-sans', FONT_STACKS.sans));
  lines.push(declaration('family-mono', FONT_STACKS.mono));
  return lines;
}

/** One theme's colours and elevations. */
function themeDeclarations(theme: Theme): readonly string[] {
  const lines = COLOUR_ROLES.map((role) => declaration(role, colour(theme, role)));
  for (const [step, value] of Object.entries(SHADOWS[theme])) {
    lines.push(declaration(`elev-${step}`, value));
  }
  return lines;
}

/** The density metrics, which are the only thing a density changes. */
function densityDeclarations(density: keyof typeof DENSITY_METRICS): readonly string[] {
  const metrics = DENSITY_METRICS[density];
  return [
    declaration('density-gap', `${String(metrics.gap)}px`),
    declaration('density-control', `${String(metrics.control)}px`),
    declaration('density-row', `${String(metrics.row)}px`),
  ];
}

function block(selector: string, lines: readonly string[]): string {
  return `${selector} {\n${lines.join('\n')}\n}`;
}

/**
 * Every custom property the stylesheet declares for `theme`.
 *
 * The scales are included even though they do not vary: a consumer asking
 * "what is declared" wants the whole vocabulary, and comparing the two themes'
 * answers is what proves neither theme has a name the other lacks.
 */
export function declaredNames(theme: Theme): ReadonlySet<string> {
  const lines = [
    ...scaleDeclarations(),
    ...themeDeclarations(theme),
    ...densityDeclarations('comfortable'),
  ];
  return new Set(lines.map((line) => line.trim().split(':')[0]?.slice(2) ?? ''));
}

/** Every token `css` reads through `var(--…)`. */
export function referencedNames(css: string): ReadonlySet<string> {
  const found = new Set<string>();
  for (const match of css.matchAll(/var\(\s*--([a-z0-9-]+)/gi)) {
    const name = match[1];
    if (name !== undefined) found.add(name);
  }
  return found;
}

/**
 * The whole runtime stylesheet: scales, both themes, and the density switch.
 *
 * The ordering is what makes the theme behave. The media query is guarded with
 * `:not([data-theme="light"])` so that a viewer who chose light keeps it on a
 * dark operating system — without the guard the query would win, and the
 * override would work in one direction only. The two explicit blocks come last
 * so an attribute always beats the system.
 */
export function tokenStylesheet(): string {
  return [
    block(':root', scaleDeclarations()),
    block(':root', themeDeclarations('light')),
    `@media (prefers-color-scheme: dark) {\n${block(
      ':root:not([data-theme="light"])',
      themeDeclarations('dark'),
    )}\n}`,
    block('[data-theme="dark"]', themeDeclarations('dark')),
    block('[data-theme="light"]', themeDeclarations('light')),
    block(':root, [data-density="comfortable"]', densityDeclarations('comfortable')),
    block('[data-density="compact"]', densityDeclarations('compact')),
  ].join('\n');
}
