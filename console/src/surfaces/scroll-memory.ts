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
 */

const INTEGRATIONS_SCROLL_KEY = 'ninjasre.integrations.scroll';

/** Remember where the page is scrolled to, before a link leaves it. */
export function captureScrollPosition(): void {
  try {
    sessionStorage.setItem(INTEGRATIONS_SCROLL_KEY, String(window.scrollY));
  } catch {
    // Storage can be unavailable — private browsing, quota, a policy that
    // disables it. Losing the memory of a scroll position is not worth
    // failing the navigation over.
  }
}

/** Read back and forget the remembered position, or `null` when there is none. */
export function consumeScrollPosition(): number | null {
  try {
    const stored = sessionStorage.getItem(INTEGRATIONS_SCROLL_KEY);
    sessionStorage.removeItem(INTEGRATIONS_SCROLL_KEY);
    if (stored === null) return null;
    const parsed = Number(stored);
    return Number.isFinite(parsed) ? parsed : null;
  } catch {
    return null;
  }
}
