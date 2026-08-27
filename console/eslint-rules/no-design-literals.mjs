/**
 * The rule that keeps the design system a system.
 *
 * Everything else in this feature is a convention: a token table, a set of
 * scales, a component library. Conventions decay, and they decay in one
 * direction — somebody needs a colour that is nearly the accent, or four pixels
 * that are nearly a step, and writes the value. A year later the "system" is a
 * folder of components that agree about nothing.
 *
 * So the closed sets are enforced mechanically rather than in review. A colour
 * literal, a length that is not a step, a duration that is not on the motion
 * scale, and an arbitrary-value utility are all errors here. The token module
 * and the stylesheet renderer are exempt in the lint configuration, because
 * they are where the values are declared; every other file has to name a token.
 *
 * The same detection is used by `scripts/check-css-literals.mjs`, which covers
 * the stylesheets ESLint does not parse. One definition of "a literal", or the
 * two disagree and the gap is where the literals go.
 */

/** A colour written out rather than named. */
const COLOUR = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|color-mix|oklch)\s*\(/;

/**
 * A length or a duration written out rather than taken from a scale.
 *
 * Only ever applied to a *style* context — a bare value, a CSS declaration, or
 * a string inside a `style` attribute. Applied to prose it would reject "last
 * swept 41s ago", and a rule that fires on copy is a rule somebody switches
 * off, which costs more than the literals it was catching.
 */
const MEASURE = /(?<![\w.-])\d+(?:\.\d+)?(px|rem|em|ms|s)(?![\w-])/;

/** A string that is nothing but a measurement, which is always a style value. */
const BARE_MEASURE = /^\s*-?\d+(?:\.\d+)?(?:px|rem|em|ms|s)\s*$/;

/** An arbitrary-value utility: the escape hatch the scales exist to close. */
const ARBITRARY = /(?:^|[\s:])-?[a-z][a-z0-9-]*-\[[^\]]*\]/;

/**
 * Utilities whose numeric step must be on the spacing scale.
 *
 * Listed rather than inferred: `z-10` and `grid-cols-3` also end in a number
 * and have nothing to do with spacing, and a rule that guessed would be a rule
 * people turn off.
 *
 * The width, height and translate families were missing from this list, and
 * that is how `max-h-96`, `max-h-64`, `h-44` and `w-0.5` shipped. They took
 * their length from Tailwind's own `--spacing` base — a scale nobody here
 * declared, which the stylesheet's comment and the documentation both insisted
 * was absent. The stylesheet now closes that base, so those four compile to
 * nothing; being listed here is what turns "no CSS, no complaint" into an
 * error naming the file and the utility. A width off the scale needs to be
 * caught where it is written, not inferred from a layout that looks nearly
 * right.
 */
const SPACED =
  /(?:^|\s)-?(p|px|py|pt|pr|pb|pl|m|mx|my|mt|mr|mb|ml|gap|gap-x|gap-y|space-x|space-y|inset|inset-x|inset-y|top|right|bottom|left|start|end|size|basis|w|h|min-w|min-h|max-w|max-h|translate|translate-x|translate-y)-(\d+(?:\.\d+)?)(?![\w-])/g;

/**
 * The seven steps, the three density aliases, and zero.
 *
 * Zero is not an eighth step. It is the removal of a step — `border-t-0` takes
 * an edge off, `left-0` pins to an edge — and a scale that could not express
 * "none" would be worked around with an arbitrary value, which is worse.
 */
const SPACING_STEPS = new Set([
  '0',
  '1',
  '2',
  '3',
  '4',
  '5',
  '6',
  '7',
  'density',
  'row',
  'control',
]);

/** Radius utilities. `full` is a shape rather than a step, so it is allowed. */
const ROUNDED = /(?:^|\s)rounded(?:-(?:t|r|b|l|tl|tr|br|bl))?-([a-z0-9]+)(?![\w-])/g;
const RADIUS_STEPS = new Set(['1', '2', '3', '4', 'full']);

/** Type utilities. The scale is named, so a t-shirt size is off it. */
const TEXT_SIZE = /(?:^|\s)text-(xs|sm|base|lg|\d?xl|\d+)(?![\w-])/;

/** Motion utilities. Durations come from the scale through `motion-*`. */
const DURATION_CLASS = /(?:^|\s)(?:duration|delay)-\d+(?![\w-])/;

