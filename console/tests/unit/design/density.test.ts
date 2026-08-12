import { beforeEach, describe, expect, it } from 'vitest';

import {
  DENSITY_ATTRIBUTE,
  DENSITY_CHANGED_EVENT,
  NO_FLASH_DENSITY_SCRIPT,
  applyDensity,
  isDensity,
  readDensity,
  readStoredDensity,
  storeDensity,
} from '@/design/density';
import { DENSITIES } from '@/design/tokens';

/**
 * The density, which existed as machinery nothing could switch on.
 *
 * Every piece of this was already written — the two steps, the metrics each one
 * decides, the attribute, the three custom properties underneath every
 * component. What was missing was anybody calling it, so a deployment watching
 * eighty-six resources read them in a table built for reading eight.
 *
 * It is kept, applied and announced the way the theme is, for the reason the
 * theme gives: a preference corrected after the first paint is a visible
 * correction, and for a density that correction is the whole page moving.
 */

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute(DENSITY_ATTRIBUTE);
});

describe('the density a viewer chose', () => {
  it('names both steps and nothing else', () => {
    expect([...DENSITIES]).toEqual(['comfortable', 'compact']);
    for (const density of DENSITIES) {
      expect(isDensity(density)).toBe(true);
    }
    expect(isDensity('cosy')).toBe(false);
    expect(isDensity(null)).toBe(false);
  });

  it('survives the session it was chosen in', () => {
    storeDensity('compact');
    expect(readStoredDensity()).toBe('compact');
    expect(readDensity()).toBe('compact');

    storeDensity('comfortable');
    expect(readStoredDensity()).toBe('comfortable');
  });

  it('is comfortable when nobody has said otherwise', () => {
    expect(readStoredDensity()).toBeNull();
    expect(readDensity()).toBe('comfortable');
  });

  it('reaches the document, so no component has to know one exists', () => {
    applyDensity('compact');
    expect(document.documentElement.getAttribute(DENSITY_ATTRIBUTE)).toBe('compact');
  });

  it('announces the change in the tab that made it', () => {
    // Storage events do not fire in the window that wrote the value, so a
    // control listening only to those would show the old choice in the very
    // window somebody just changed it in.
    let announced = 0;
    window.addEventListener(DENSITY_CHANGED_EVENT, () => {
      announced += 1;
    });
    storeDensity('compact');
    expect(announced).toBe(1);
  });

  it('treats a value it has never heard of as no choice at all', () => {
    window.localStorage.setItem('ninjasre.density', 'cosy');
    expect(readStoredDensity()).toBeNull();
  });
});

describe('the statement that runs before the first paint', () => {
  it('applies a stored density with no reference to anything', () => {
    window.localStorage.setItem('ninjasre.density', 'compact');
    // Evaluated the way the document evaluates it: no imports, no bundler.
    new Function(NO_FLASH_DENSITY_SCRIPT)();
    expect(document.documentElement.getAttribute(DENSITY_ATTRIBUTE)).toBe('compact');
  });

  it('writes nothing when there is no choice to apply', () => {
    new Function(NO_FLASH_DENSITY_SCRIPT)();
    expect(document.documentElement.hasAttribute(DENSITY_ATTRIBUTE)).toBe(false);
  });
});
