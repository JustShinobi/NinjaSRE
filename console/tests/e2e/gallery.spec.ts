import { expect, test } from '@playwright/test';

/**
 * The claims a real browser has to answer, because jsdom lays nothing out.
 *
 * Three of this feature's success criteria are geometric: nothing overflows
 * sideways at any width the console declares, the two themes differ in colour
 * and never in position, and a viewer who asked for no motion gets none. A unit
 * test can assert the classes that ought to produce those; only a browser can
 * say whether they did.
 */

/** The widths the design declares, and the zoom a low-vision viewer uses. */
const WIDTHS = [320, 768, 1440];

/** Every box on the page, keyed by a path that survives a theme change. */
const MEASURE_GEOMETRY = `
  (() => {
    const boxes = {};
    let index = 0;
    for (const element of document.querySelectorAll('body *')) {
      const box = element.getBoundingClientRect();
      boxes[index + ':' + element.tagName + '.' + element.className.toString()] = [
        Math.round(box.x),
        Math.round(box.y),
        Math.round(box.width),
        Math.round(box.height),
      ];
      index += 1;
    }
    return boxes;
  })()
`;

for (const width of WIDTHS) {
  test(`the gallery does not scroll sideways at ${String(width)}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/gallery');

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    // Naming the widest elements rather than only the number: "something
    // overflows by 41 pixels" is a message that costs an afternoon.
    const culprits = await page.evaluate(() => {
      const limit = document.documentElement.clientWidth;
      return [...document.querySelectorAll('body *')]
        .filter((element) => element.getBoundingClientRect().right > limit + 1)
        .slice(0, 5)
        .map((element) => `${element.tagName}.${element.getAttribute('class') ?? ''}`);
    });
    expect(
      overflow,
      `these run past the viewport: ${culprits.join(' | ')}`,
    ).toBeLessThanOrEqual(0);
  });
}

test('the gallery does not scroll sideways at 200% zoom', async ({ page }) => {
  // Zoom, as a browser does it: the same page in half the CSS pixels. A viewer
  // at 200% on a 1280 monitor sees a 640-pixel-wide document, and a console
  // that needs a horizontal scrollbar there is a console they cannot read.
  await page.setViewportSize({ width: 640, height: 800 });
  await page.goto('/gallery');

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

test('switching theme changes no geometry, only colour', async ({ browser }) => {
  // Reduced motion, because the claim is about *layout*. A spinner's bounding
  // box depends on which frame of its rotation was measured, and comparing two
  // frames would fail for a reason that has nothing to do with the theme.
  const context = await browser.newContext({
    reducedMotion: 'reduce',
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  await page.goto('/gallery');

  await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'light');
  });
  const light: unknown = await page.evaluate(MEASURE_GEOMETRY);

  await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
  });
  const dark: unknown = await page.evaluate(MEASURE_GEOMETRY);

  // Every box, to the pixel. A theme that moved one of them would be a second
  // layout wearing the first one's name, and the visual baselines for the two
  // themes would then be comparing two different pages.
  expect(dark).toEqual(light);

  const ground = await page.evaluate(
    () => getComputedStyle(document.body).backgroundColor,
  );
  await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'light');
  });
  const lightGround = await page.evaluate(
    () => getComputedStyle(document.body).backgroundColor,
  );
  expect(ground, 'the two themes render the same colour').not.toBe(lightGround);
  await context.close();
});

test('a viewer who asked for no motion gets none, rather than a shorter one', async ({
  browser,
}) => {
  const context = await browser.newContext({ reducedMotion: 'reduce' });
  const page = await context.newPage();
  await page.goto('/gallery');

  const durations = await page.evaluate(() =>
    [...document.querySelectorAll('body *')].map((element) => {
      const style = getComputedStyle(element);
      return `${style.transitionDuration}|${style.animationDuration}`;
    }),
  );

  for (const duration of durations) {
    // Removed, not shortened: every value is zero. A design system that halved
    // its durations here would have satisfied nobody and reported success.
    expect(duration.replace(/0s|0ms|,/g, '').trim()).toBe('|');
  }
  await context.close();
});

test('the gallery is not reachable from the console', async ({ page }) => {
  await page.goto('/');

  const links = await page.evaluate(() =>
    [...document.querySelectorAll('a[href]')].map(
      (element) => element.getAttribute('href') ?? '',
    ),
  );
  expect(links.filter((href) => href.includes('gallery'))).toEqual([]);
});
