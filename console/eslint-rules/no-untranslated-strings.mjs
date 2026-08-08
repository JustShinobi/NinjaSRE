/**
 * The rule that keeps the catalogue the only place a sentence is written.
 *
 * A completeness test can only compare the locales it is given. It has nothing
 * at all to say about a sentence that never reached a catalogue — and that is
 * the sentence that ships untranslated, because it looks correct in the language
 * the reviewer reads.
 *
 * So the check runs at the other end. Text written into a component, and text
 * handed to an attribute a person will hear or read, are both errors. What is
 * left is `message(locale, key)`, which the completeness test can see.
 *
 * Deliberately narrow. It does not police every string — a class name, a test
 * identifier, an href and a status the API sent are all strings, and none of
 * them is a sentence. It polices literal text in the tree and the handful of
 * attributes that carry a sentence to a reader.
 */

/**
 * The attributes whose value a person reads or hears.
 *
 * Listed rather than inferred. `className` and `href` are strings too, and a
 * rule that guessed would be a rule somebody turns off.
 */
const SPOKEN = new Set([
  'alt',
  'aria-description',
  'aria-label',
  'aria-placeholder',
  'aria-roledescription',
  'aria-valuetext',
  'heading',
  'label',
  'placeholder',
  'title',
]);

/** Text with no letter in it is punctuation, a separator, or whitespace. */
const HAS_LETTER = /\p{L}/u;

/**
 * Text that is a single word of markup rather than a sentence.
 *
 * A one-character glyph — an arrow, a middot, a bullet — is a shape and not a
 * string somebody translates. Anything longer has to come from the catalogue.
 */
function isGlyph(text) {
  return text.trim().length <= 1;
}

/** @type {import('eslint').Rule.RuleModule} */
export const noUntranslatedStrings = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Reject literal text in a component and literal sentences in the attributes a person reads.',
    },
    schema: [],
    messages: {
      text: 'Literal text in a component ({{value}}). Every user-visible string comes from the catalogue, through message(locale, key) — a literal here is a string no completeness test can see.',
      attribute:
        'A literal {{name}} ({{value}}). This is read aloud or shown; take it from the catalogue.',
    },
  },
  create(context) {
    return {
      JSXText(node) {
        const text = node.value.trim();
        if (text === '' || !HAS_LETTER.test(text) || isGlyph(text)) return;
        context.report({ node, messageId: 'text', data: { value: text.slice(0, 40) } });
      },
      JSXAttribute(node) {
        const name =
          node.name.type === 'JSXIdentifier'
            ? node.name.name
            : `${node.name.namespace.name}:${node.name.name.name}`;
        if (!SPOKEN.has(name)) return;
        const value = node.value;
        if (value === null || value.type !== 'Literal') return;
        if (typeof value.value !== 'string') return;
        const text = value.value.trim();
        if (text === '' || !HAS_LETTER.test(text) || isGlyph(text)) return;
        context.report({
          node: value,
          messageId: 'attribute',
          data: { name, value: text.slice(0, 40) },
        });
      },
    };
  },
};

/** The plugin the lint configuration registers. */
const plugin = { rules: { 'no-untranslated-strings': noUntranslatedStrings } };

export default plugin;
