/**
 * Looking a string up, and what happens when a locale does not have one.
 *
 * The fallback is **per key**. A locale missing one string keeps every other
 * string it has; only the missing one arrives in English. Falling back per
 * *locale* would be worse than the gap it patches — a page that silently
 * switches language mid-session reads as a broken console rather than as an
 * untranslated sentence, and nobody reports it because nobody can describe it.
 *
 * A key no catalogue declares throws. Rendering the key instead is how
 * `nav.dashbaord` ships: it looks like a word in a language the reviewer does
 * not speak, and every screenshot review passes straight over it.
 */

import { EN, type MessageKey } from './en';
import { PT_BR } from './pt-BR';

/** The locales this console carries. */
export const LOCALES = ['en', 'pt-BR'] as const;

export type Locale = (typeof LOCALES)[number];

/** The source locale, and what every per-key fallback resolves to. */
export const DEFAULT_LOCALE: Locale = 'en';

/** One locale's strings. Partial for every locale but the source. */
export type Catalogue = Partial<Record<MessageKey, string>>;

export const CATALOGUES: Readonly<Record<Locale, Catalogue>> = {
  en: EN,
  'pt-BR': PT_BR,
};

/** What a message may be given to substitute into its placeholders. */
export type Params = Readonly<Record<string, string | number>>;

/** Every key `locale` does not carry, in the order the source declares them. */
export function missingKeys(locale: Locale): readonly MessageKey[] {
  const catalogue = CATALOGUES[locale];
  return (Object.keys(EN) as MessageKey[]).filter(
    (key) => catalogue[key] === undefined || catalogue[key] === '',
  );
}

/**
 * Substitute `{name}` placeholders.
 *
 * A placeholder with no parameter is left as it was written. The alternative is
 * a blank, and a blank is invisible: it survives review, survives a screenshot,
 * and is discovered by the person it was supposed to name.
 */
function interpolate(template: string, params: Params): string {
  return template.replace(/\{([a-z][a-z0-9]*)\}/gi, (whole, name: string) => {
    const value = params[name];
    return value === undefined ? whole : String(value);
  });
}

/**
 * The string `key` has in `locale`, with `params` substituted.
 *
 * `override` exists for the tests that prove the fallback: handing in a partial
 * catalogue is the only honest way to show what a missing key does, and adding
 * a deliberately broken locale to the shipped set to test it would be worse.
 */
export function message(
  locale: Locale,
  key: MessageKey,
  params: Params = {},
  override?: Catalogue,
): string {
  const catalogue = override ?? CATALOGUES[locale];
  // Read through a total-looking view rather than through `typeof EN`: the
  // compiler believes every key of `EN` exists, and it is right about the keys
  // it knows. The one this guards against is the key a caller asserted into
  // existence — a value read from a URL, a fixture, or a locale from a build one
  // version ahead — and against those the compiler has nothing to say.
  const source: Readonly<Record<string, string | undefined>> = EN;
  const found = catalogue[key] ?? source[key];
  if (found === undefined) {
    throw new Error(`${key} is not in the message catalogue`);
  }
  return interpolate(found, params);
}

/** Whether `value` names a locale this console carries. */
export function isLocale(value: string | null | undefined): value is Locale {
  return (
    value !== null &&
    value !== undefined &&
    (LOCALES as readonly string[]).includes(value)
  );
}

/**
 * The locale to use, from an `Accept-Language` header or a stored choice.
 *
 * Matched case-insensitively, exact tag first: a header naming `pt-BR` gets
 * `pt-BR` rather than whatever else shares its language. Failing that, matched
 * by *language* — the part before the hyphen — against every tag offered, in
 * the order the header gives them: `pt` and `pt-PT` both fall through to
 * `pt-BR`, because it is the only Portuguese this console carries and refusing
 * a reader their language over a regional letter they did not choose is a
 * worse guess than serving Brazilian spelling to a Portuguese reader. The
 * exact match still runs first and wins, so the day a second Portuguese
 * catalogue exists a header naming it exactly is never overridden by this
 * fallback. A tag nothing matches, by either rule, falls back to English,
 * which is the source locale rather than a preference.
 */
export function resolveLocale(header: string | null | undefined): Locale {
  if (header === null || header === undefined) {
    return DEFAULT_LOCALE;
  }
  const tags = header
    .split(',')
    .map((part) => part.split(';')[0]?.trim().toLowerCase() ?? '')
    .filter((tag) => tag !== '');

  // One pass, most preferred tag first: a tag's own exact match wins over its
  // own language fallback, and either wins over anything a later, less
  // preferred tag could offer — an exact match three tags down must not beat
  // a language fallback on the tag actually listed first.
  for (const tag of tags) {
    const exact = LOCALES.find((locale) => locale.toLowerCase() === tag);
    if (exact !== undefined) {
      return exact;
    }
    const language = tag.split('-')[0] ?? '';
    if (language === '') continue;
    const byLanguage = LOCALES.find(
      (locale) => (locale.toLowerCase().split('-')[0] ?? '') === language,
    );
    if (byLanguage !== undefined) {
      return byLanguage;
    }
  }
  return DEFAULT_LOCALE;
}

export type { MessageKey };
