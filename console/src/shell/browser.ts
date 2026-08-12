'use client';

import { useSyncExternalStore } from 'react';

import { DENSITY_CHANGED_EVENT, readStoredDensity } from '@/design/density';
import { readStoredTheme, THEME_CHANGED_EVENT } from '@/design/theme';
import type { Density, Theme } from '@/design/tokens';
import { DEFAULT_LOCALE, isLocale, type Locale } from '@/i18n/messages';
import { LOCALE_COOKIE } from '@/session/cookies';

/**
 * The three things the shell can only learn from a browser.
 *
 * Each is read through `useSyncExternalStore` rather than through a state and an
 * effect, and the difference is not stylistic. A value read into state inside an
 * effect is rendered once with the server's answer and once with the browser's,
 * which is a visible correction on every load — the same failure the theme
 * script exists to prevent, arriving through a different door. A store has a
 * server snapshot and a client snapshot, and React renders the right one.
 */

/** How often the clock is re-read. A minute's warning does not need a second's precision. */
export const CLOCK_INTERVAL_MS = 30_000;

let sampled = 0;

function subscribeToClock(onChange: () => void): () => void {
  const tick = setInterval(() => {
    sampled = Date.now();
    onChange();
  }, CLOCK_INTERVAL_MS);
  return () => {
    clearInterval(tick);
  };
}

function clockSnapshot(): number {
  if (sampled === 0) {
    sampled = Date.now();
  }
  return sampled;
}

function clockServerSnapshot(): number {
  return 0;
}

/**
 * The current instant, or `null` on the server.
 *
 * `null` rather than the server's clock, because the server's clock is not the
 * viewer's and a countdown rendered from it is wrong by the network's latency
 * plus whatever the two machines disagree about.
 */
export function useNow(): Date | null {
  const at = useSyncExternalStore(subscribeToClock, clockSnapshot, clockServerSnapshot);
  return at === 0 ? null : new Date(at);
}

function subscribeToTheme(onChange: () => void): () => void {
  window.addEventListener(THEME_CHANGED_EVENT, onChange);
  return () => {
    window.removeEventListener(THEME_CHANGED_EVENT, onChange);
  };
}

function themeServerSnapshot(): Theme | null {
  return null;
}

/** The theme this viewer chose, or `null` when they are following the system. */
export function useChosenTheme(): Theme | null {
  return useSyncExternalStore(subscribeToTheme, readStoredTheme, themeServerSnapshot);
}

function subscribeToDensity(onChange: () => void): () => void {
  window.addEventListener(DENSITY_CHANGED_EVENT, onChange);
  return () => {
    window.removeEventListener(DENSITY_CHANGED_EVENT, onChange);
  };
}

function densityServerSnapshot(): Density {
  // The server cannot know the choice, and comfortable is what the stylesheet
  // produces without an attribute — so this is the markup the pre-paint
  // statement then corrects, rather than a guess it has to undo.
  return 'comfortable';
}

function densitySnapshot(): Density {
  return readStoredDensity() ?? 'comfortable';
}

/** The density this viewer reads long lists at. */
export function useDensity(): Density {
  return useSyncExternalStore(
    subscribeToDensity,
    densitySnapshot,
    densityServerSnapshot,
  );
}

function subscribeToNothing(): () => void {
  // A cookie does not change under a page that is not reloading. There is
  // nothing to subscribe to, and pretending otherwise would be a listener that
  // never fires.
  return () => undefined;
}

function localeSnapshot(): Locale {
  const found = document.cookie
    .split(';')
    .map((part) => part.trim().split('='))
    .find(([name]) => name === LOCALE_COOKIE)?.[1];
  return isLocale(found) ? found : DEFAULT_LOCALE;
}

function localeServerSnapshot(): Locale {
  return DEFAULT_LOCALE;
}

/**
 * The locale, read in a browser.
 *
 * Only for the error boundary, which Next mounts outside the layout that
 * resolves the locale on the server. Everything else is handed one as a prop.
 */
export function useBrowserLocale(): Locale {
  return useSyncExternalStore(subscribeToNothing, localeSnapshot, localeServerSnapshot);
}
