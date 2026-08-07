/**
 * "Without a layout shift between states", made checkable.
 *
 * A jsdom test cannot measure a box — nothing lays anything out. What it *can*
 * do is read the classes that would decide the box, and that turns out to be
 * the stronger assertion anyway: a component whose padding class changes on
 * hover has a layout shift on every machine, and one whose colour class changes
 * has none on any. So the geometry classes are extracted and required to be
 * equal across every state a component declares, while the rest are free to
 * differ — which is exactly the property FR-008 asks for.
 *
 * The same extraction answers the theme question. Themes swap token *values*,
 * never utilities, so two renders under different themes have identical classes
 * altogether; SC-006 is asserted at the pixel level in the visual suite and at
 * this level as the reason that comparison can be expected to hold.
 */

/** Utility prefixes that decide where something is and how big it is. */
const GEOMETRY = [
  'p',
  'px',
  'py',
  'pt',
  'pr',
  'pb',
  'pl',
  'm',
  'mx',
  'my',
  'mt',
  'mr',
  'mb',
  'ml',
  'gap',
  'gap-x',
  'gap-y',
  'w',
  'h',
  'min-w',
  'min-h',
  'max-w',
  'max-h',
  'size',
  'leading',
  'tracking',
  'edge',
  'rounded',
  'grid-cols',
  'col-span',
  'items',
  'justify',
  'icon',
  'inset',
  'top',
  'right',
  'bottom',
  'left',
];

/** Utilities that are geometry on their own rather than a prefixed family. */
const WHOLE = new Set([
  'flex',
  'inline-flex',
  'grid',
  'inline-grid',
  'block',
  'inline-block',
  'hidden',
  'absolute',
  'relative',
  'fixed',
  'sticky',
  'font-sans',
  'font-mono',
  'truncate',
  'edge',
]);

/**
 * The type steps.
 *
 * `text-` is the one prefix that is both: `text-body` is a size, a line height,
 * a weight and a tracking, while `text-danger` is a colour. Treating the whole
 * family as geometry would make every state that changes colour look like a
 * layout shift, and treating none of it as geometry would miss a real one.
 */
const TYPE_STEPS = new Set([
  'text-display',
  'text-title',
  'text-section',
  'text-strong',
  'text-body',
  'text-small',
  'text-meta',
  'text-micro',
]);

/** Whether `token` is a class that decides geometry rather than appearance. */
function isGeometry(token: string): boolean {
  const bare = token.includes(':') ? (token.split(':').pop() ?? token) : token;
  const name = bare.startsWith('-') ? bare.slice(1) : bare;
  if (WHOLE.has(name) || TYPE_STEPS.has(name)) return true;
  return GEOMETRY.some((prefix) => name === prefix || name.startsWith(`${prefix}-`));
}

/** The geometry classes on `element`, sorted so ordering is not a difference. */
export function geometryClasses(element: Element): readonly string[] {
  return element.className
    .split(/\s+/)
    .filter((token) => token !== '' && isGeometry(token))
    .sort();
}
