import { message, type Locale, type MessageKey } from '@/i18n/messages';

/**
 * What an autonomy level permits, in words, at the point somebody chooses it.
 *
 * The deployment sends these as slugs — `propose_only`, `act_on_low_risk` — and
 * every control that offered them offered the slug: a `<Select>` whose most
 * consequential option was indistinguishable from its least, and a badge that
 * printed an identifier where a state should be. This is the most consequential
 * decision in the product, and a posture an operator misreads is a posture they
 * did not choose.
 *
 * **The slug is the fallback, not an error.** The levels come from the
 * deployment rather than from this console, so a deployment that declares a
 * fifth one must still render a usable control — it shows the slug, which is
 * exactly what every control did before, rather than an empty option or a
 * crash. A level added here later upgrades it in place.
 */

/** The levels this console has words for. A deployment may declare others. */
const DESCRIBED: Readonly<Record<string, MessageKey>> = {
  propose_only: 'autonomy.level.propose_only',
  act_on_low_risk: 'autonomy.level.act_on_low_risk',
  act_and_report: 'autonomy.level.act_and_report',
  act_silently: 'autonomy.level.act_silently',
};

/** What `level` permits, or the slug itself when this console has no words for it. */
export function postureLabel(locale: Locale, level: string): string {
  const key = DESCRIBED[level];
  return key === undefined ? level : message(locale, key);
}

/**
 * The short name for each level this console has words for — what a
 * subtitle or a heading states beside a node's own name, in a sentence of
 * its own. `DESCRIBED`'s text is written for the `<Select>` option it is
 * and carries its own full stop; interpolating that whole sentence into
 * another one produces one sentence wearing the punctuation of two.
 */
const NAMED: Readonly<Record<string, MessageKey>> = {
  propose_only: 'autonomy.level.propose_only.short',
  act_on_low_risk: 'autonomy.level.act_on_low_risk.short',
  act_and_report: 'autonomy.level.act_and_report.short',
  act_silently: 'autonomy.level.act_silently.short',
};

/** `level`'s short name, or the slug itself when this console has no word for it. */
export function postureName(locale: Locale, level: string): string {
  const key = NAMED[level];
  return key === undefined ? level : message(locale, key);
}

/**
 * `levels` as a lookup a client editor can hold, keyed by the deployment's slug.
 *
 * The editors are client components with no locale of their own, so the screen
 * that has one resolves the words and hands them over. A record rather than a
 * function because it crosses into a client component, where a closure would be
 * a serialisation boundary this does not need.
 */
export function postureLabels(
  locale: Locale,
  levels: readonly string[],
): Readonly<Record<string, string>> {
  return Object.fromEntries(
    levels.map((level) => [level, postureLabel(locale, level)]),
  );
}
