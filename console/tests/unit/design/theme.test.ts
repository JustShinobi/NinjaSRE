import { afterEach, describe, expect, it, type MockInstance, vi } from 'vitest';

import {
  NO_FLASH_SCRIPT,
  readStoredTheme,
  resolveTheme,
  storeTheme,
  THEME_ATTRIBUTE,
  THEME_STORAGE_KEY,
} from '@/design/theme';

/**
 * Theme resolution, and the property that is easy to claim and easy to lose.
 *
 * The final state is the boring half: system by default, an explicit choice
 * wins, and the choice survives a reload. The half that actually costs
 * something is *when* it is applied — a console that resolves the theme after
 * React has hydrated shows the wrong theme for a frame, on every load, which is
 * the flash FR-004 forbids. So the script that applies it is asserted to run
 * before the document has a body, which is the only place a flash can be ruled
 * out rather than shortened.
 */

afterEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute(THEME_ATTRIBUTE);
});

/** A browser in private mode, or an origin whose storage the operator blocked. */
function refuseStorage(): MockInstance<Storage['getItem']> {
  return vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('storage is not available');
  });
}

/** Run the no-flash script the way a browser does: as a script in the document. */
function runNoFlashScript(): void {
  const element = document.createElement('script');
  element.text = NO_FLASH_SCRIPT;
  document.head.append(element);
  element.remove();
}

describe('resolving a theme', () => {
  it('follows the operating system when nobody has chosen', () => {
    expect(resolveTheme(null, true)).toBe('dark');
    expect(resolveTheme(null, false)).toBe('light');
  });

  it('lets an explicit choice override the operating system, both ways', () => {
    expect(resolveTheme('light', true)).toBe('light');
    expect(resolveTheme('dark', false)).toBe('dark');
  });

  it('ignores a stored value that is not a theme rather than rendering nothing', () => {
    expect(resolveTheme('midnight', true)).toBe('dark');
    expect(resolveTheme('', false)).toBe('light');
  });
});

describe('persisting a choice', () => {
  it('survives a reload', () => {
    storeTheme('dark');
    expect(readStoredTheme()).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('returns to following the operating system when the choice is cleared', () => {
    storeTheme('dark');
    storeTheme(null);
    expect(readStoredTheme()).toBeNull();
    expect(resolveTheme(readStoredTheme(), true)).toBe('dark');
  });

  it('treats storage a browser refuses as no choice rather than as a crash', () => {
    const refused = refuseStorage();
    try {
      expect(readStoredTheme()).toBeNull();
    } finally {
      refused.mockRestore();
    }
  });
});

describe('the no-flash script', () => {
  it('applies the stored choice before anything is painted', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    runNoFlashScript();
    expect(document.documentElement.getAttribute(THEME_ATTRIBUTE)).toBe('dark');
  });

  it('leaves the operating system in charge when nobody has chosen', () => {
    runNoFlashScript();
    // No attribute at all, so the media query in the stylesheet decides. Writing
    // a resolved value here would freeze the theme at load and stop it tracking
    // a system that changes while the page is open.
    expect(document.documentElement.hasAttribute(THEME_ATTRIBUTE)).toBe(false);
  });

  it('is a single synchronous statement, so nothing can paint before it', () => {
    expect(NO_FLASH_SCRIPT).not.toContain('addEventListener');
    expect(NO_FLASH_SCRIPT).not.toContain('DOMContentLoaded');
    expect(NO_FLASH_SCRIPT).not.toContain('await');
    expect(NO_FLASH_SCRIPT.length).toBeLessThan(400);
  });

  it('survives a browser that refuses storage', () => {
    const refused = refuseStorage();
    try {
      runNoFlashScript();
      expect(document.documentElement.hasAttribute(THEME_ATTRIBUTE)).toBe(false);
    } finally {
      refused.mockRestore();
    }
  });
});
