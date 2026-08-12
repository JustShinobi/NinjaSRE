/**
 * The WCAG 2.1 relative-luminance and contrast arithmetic.
 *
 * A port rather than an invention: this repository already computes these
 * numbers, and its test suite asserts them against the palette it ships. Two
 * implementations that disagree in the fourth decimal place eventually disagree
 * about whether a pair passes, so the port is held to the Python one's output
 * rather than to the specification's prose.
 *
 * Nothing here reads a token. It is arithmetic over colours, which is what lets
 * the token table import it without a cycle and lets the test import both.
 */

/** The ratio a foreground has to reach against the background it is read on. */
export const BODY_MINIMUM = 4.5;

/**
 * The ratio a boundary has to reach.
 *
 * Lower than body text because WCAG 1.4.11 asks a viewer to *find* a control
 * edge rather than to read it. Decorative separators — a table rule, a card
 * edge — are outside the requirement entirely, which is why this system carries
 * two border tokens rather than one.
 */
export const BOUNDARY_MINIMUM = 3;

/**
 * The ratio a hover has to reach against the ground it covers.
 *
 * WCAG says nothing about this — it is a change of state on a surface, not a
 * foreground anybody reads — so the number is ours and the reasoning has to
 * stand on its own. Below roughly 1.06 a ground-on-ground change is not
 * perceivable on an ordinary display at ordinary brightness; 1.1 leaves room
 * for a dim panel and a viewer who is not looking for it, and is still far
 * below anything that would read as a selection.
 */
export const HOVER_MINIMUM = 1.1;

/** The three 8-bit channels of a `#rrggbb` colour. */
function channels(colour: string): [number, number, number] {
  const value = colour.startsWith('#') ? colour.slice(1) : colour;
  if (!/^[0-9a-fA-F]{6}$/.test(value)) {
    throw new Error(`${colour} is not a #rrggbb colour`);
  }
  return [
    Number.parseInt(value.slice(0, 2), 16),
    Number.parseInt(value.slice(2, 4), 16),
    Number.parseInt(value.slice(4, 6), 16),
  ];
}

/** One 8-bit channel converted to linear light, per WCAG 2.1. */
function linear(channel: number): number {
  const proportion = channel / 255;
  return proportion <= 0.04045
    ? proportion / 12.92
    : ((proportion + 0.055) / 1.055) ** 2.4;
}

/** The WCAG relative luminance of a `#rrggbb` colour, 0.0 to 1.0. */
export function relativeLuminance(colour: string): number {
  const [red, green, blue] = channels(colour);
  return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue);
}

/** The WCAG contrast ratio between two colours, 1.0 to 21.0. */
export function contrastRatio(foreground: string, background: string): number {
  const first = relativeLuminance(foreground);
  const second = relativeLuminance(background);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}
