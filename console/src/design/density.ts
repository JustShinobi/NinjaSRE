/**
 * Density, applied once at the top of the application.
 *
 * A density is not a theme and must never become one. It changes spacing and
 * control height, which is what `DENSITY_METRICS` declares and all it declares
 * — three lengths, no colours. Applying it as an attribute on the document root
 * means the tokens underneath every component change together, so no component
 * knows a density exists and none of them can disagree about what compact means.
 *
 * It is the operator's choice, and it is kept: a long list is read compact by
 * the people who read long lists, and asking them to say so on every page would
 * be the same as not offering it. The choice lives in the browser's own storage
 * for this origin, which is one deployment — a console served from somewhere
 * else is a different deployment and gets its own answer.
 *
 * Unlike the theme there is no third state. A theme can follow the operating
 * system, which has an opinion about it; nothing outside this console has an
 * opinion about how tall a table row should be, so there are two steps and the
 * default is comfortable.
 */

import { DENSITIES, type Density } from './tokens';

/** The attribute the token stylesheet keys the compact block off. */
export const DENSITY_ATTRIBUTE = 'data-density';

/** Where the choice is kept. */
export const DENSITY_STORAGE_KEY = 'ninjasre.density';

/**
 * Published when the choice changes.
 *
 * Storage events do not fire in the tab that wrote the value, so a control that
 * only listened to those would show the old choice in the very window somebody
 * just changed it in.
 */
export const DENSITY_CHANGED_EVENT = 'ninjasre:density-changed';

/** Whether `value` names a density this console has. */
export function isDensity(value: string | null): value is Density {
  return value !== null && (DENSITIES as readonly string[]).includes(value);
}

/** Put `density` on the document. */
export function applyDensity(density: Density): void {
  document.documentElement.setAttribute(DENSITY_ATTRIBUTE, density);
}

/** The density in force, which is comfortable unless something said otherwise. */
export function readDensity(): Density {
  const applied = document.documentElement.getAttribute(DENSITY_ATTRIBUTE);
  return isDensity(applied) ? applied : 'comfortable';
}

/**
 * The stored choice, or `null` when there is none.
 *
 * A browser may refuse storage entirely — private mode, a blocked origin, a
 * quota. That is "no choice", not a broken console, so it is caught here rather
 * than thrown at whichever component happened to ask. A stored value this build
 * has never heard of is treated the same way.
 */
export function readStoredDensity(): Density | null {
  try {
    const stored = window.localStorage.getItem(DENSITY_STORAGE_KEY);
    return isDensity(stored) ? stored : null;
  } catch {
    return null;
  }
}

/** Keep `density` across sessions, apply it, and say so. */
export function storeDensity(density: Density): void {
  try {
    window.localStorage.setItem(DENSITY_STORAGE_KEY, density);
  } catch {
    // A browser that refuses storage still gets the density it asked for for
    // the life of the page. Failing the interaction would be worse than
    // forgetting the choice.
  }
  applyDensity(density);
  window.dispatchEvent(new Event(DENSITY_CHANGED_EVENT));
}

/**
 * The statement that runs before the first paint.
 *
 * A density corrected in an effect is not a flash of the wrong colour — it is
 * every row on the page changing height under somebody's eyes, and on a table
 * of eighty-six that moves whatever they were about to click. So it is applied
 * synchronously, before there is a body, exactly as the theme is.
 *
 * It writes nothing when there is no stored choice, because comfortable is the
 * default and the stylesheet already produces it without an attribute.
 */
export const NO_FLASH_DENSITY_SCRIPT = `try{var d=localStorage.getItem(${JSON.stringify(
  DENSITY_STORAGE_KEY,
)});if(d==="comfortable"||d==="compact")document.documentElement.setAttribute(${JSON.stringify(
  DENSITY_ATTRIBUTE,
)},d)}catch(e){}`;
