import { message, type Locale, type MessageKey } from '@/i18n/messages';

/**
 * What a tool's worst-case side effect means, in words, at the point somebody
 * decides whether to approve it.
 *
 * The deployment sends these as slugs, and a proposal card once interpolated
 * the slug straight into the sentence beside it: a reviewer deciding whether
 * to approve something read `write_irreversible — This change is queued
 * rather than applied.`, a token where a sentence belonged. It is the same
 * defect `postures.ts` exists to end for an autonomy level, for the vocabulary
 * a tool's own side effect uses instead.
 *
 * **The slug is the fallback, not an error.** The five levels are declared in
 * `config/constants/security.py`, ordered least to most dangerous, and the
 * words chosen here preserve that order — a reader should be able to tell
 * `write_reversible` from `destructive` without knowing the enum. A
 * deployment that ever reports a level outside those five still has to render
 * something usable, so an unrecognised value shows as the slug itself, which
 * is exactly what every row did before this module existed, rather than an
 * empty value or a crash.
 */

/** The levels this console has words for. A deployment may declare others. */
const DESCRIBED: Readonly<Record<string, MessageKey>> = {
  read: 'sideEffect.level.read',
  read_sensitive: 'sideEffect.level.read_sensitive',
  write_reversible: 'sideEffect.level.write_reversible',
  write_irreversible: 'sideEffect.level.write_irreversible',
  destructive: 'sideEffect.level.destructive',
};

/** What `level` means, or the slug itself when this console has no words for it. */
export function sideEffectLabel(locale: Locale, level: string): string {
  const key = DESCRIBED[level];
  return key === undefined ? level : message(locale, key);
}

/** The short chip words for `level` — for a template that adds its own dash. */
const NAMED: Readonly<Record<string, MessageKey>> = {
  read: 'sideEffect.chip.read',
  read_sensitive: 'sideEffect.chip.read_sensitive',
  write_reversible: 'sideEffect.chip.write_reversible',
  write_irreversible: 'sideEffect.chip.write_irreversible',
  destructive: 'sideEffect.chip.destructive',
};

/** `level`'s short name, or the slug itself when this console has no words for it. */
export function sideEffectName(locale: Locale, level: string): string {
  const key = NAMED[level];
  return key === undefined ? level : message(locale, key);
}
