/**
 * Types for the design-literal rule, so the typed suite can reach it.
 *
 * The rule is authored in JavaScript because ESLint loads its configuration as
 * JavaScript, and `allowJs` is off here on purpose — a TypeScript project that
 * silently accepts untyped JavaScript is one that grows some. This declaration
 * is the narrow bridge: it exposes the one function a test needs, so the rule's
 * scales are asserted by a test rather than only by the tree happening to pass.
 */

/** One ESLint message id, and the text that triggered it. */
export type Finding = [messageId: string, value: string];

/**
 * Every finding in one string.
 *
 * `styled` says whether the string is a style value — a CSS declaration, or a
 * string handed to a `style` attribute — because only then is a measurement a
 * design decision rather than a sentence.
 */
export declare function findings(
  text: string,
  where?: { styled?: boolean },
): readonly Finding[];
