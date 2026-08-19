/**
 * Remembering a scroll position across the round trip through the credential
 * panel.
 *
 * This is session state, not screen state. The URL already carries every
 * filter the panel's close address needs to reopen the same view — that is
 * what `url-state.ts` is for — but scroll position is not one of the things
 * a link carries: nobody expects a shared `/integrations` link to land at
 * somebody else's scroll offset. `sessionStorage` is the right shelf for
 * exactly that distinction. It survives the round trip through the panel's
 * own address but never leaves this tab, and it is read back once and
 * forgotten so a stale position never reappears on an unrelated visit.
 *
 * The position is read twice in one round trip, not once: `IntegrationPanel`
 * peeks it on mount, to correct a jump the browser itself introduces (below),
 * and consumes it on unmount, to put the catalogue back where it was. Both
 * reads have to reach the same value, which is why capturing only forgets on
 * `consumeScrollPosition`, never on `peekScrollPosition`.
 *
 * **Why the panel needs to correct its own opening, not only its closing.**
 * `/integrations` and `/integrations/[name]` are two distinct routes, and a
 * client-side navigation between them replaces the whole server-rendered
 * subtree rather than patching it in place. For the instant that replacement
 * takes, the document can be shorter than the scroll position it was at —
 * the browser clamps `window.scrollY` down to fit what is on screen right
 * then, and does not undo that clamp once the new content restores the
 * document to its full height. The result is a small, one-off upward jump
 * that a wider viewport or a shorter catalogue hides and a long one does not.
 * The fix is not to hold the page artificially tall through the swap; it is
 * to notice, once the panel has mounted, that the browser moved away from
 * where the card was actually clicked, and put it back.
 */

const INTEGRATIONS_SCROLL_KEY = 'ninjasre.integrations.scroll';

/**
 * How long a captured position is trusted for the correction above.
 *
 * Generous for the slowest realistic client-side navigation, far short of
 * "the operator came back to this tab later". A stored value older than this
 * is a leftover from a visit that opened the panel and never closed it
 * (a hard reload, a typed address, a closed tab) rather than evidence about
 * the navigation happening now — trusting it would drag a fresh deep link
 * down to a stranger's old scroll offset instead of landing at the top.
 */
const SCROLL_MEMORY_MAX_AGE_MS = 5000;

interface StoredScroll {
  readonly y: number;
  readonly at: number;
}

/** `raw`, read as a capture this module wrote, or `null` for anything else. */
function parsed(raw: string): StoredScroll | null {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  const y: unknown = Reflect.get(Object(value), 'y');
  const at: unknown = Reflect.get(Object(value), 'at');
  return typeof y === 'number' &&
    Number.isFinite(y) &&
    typeof at === 'number' &&
    Number.isFinite(at)
    ? { y, at }
    : null;
}

/** Remember where the page is scrolled to, before a link leaves it. */
export function captureScrollPosition(): void {
  try {
    sessionStorage.setItem(
      INTEGRATIONS_SCROLL_KEY,
      JSON.stringify({ y: window.scrollY, at: Date.now() }),
    );
  } catch {
    // Storage can be unavailable — private browsing, quota, a policy that
    // disables it. Losing the memory of a scroll position is not worth
    // failing the navigation over.
  }
}

/**
 * Read the remembered position without forgetting it, or `null` when there
 * is none or when it is too old to trust (see `SCROLL_MEMORY_MAX_AGE_MS`).
 *
 * For a caller that needs to read it again later in the same round trip —
 * `IntegrationPanel`'s own unmount still has to see it, so the mount-time
 * correction cannot be the read that consumes it.
 */
export function peekScrollPosition(): number | null {
  try {
    const stored = sessionStorage.getItem(INTEGRATIONS_SCROLL_KEY);
    if (stored === null) return null;
    const found = parsed(stored);
    if (found === null) return null;
    return Date.now() - found.at > SCROLL_MEMORY_MAX_AGE_MS ? null : found.y;
  } catch {
    return null;
  }
}

/** Read back and forget the remembered position, or `null` when there is none. */
export function consumeScrollPosition(): number | null {
  const value = peekScrollPosition();
  try {
    sessionStorage.removeItem(INTEGRATIONS_SCROLL_KEY);
  } catch {
    // As above: losing the memory of a scroll position is not fatal.
  }
  return value;
}
