import type { Page } from '@playwright/test';

/**
 * What a screenshot has to do before it is worth comparing: contain the whole
 * of the thing it was registered to protect.
 *
 * Playwright's `fullPage` grows the picture to the height of the *document*.
 * That is the right answer for a page that scrolls, and the wrong one for a
 * panel that scrolls inside itself: a fixed box the viewport's tall, with its
 * own `overflow-y`, contributes nothing to the document's height, so the
 * picture stops at the first viewport of it and nothing in the resulting image
 * says a piece is missing. A baseline accepted from such an image protects the
 * top of a panel and is silent about the rest — which is worse than no baseline,
 * because the gate reports it as covered.
 *
 * So the viewport is fitted to the content before the shutter opens. Growing
 * the viewport is what reaches a `fixed inset-y-0` drawer: its height is the
 * viewport's, so a taller viewport is a taller drawer, and past the point where
 * the drawer is as tall as its content there is nothing left inside it to
 * scroll. That is measured rather than assumed — the loop below stops when the
 * measurement comes back empty, and gives up rather than spinning when growing
 * stops helping, because a container with a fixed pixel height will never be
 * satisfied by a taller window and should be reported instead of waited on.
 */

/**
 * The width and height every registered screen is captured at unless it names
 * another. The same pair `playwright.config.ts` fixes for the suite, restated
 * here because the fitting below is defined against it: growth is measured from
 * this height, and a screen that needs none is captured at exactly it.
 */
export const CAPTURE_VIEWPORT_WIDTH = 1440;
export const CAPTURE_VIEWPORT_HEIGHT = 900;

/**
 * How tall a capture may grow. A ceiling rather than an unbounded loop: a
 * screen that wants more than this is a screen with a runaway list on it, and a
 * 20,000-pixel PNG nobody can review is not the thing to answer that with. Ten
 * viewports, which is five times the scroll budget any configuration screen is
 * allowed, so reaching it means something is wrong rather than something is
 * long.
 */
export const CAPTURE_MAX_HEIGHT = CAPTURE_VIEWPORT_HEIGHT * 10;

/**
 * How many times to grow and re-measure. Fitting a drawer whose height tracks
 * the viewport takes one pass; a second exists because growing the window can
 * reflow what is inside it, and a third is the margin. Beyond that the
 * measurement is not converging and the caller should hear so.
 */
const FITTING_PASSES = 4;

/** Sub-pixel rounding, not a clipped region. */
const OVERFLOW_TOLERANCE_PX = 1;

/** One region whose content extends past the box drawn around it. */
export interface ClippedRegion {
  /** The element, named the way a failure message can be read. */
  readonly element: string;
  /** How many pixels of it are out of sight. */
  readonly overflow: number;
}

/**
 * Return every region on `page` that scrolls inside itself, worst first.
 *
 * The document's own scroller is excluded: that one `fullPage` already handles,
 * and reporting it would mean every ordinary long page came back as clipped.
 * Only the vertical axis is considered, because only the vertical axis is what
 * `fullPage` grows and therefore only the vertical axis is what it can be wrong
 * about.
 */
export async function innerScrollers(page: Page): Promise<ClippedRegion[]> {
  return page.evaluate(
    ({ tolerance }) => {
      const root = document.scrollingElement;
      const found: { element: string; overflow: number }[] = [];

      for (const element of document.querySelectorAll('*')) {
        if (element === root || element === document.body) continue;
        const style = getComputedStyle(element);
        if (style.overflowY !== 'auto' && style.overflowY !== 'scroll') continue;
        const overflow = element.scrollHeight - element.clientHeight;
        if (overflow <= tolerance) continue;

        const name = element.tagName.toLowerCase();
        const testId = element.getAttribute('data-testid');
        const role = element.getAttribute('role');
        found.push({
          element: testId ?? (role === null ? name : `${name}[role=${role}]`),
          overflow,
        });
      }

      return found.sort((left, right) => right.overflow - left.overflow);
    },
    { tolerance: OVERFLOW_TOLERANCE_PX },
  );
}

/**
 * Grow `page`'s viewport until nothing on it scrolls inside itself, and return
 * what is still clipped when it stops.
 *
 * An empty return is the ordinary outcome and means the next capture will
 * contain everything. A non-empty one names what a capture would cut, and is
 * the caller's to fail on — this function does not assert, because the visual
 * suite and the behaviour suite want to say different things about the same
 * measurement.
 *
 * A screen with nothing clipped is left at exactly the height it arrived at.
 * That is not an optimisation: every committed baseline was captured at the
 * registered height, and a harness that grew the viewport unconditionally would
 * invalidate all of them to fix the one screen that needed it.
 */
export async function fitToInnerScrollers(page: Page): Promise<ClippedRegion[]> {
  const width = page.viewportSize()?.width ?? CAPTURE_VIEWPORT_WIDTH;
  let height = page.viewportSize()?.height ?? CAPTURE_VIEWPORT_HEIGHT;

  for (let pass = 0; pass < FITTING_PASSES; pass += 1) {
    const clipped = await innerScrollers(page);
    if (clipped.length === 0) return [];

    const worst = clipped[0]?.overflow ?? 0;
    const wanted = Math.min(height + worst, CAPTURE_MAX_HEIGHT);
    // No progress left to make: either the ceiling is reached, or the tallest
    // clipped region has a height of its own that a bigger window does not
    // change. Either way the answer is the measurement, not another pass.
    if (wanted <= height) return clipped;

    height = wanted;
    await page.setViewportSize({ width, height });
  }

  return innerScrollers(page);
}
