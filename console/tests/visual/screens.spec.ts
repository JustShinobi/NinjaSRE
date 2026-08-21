import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

import { signIn } from '../e2e/session';

/**
 * Every registered screen, captured and compared against its committed baseline.
 *
 * The data comes from the committed fixture set, served to the console by the
 * Node fixture server the capture harness starts. It has to be a real address
 * rather than an interception in the browser: the shell resolves the viewer on
 * the *server*, so a console with nothing to talk to captures the sign-in page
 * and proves nothing about the console. The dataset carries one fixed instant,
 * so two runs a week apart produce the same image.
 *
 * A screen is a route *at a width in a theme*, not a route. The design declares
 * three widths and two themes; a baseline that only ever saw one of the six
 * says nothing about the other five, which is exactly where a responsive
 * regression lives.
 */

interface Screen {
  readonly id: string;
  readonly route: string;
  readonly status: string;
  readonly viewport?: number;
  readonly theme?: string;
}

interface Registry {
  readonly screens: readonly Screen[];
}

function registry(): Registry {
  const path = fileURLToPath(new URL('../../visual/screens.json', import.meta.url));
  const loaded: unknown = JSON.parse(readFileSync(path, 'utf8'));
  if (typeof loaded !== 'object' || loaded === null) {
    throw new Error('visual/screens.json does not hold an object');
  }
  const screens: unknown = Reflect.get(loaded, 'screens');
  if (!Array.isArray(screens)) {
    throw new Error('visual/screens.json declares no screens');
  }
  return { screens: screens as readonly Screen[] };
}

/** The one route an unauthenticated visitor may reach, and the only one captured cold. */
const UNAUTHENTICATED = '/sign-in';

for (const screen of registry().screens.filter((each) => each.status === 'baselined')) {
  test(`${screen.id} matches its baseline`, async ({ page, context, baseURL }) => {
    await page.setViewportSize({ width: screen.viewport ?? 1440, height: 900 });

    if (screen.route !== UNAUTHENTICATED) {
      await signIn(context, baseURL ?? 'http://127.0.0.1:8425');
    }

    // Set before navigating, so the theme is the one the first paint used and
    // the capture is not of a page that changed theme under itself.
    const theme = screen.theme ?? 'light';
    await page.addInitScript((chosen: string) => {
      window.localStorage.setItem('ninjasre.theme', chosen);
    }, theme);

    await page.goto(screen.route);
    await expect(page).toHaveScreenshot(`${screen.id}.png`, { fullPage: true });
  });
}
