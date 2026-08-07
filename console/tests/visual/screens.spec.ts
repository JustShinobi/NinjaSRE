import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

/**
 * Every registered screen, captured and compared against its committed baseline.
 *
 * The data comes from the committed fixture set rather than from a running
 * gateway. A screenshot suite that depends on a live backend is a screenshot
 * suite that fails for reasons which have nothing to do with the pixels, and
 * the fixture set already carries a fixed reference instant so that two runs a
 * week apart produce the same image.
 */

interface Screen {
  readonly id: string;
  readonly route: string;
  readonly status: string;
}

interface Registry {
  readonly screens: readonly Screen[];
}

function readJson(relative: string): unknown {
  const path = fileURLToPath(new URL(relative, import.meta.url));
  return JSON.parse(readFileSync(path, 'utf8'));
}

function registry(): Registry {
  const loaded = readJson('../../visual/screens.json');
  if (typeof loaded !== 'object' || loaded === null) {
    throw new Error('visual/screens.json does not hold an object');
  }
  const screens: unknown = Reflect.get(loaded, 'screens');
  if (!Array.isArray(screens)) {
    throw new Error('visual/screens.json declares no screens');
  }
  return { screens: screens as readonly Screen[] };
}

/** The body the committed fixture set answers `endpoint` with, for `scenario`. */
function fixtureBody(scenario: string, endpoint: string): unknown {
  const loaded = readJson(`../../../fixtures/scenarios/${scenario}/${endpoint}.json`);
  const responses: unknown = Reflect.get(Object(loaded), 'responses');
  if (!Array.isArray(responses) || responses.length === 0) {
    throw new Error(`${scenario}/${endpoint}.json holds no responses`);
  }
  return Reflect.get(Object(responses[0]), 'body');
}

const ENDPOINT_FOR: Readonly<Record<string, string>> = {
  '/v1/runs': 'runs',
};

for (const screen of registry().screens.filter((each) => each.status === 'baselined')) {
  test(`${screen.id} matches its baseline`, async ({ page }) => {
    await page.route('**/v1/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      const endpoint = ENDPOINT_FOR[path];
      if (endpoint === undefined) {
        await route.fulfill({ status: 404, body: '{}' });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(fixtureBody('populated', endpoint)),
      });
    });

    await page.goto(screen.route);
    await expect(page).toHaveScreenshot(`${screen.id}.png`, { fullPage: true });
  });
}
