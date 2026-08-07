/**
 * Density, applied once at the top of the application.
 *
 * A density is not a theme and must never become one. It changes spacing and
 * control height, which is what `DENSITY_METRICS` declares and all it declares
 * — three lengths, no colours. Applying it as an attribute on the document root
 * means the tokens underneath every component change together, so no component
 * knows a density exists and none of them can disagree about what compact means.
 */

import { DENSITIES, type Density } from './tokens';

/** The attribute the token stylesheet keys the compact block off. */
export const DENSITY_ATTRIBUTE = 'data-density';

/** Whether `value` names a density this console has. */
export function isDensity(value: string | null): value is Density {
  return value !== null && (DENSITIES as readonly string[]).includes(value);
}

/** Put `density` on the document. Comfortable is the default and clears it. */
export function applyDensity(density: Density): void {
  document.documentElement.setAttribute(DENSITY_ATTRIBUTE, density);
}

/** The density in force, which is comfortable unless something said otherwise. */
export function readDensity(): Density {
  const applied = document.documentElement.getAttribute(DENSITY_ATTRIBUTE);
  return isDensity(applied) ? applied : 'comfortable';
}
