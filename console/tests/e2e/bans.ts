import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * The five detectors the "Now" transversal rules are built on.
 *
 * Each one is a pure function — text (and, where the rule is inherently about
 * two facts on one page, a second piece of text or a flag) goes in, a
 * violation or `null` comes out. Nothing here touches a page. That split is
 * deliberate: `transversal-rules.spec.ts` is the only thing that knows which
 * routes exist and what a page actually drew, and a unit test can prove these
 * five functions accuse the exact text a diagnosis once recorded without ever
 * opening a browser — which is what keeps them proved on every run of the
 * standard gate, not only on the day somebody points the suite at a
 * violating dataset.
 *
 * The English fallback word the placeholder detector counts is read from the
 * console's own catalogue, not repeated as a literal — the same technique
 * `transversal-rules.spec.ts` already uses to read `SETTINGS_PAGES` and the
 * scroll-budget viewport: a narrow, load-bearing read of the one file that
 * owns the fact, because a Playwright spec cannot `import` a Next.js module
 * built for the browser.
 */

/** One string this file read out of a source file it does not own. */
function sourceText(relativeToThisFile: string): string {
  return readFileSync(
    fileURLToPath(new URL(relativeToThisFile, import.meta.url)),
    'utf8',
  );
}

/** The English string `console/src/i18n/en.ts` declares for `key`. */
function catalogueMessage(key: string): string {
  const source = sourceText('../../src/i18n/en.ts');
  const found = new RegExp(`'${key}':\\s*'([^']*)'`).exec(source);
  if (found?.[1] === undefined) {
    throw new Error(`${key} is not declared in console/src/i18n/en.ts`);
  }
  return found[1];
}

// --- 1. Raw markdown never stands in for rendered or summarised text -------

/**
 * The three markers a document was written in markdown and delivered raw: a
 * heading, bold emphasis, and an inline code span. Any one of them, visible
 * as literal characters rather than as formatting, is the violation — a
 * renderer or a summary is missing, not a matter of degree.
 */
const MARKDOWN_MARKERS: readonly string[] = ['###', '**', '`'];

/** A short window of `text` around `marker`, for a failure message to quote. */
function around(text: string, marker: string): string {
  const index = text.indexOf(marker);
  const start = Math.max(0, index - 20);
  const end = Math.min(text.length, index + marker.length + 20);
  return text.slice(start, end).trim();
}

/**
 * The offending snippet, when `text` carries a raw markdown marker.
 *
 * `null` when `text` is prose a person would read as prose — which is the
 * ordinary case for every screen this rule holds, because the console has no
 * markdown renderer and is not supposed to need one for a title, a cell, or
 * a paragraph.
 */
export function rawMarkdown(text: string): string | null {
  for (const marker of MARKDOWN_MARKERS) {
    if (text.includes(marker)) {
      return around(text, marker);
    }
  }
  return null;
}

// --- 2. An identifier never plays the part of a name ------------------------

/** A whole value that is nothing but hexadecimal digits, eight or more of them. */
const RAW_HEX = /^[0-9a-f]{8,}$/i;

/**
 * Two or more namespace segments joined by colons — `kind:vendor:hash`.
 *
 * Each segment has to carry at least one non-digit — a lookahead per
 * segment, rather than the plain `[a-z0-9_-]+` this used to be, because a
 * clock reading (`23:41:02`) is three colon-joined, all-digit segments too,
 * and would otherwise read as a composite id the moment one showed up next
 * to a real one in the same sentence.
 */
const COMPOSITE_ID =
  /(?:(?=[a-z0-9_-]*[a-z_-])[a-z0-9_-]+:){2}(?=[a-z0-9_-]*[a-z_-])[a-z0-9_-]+/i;

/** At least two percent-encoded bytes — one is a stray character, two is an id. */
const PERCENT_ENCODED = /%[0-9a-f]{2}/gi;

/**
 * The offending value, when `text` is an identifier standing in for a name.
 *
 * Covers the three shapes the diagnosis found doing this: a hexadecimal run
 * id with nothing else to it, a colon-joined composite id, and an id that
 * arrived percent-encoded and was never decoded before it was shown. `text`
 * is expected to be one value already isolated by the caller — a cell, a
 * title, a breadcrumb's current crumb — never a whole page, because a page
 * of prose can legitimately contain a word that happens to be eight
 * hexadecimal-looking characters somewhere in a sentence.
 */
export function identifierAsName(text: string): string | null {
  const trimmed = text.trim();
  if (trimmed === '') return null;
  const percentHits = trimmed.match(PERCENT_ENCODED);
  if (percentHits !== null && percentHits.length >= 2) return trimmed;
  if (RAW_HEX.test(trimmed)) return trimmed;
  const composite = COMPOSITE_ID.exec(trimmed);
  if (composite !== null) return composite[0];
  return null;
}

// --- 3. A metadata line carries at most one placeholder ---------------------

/** What this console shows for a fact nothing recorded — read, not repeated. */
export const FALLBACK_TOKEN = catalogueMessage('surface.none');

/**
 * The count and the line, when `line` carries the fallback word twice or more.
 *
 * `line` is one metadata line as a reader takes it in — a list row's cells
 * joined together, or a page subtitle already joined by its own separator.
 * One fallback in a line is an honest gap; two side by side is a sentence
 * with nothing left to be about.
 */
export function twoPlaceholders(line: string): string | null {
  const count = line.split(FALLBACK_TOKEN).length - 1;
  if (count < 2) return null;
  return `"${FALLBACK_TOKEN}" appears ${String(count)} times in "${line.trim()}"`;
}

// --- 4. A live control never survives onto a terminal run -------------------

/** The words a run's own status settles on. Mirrors `design/status.ts#isSettled`. */
const SETTLED_RUN_WORDS: readonly string[] = ['succeeded', 'failed', 'cancelled'];

/**
 * The violation, when a settled run's own page still offers a live control.
 *
 * `listStatus` is the status word the run list showed for this row before it
 * was opened; `controlText` is the live-only control's own visible text on
 * the run's detail page, or `''` when the page offered none. Both empty or
 * `listStatus` still in flight is not a violation — a run genuinely being
 * watched is exactly when this control belongs.
 */
export function liveControlOnTerminalRun(
  listStatus: string,
  controlText: string,
): string | null {
  const settled = SETTLED_RUN_WORDS.includes(listStatus.trim().toLowerCase());
  if (settled && controlText.trim() !== '') {
    return (
      `the list showed status "${listStatus.trim()}" and the run's own page ` +
      `still offered "${controlText.trim()}"`
    );
  }
  return null;
}

// --- 5. Nothing is asserted in the negative from a read that failed ---------

/**
 * The violation, when `assertion` is shown while the read behind it failed.
 *
 * `dependencyFailed` is whether the panel or chip that would justify
 * `assertion` is known, on this same page, to have come from a read that did
 * not succeed. A screen may say it does not know; it may not derive a
 * statement about the world from a read that never answered.
 */
export function negativeAssertionAfterFailedRead(
  dependencyFailed: boolean,
  assertion: string,
): string | null {
  const trimmed = assertion.trim();
  if (dependencyFailed && trimmed !== '') {
    return `"${trimmed}" is asserted on a page where the read behind it failed`;
  }
  return null;
}
