import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

import {
  CAPTURE_VIEWPORT_HEIGHT,
  CAPTURE_VIEWPORT_WIDTH,
  fitToInnerScrollers,
} from '../capture';
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
 *
 * The height is the registered one only until something on the screen is found
 * to scroll inside itself, at which point the viewport grows until it does not
 * — see `tests/capture.ts`. `fullPage` measures the *document*, and a slide-over
 * with its own scrollbar is not part of the document's height, so without this
 * the picture would stop partway down the panel and say nothing about it. A
 * screen with nothing clipped is captured at exactly the height it declares,
 * which is why this leaves every existing baseline where it was.
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

/**
 * A registered `route` may carry this token in place of an id the fixture
 * generator chooses, not this file — an incident id is not a route that
 * exists by construction the way `/settings/machine-tokens` is. Resolving it
 * here, against the same capture the incident-detail screen itself reads,
 * means a fixture rebuild that hands the investigated timeline to a
 * different incident moves this baseline's target with it instead of
 * leaving the entry pointed at whichever id used to be first — which is
 * exactly how a previous registration ended up capturing an incident that
 * had never existed in any fixture.
 */
const DETAILED_INCIDENT_TOKEN = '{{detailed-incident-id}}';

/**
 * The public address of the incident the dataset details — the only one the
 * seeder gives a timeline. Found by carrying an investigation, never by
 * "whichever record the file lists first": the file's own record order
 * follows its own keys (the public address each incident answers by), not
 * the order the incidents were raised in.
 */
function detailedIncidentId(): string {
  const source = readFileSync(
    fileURLToPath(
      new URL(
        '../../../fixtures/scenarios/populated/incident-detail.json',
        import.meta.url,
      ),
    ),
    'utf8',
  );
  const captured = JSON.parse(source) as {
    responses: {
      body?: {
        incident?: { public_id?: string };
        investigation?: unknown;
      };
    }[];
  };
  for (const response of captured.responses) {
    const found = response.body?.incident?.public_id;
    if (
      typeof found === 'string' &&
      found !== '' &&
      response.body?.investigation !== null &&
      response.body?.investigation !== undefined
    ) {
      return found;
    }
  }
  throw new Error(
    'the incident-detail capture names no investigated incident, so no timeline is ever seeded',
  );
}

/** `screen.route`, with `DETAILED_INCIDENT_TOKEN` resolved when it carries one. */
function routeFor(screen: Screen): string {
  return screen.route.includes(DETAILED_INCIDENT_TOKEN)
    ? screen.route.replace(DETAILED_INCIDENT_TOKEN, detailedIncidentId())
    : screen.route;
}

/** The one route an unauthenticated visitor may reach, and the only one captured cold. */
const UNAUTHENTICATED = '/sign-in';

for (const screen of registry().screens.filter((each) => each.status === 'baselined')) {
  test(`${screen.id} matches its baseline`, async ({ page, context, baseURL }) => {
    await page.setViewportSize({
      width: screen.viewport ?? CAPTURE_VIEWPORT_WIDTH,
      height: CAPTURE_VIEWPORT_HEIGHT,
    });

    const route = routeFor(screen);

    if (route !== UNAUTHENTICATED) {
      await signIn(context, baseURL ?? 'http://127.0.0.1:8425');
    }

    // Set before navigating, so the theme is the one the first paint used and
    // the capture is not of a page that changed theme under itself.
    const theme = screen.theme ?? 'light';
    await page.addInitScript((chosen: string) => {
      window.localStorage.setItem('ninjasre.theme', chosen);
    }, theme);

    await page.goto(route);

    // Before the shutter, not after: a capture that cut a panel in half is a
    // baseline somebody would accept without ever seeing what it left out.
    const clipped = await fitToInnerScrollers(page);
    expect(
      clipped,
      `${screen.id} has a region a full-page capture cannot reach into, so the ` +
        `image would be missing part of what this entry protects`,
    ).toEqual([]);

    await expect(page).toHaveScreenshot(`${screen.id}.png`, { fullPage: true });
  });
}
