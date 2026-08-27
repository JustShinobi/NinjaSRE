import type { Locale } from '@/i18n/messages';
import { readFailure } from './failures';
import { text } from './read';
import { triggerLabel } from './run-trigger';

/**
 * The one place that decides what a run is called.
 *
 * Three surfaces used to compute this separately — the detail page's own
 * title, the browser tab, and the runs list column — and because each one
 * called `readFailure` on the raw summary and used its `title`, all three
 * printed the deployment's entire markdown report as the run's name. This
 * module is what the three now call instead, so they cannot diverge again.
 *
 * The order this resolves in is the order the requirements name: the
 * headline the record carries, when there is one; the translation this
 * console already has for a recognised failure, when the text gravado is
 * one; and the pairing of the trigger with the run's own short id, always
 * computable, when neither of the first two applies. The report — the
 * document itself — is never a candidate at any step.
 */

/**
 * Longest a run's displayed name may be.
 *
 * A presentation limit rather than a storage one: the backend's own
 * normalisation allows a longer sentence to be recorded, because a title, a
 * list column and a push notification all have less room than a database
 * column does. Declared here, not in the backend's constants, because it is
 * this console's own screens this number is sized for.
 */
export const MAX_RUN_NAME_LENGTH = 120;

/** Appended to a name cut at the limit — the visible sign that it was cut. */
const TRUNCATION_MARK = '…';

/** Any of these, as a literal character in visible text, is markdown syntax. */
const MARKDOWN_SYNTAX = /[#*`_~[\]|>]/g;

/** What the console shows in place of a run's name — never blank, never the report. */
export interface RunSubject {
  /** At most `MAX_RUN_NAME_LENGTH` characters, no line break, no markdown syntax. */
  readonly text: string;
  /** The same name, untruncated — for a tooltip over the clipped text. */
  readonly full: string;
  /** Whether `text` is a clipped version of `full`. */
  readonly truncated: boolean;
}

/** The first non-empty line of `raw`, with markdown syntax stripped and whitespace collapsed. */
function flattenHeadline(raw: string): string {
  const firstLine = raw.split(/\r?\n/).find((line) => line.trim() !== '') ?? '';
  return firstLine.replace(MARKDOWN_SYNTAX, '').replace(/\s+/g, ' ').trim();
}

/** `full`, cut at a word boundary at or before the display limit, with the mark appended. */
function clip(full: string): RunSubject {
  if (full.length <= MAX_RUN_NAME_LENGTH) {
    return { text: full, full, truncated: false };
  }
  const limit = MAX_RUN_NAME_LENGTH - TRUNCATION_MARK.length;
  const cut = full.slice(0, limit);
  const lastSpace = cut.lastIndexOf(' ');
  const atWordBoundary = lastSpace > 0 ? cut.slice(0, lastSpace) : cut;
  return { text: `${atWordBoundary}${TRUNCATION_MARK}`, full, truncated: true };
}

/** `<trigger label> · <first eight characters of the run id>` — always computable. */
function fallbackName(record: unknown, locale: Locale): string {
  const trigger = triggerLabel(locale, text(record, 'trigger'));
  const shortId = text(record, 'run_id').slice(0, 8);
  return `${trigger} · ${shortId}`;
}

/**
 * The name of the run `record` describes.
 *
 * `record` is read the same untyped way every surface reads an API body —
 * `headline`, `summary` and `trigger` are read as text, `run_id` as text —
 * so this accepts whatever `dataOf` already produced rather than asking
 * every caller to reshape it first.
 */
export function subjectOf(record: unknown, locale: Locale): RunSubject {
  const headline = flattenHeadline(text(record, 'headline'));
  if (headline !== '') {
    return clip(headline);
  }

  // No headline: the record predates it, or the model never produced one.
  // The only other candidate is the translation this console already has
  // for a recognised failure — never the raw summary itself, which for an
  // ordinary run is the whole markdown document.
  const said = readFailure(text(record, 'summary'), locale);
  if (said.known) {
    return clip(said.title);
  }

  return clip(fallbackName(record, locale));
}