/** Border widths come from the `edge` utilities rather than from a number. */
const BORDER_WIDTH = /(?:^|\s)border(?:-[xytrbl])?-([1-9]\d*)(?![\w-])/;

/**
 * Every finding in one string, as `[messageId, offendingText]` pairs.
 *
 * `styled` says whether the string is a style value — a CSS declaration, or a
 * string handed to a `style` attribute. Only then is a measurement a finding,
 * because only then is it a design decision rather than a sentence.
 *
 * @param {string} text
 * @param {{ styled?: boolean }} [where]
 * @returns {[string, string][]}
 */
export function findings(text, where = {}) {
  const found = [];
  const colour = COLOUR.exec(text);
  if (colour !== null) found.push(['colour', colour[0]]);

  const measure = MEASURE.exec(text);
  if (measure !== null && (where.styled === true || BARE_MEASURE.test(text))) {
    found.push([
      measure[1] === 'ms' || measure[1] === 's' ? 'duration' : 'length',
      measure[0],
    ]);
  }

  const arbitrary = ARBITRARY.exec(text);
  if (arbitrary !== null) found.push(['arbitrary', arbitrary[0].trim()]);

  for (const match of text.matchAll(SPACED)) {
    if (!SPACING_STEPS.has(match[2])) found.push(['offScale', match[0].trim()]);
  }
  for (const match of text.matchAll(ROUNDED)) {
    if (!RADIUS_STEPS.has(match[1])) found.push(['offScale', match[0].trim()]);
  }

  const size = TEXT_SIZE.exec(text);
  if (size !== null) found.push(['typeStep', size[0].trim()]);

  const duration = DURATION_CLASS.exec(text);
  if (duration !== null) found.push(['duration', duration[0].trim()]);

  const border = BORDER_WIDTH.exec(text);
  if (border !== null) found.push(['offScale', border[0].trim()]);

  return found;
}

/** @type {import('eslint').Rule.RuleModule} */
export const noDesignLiterals = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Reject colour, length and duration literals, and utilities off the declared scales.',
    },
    schema: [],
    messages: {
      colour:
        'A colour written out ({{value}}). Colour is declared by role in src/design/tokens.ts and reaches a component as a utility — a literal here is a colour no contrast test measured.',
      length:
        'A length written out ({{value}}). Use a step of the spacing, radius or border scale.',
      duration:
        'A duration written out ({{value}}). Use motion-hover, motion-overlay or motion-toast, so reduced motion can remove it.',
      arbitrary:
        'An arbitrary-value utility ({{value}}). Every value comes from a closed set; an arbitrary one is the set being reopened.',
      offScale: '{{value}} is not on the declared scale.',
      typeStep:
        '{{value}} is not a step of the type scale. The steps are display, title, section, strong, body, small, meta and micro.',
    },
  },
  create(/** @type {import('eslint').Rule.RuleContext} */ context) {
    /**
     * Whether `node` sits inside something that becomes CSS.
     *
     * @param {import('estree').Node} node
     * @returns {boolean}
     */
    function inAStyleContext(node) {
      return context.sourceCode
        .getAncestors(node)
        .some(
          (ancestor) =>
            ancestor.type === 'JSXAttribute' &&
            ancestor.name.type === 'JSXIdentifier' &&
            ancestor.name.name === 'style',
        );
    }

    /**
     * Report every finding in one node's text.
     *
     * @param {import('estree').Node} node
     * @param {string} text
     * @returns {void}
     */
    function inspect(node, text) {
      for (const [messageId, value] of findings(text, {
        styled: inAStyleContext(node),
      })) {
        context.report({ node, messageId, data: { value } });
      }
    }

    return {
      Literal(node) {
        if (typeof node.value !== 'string') return;
        inspect(node, node.value);
      },
      TemplateElement(node) {
        inspect(node, node.value.raw);
      },
      JSXText(node) {
        // Prose is not a stylesheet, but a hex colour in copy is still a colour
        // nobody measured — and it is how a "temporary" swatch becomes shipped.
        const colour = COLOUR.exec(node.value);
        if (colour !== null) {
          context.report({ node, messageId: 'colour', data: { value: colour[0] } });
        }
      },
    };
  },
};

/** The plugin the lint configuration registers. */
const plugin = { rules: { 'no-design-literals': noDesignLiterals } };

export default plugin;
