import { expect, test } from '@playwright/test';

import {
  CAPTURE_VIEWPORT_HEIGHT,
  CAPTURE_VIEWPORT_WIDTH,
  fitToInnerScrollers,
  innerScrollers,
} from '../capture';
import { signIn } from './session';

/**
 * The capture harness itself, held to the property every baseline depends on:
 * that the picture contains the whole of what it was registered to protect.
 *
 * `fullPage` grows the picture to the *document*, and a panel that carries its
 * own scrollbar is not part of the document's height — it is a fixed box the
 * viewport's tall, with its content clipped inside. So a full-page capture of a
 * screen whose subject scrolls inside itself photographs the first viewport of
 * that subject and stops, and nothing about the resulting image says a piece is
 * missing. The integrations slide-over is where this was found: the capture cut
 * at the certificate-authority field, and the package-documentation section the
 * screen's own acceptance record names was outside the image.
 *
 * The screen is not the defect. This is the instrument, tested here rather than
 * in the visual project because the property is about geometry, not about
 * pixels — it needs a browser and a running console, both of which the
 * behaviour project has on any machine, and neither of which is the pinned
 * capture image the visual baselines require.
 */

const PANEL_ROUTE = '/integrations/alertmanager';

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

test.describe('a screen whose subject scrolls inside itself', () => {
  test('is measured as out of frame before the harness is asked to fit it', async ({
    page,
  }) => {
    await page.setViewportSize({
      width: CAPTURE_VIEWPORT_WIDTH,
      height: CAPTURE_VIEWPORT_HEIGHT,
    });
    await page.goto(PANEL_ROUTE);
    await expect(page.getByTestId('integration-docs')).toBeAttached();

    // Not "the panel overflows" as a fact worth pinning — it would stop being
    // true the day somebody shortens the panel, and that day is not a defect.
    // What is pinned is that the measurement *finds* an overflow when one is
    // there, which is the half of the instrument the fitting below depends on.
    const clipped = await innerScrollers(page);
    expect(
      clipped.length,
      'the slide-over carries more than a viewport of content, so the measurement has something to find',
    ).toBeGreaterThan(0);
  });

  test('is wholly inside the frame once the harness has fitted the viewport to it', async ({
    page,
  }) => {
    await page.setViewportSize({
      width: CAPTURE_VIEWPORT_WIDTH,
      height: CAPTURE_VIEWPORT_HEIGHT,
    });
    await page.goto(PANEL_ROUTE);
    await expect(page.getByTestId('integration-docs')).toBeAttached();

    await fitToInnerScrollers(page);

    expect(
      await innerScrollers(page),
      'something on this screen still scrolls inside itself, so a full-page capture would cut it',
    ).toEqual([]);

    // The clause the acceptance record names by hand, checked as geometry: the
    // deepest thing on the screen sits within the box a capture takes.
    const docs = await page.getByTestId('integration-docs').boundingBox();
    const viewport = page.viewportSize();
    expect(docs).not.toBeNull();
    expect(viewport).not.toBeNull();
    const bottom = (docs?.y ?? 0) + (docs?.height ?? 0);
    expect(
      bottom,
      'the package-documentation section ends below the captured area',
    ).toBeLessThanOrEqual(viewport?.height ?? 0);
  });

  test('leaves a screen with nothing scrolling inside itself at the registered height', async ({
    page,
  }) => {
    await page.setViewportSize({
      width: CAPTURE_VIEWPORT_WIDTH,
      height: CAPTURE_VIEWPORT_HEIGHT,
    });
    await page.goto('/integrations');
    await expect(page.getByTestId('page-header')).toBeVisible();

    await fitToInnerScrollers(page);

    // Forty-two committed baselines were captured at this height, and a
    // harness that grew the viewport on every screen would invalidate all of
    // them to fix one. Growth happens where something is clipped and nowhere
    // else.
    expect(page.viewportSize()?.height).toBe(CAPTURE_VIEWPORT_HEIGHT);
  });
});
