/**
 * Which theme a viewer gets, and when.
 *
 * The rule is short: follow the operating system, let an explicit choice
 * override it, and keep that choice. What costs something is *when* the choice
 * is applied. A console that resolves the theme in a React effect renders the
 * default first and the choice a frame later, so every load flashes — and a
 * flash is not a cosmetic complaint at three in the morning, it is a white
 * rectangle in a dark room.
 *
 * So the system default needs no JavaScript at all: it is a media query in the
 * token stylesheet. Only the *override* needs code, and that code is one
 * synchronous statement in the document head, before there is a body to paint.
 */

import { THEMES, type Theme } from './tokens';

/** Where an explicit choice is kept. */
export const THEME_STORAGE_KEY = 'ninjasre.theme';

/** The attribute the token stylesheet keys its two explicit blocks off. */
export const THEME_ATTRIBUTE = 'data-theme';

/** Whether `value` names a theme this console has. */
export function isTheme(value: string | null): value is Theme {
  return value !== null && (THEMES as readonly string[]).includes(value);
}

/**
 * The theme a viewer gets, given what they chose and what their system asks for.
 *
 * A stored value that is not a theme is treated as no choice rather than as an
 * error: a build one version ahead may have written a name this one has never
 * heard of, and the honest answer to that is to follow the system.
 */
export function resolveTheme(stored: string | null, systemPrefersDark: boolean): Theme {
  if (isTheme(stored)) {
    return stored;
  }
  return systemPrefersDark ? 'dark' : 'light';
}

/**
 * The stored choice, or `null` when there is none.
 *
 * A browser may refuse storage entirely — private mode, a blocked origin, a
 * quota. That is "no choice", not a broken console, so it is caught here rather
 * than thrown at whichever component happened to ask.
 */
export function readStoredTheme(): Theme | null {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(stored) ? stored : null;
  } catch {
    return null;
  }
}

/** Keep `theme` across sessions, or clear the choice and go back to the system. */
export function storeTheme(theme: Theme | null): void {
  try {
    if (theme === null) {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
    } else {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    }
  } catch {
    // A browser that refuses storage still gets the theme it asked for for the
    // life of the page. Failing the interaction would be worse than forgetting.
  }
  applyTheme(theme);
}

/** Put `theme` on the document, or take the override off and follow the system. */
export function applyTheme(theme: Theme | null): void {
  const root = document.documentElement;
  if (theme === null) {
    root.removeAttribute(THEME_ATTRIBUTE);
    return;
  }
  root.setAttribute(THEME_ATTRIBUTE, theme);
}

/**
 * The statement that runs before the first paint.
 *
 * It writes nothing when there is no stored choice, which is deliberate: an
 * attribute holding a resolved value would freeze the theme at load and stop it
 * following an operating system that changes while the page is open. The media
 * query already handles that case, and handles it without JavaScript.
 */
export const NO_FLASH_SCRIPT = `try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});if(t==="dark"||t==="light")document.documentElement.setAttribute(${JSON.stringify(
  THEME_ATTRIBUTE,
)},t)}catch(e){}`;
