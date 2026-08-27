import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * Following a link inside the console changes the screen, not the document.
 *
 * Every list in here puts what it is showing in the address — which row is
 * open, which column sorts it, which filter is applied — and that is the right
 * design: a view can be sent to a colleague and it survives a reload. What was
 * wrong is how the address changed. The anchors carrying it were plain `<a>`
 * elements, so each one tore the document down and built it again: the frame,
 * the sidebar, the stylesheet, the scroll position, and any panel further down
 * the page that had already answered. Opening an investigation to read it
 * flashed the whole console, which is the one gesture on this screen somebody
 * repeats.
 *
 * The property is asserted the only way it can be observed from outside: a
 * value is put on `window`, the link is followed, and the value is looked for
 * again. A document that was replaced cannot still be holding it. `navigation`
 * timeline entries are counted as well, because a soft navigation adds none
 * and a reload adds one — two independent witnesses to the same fact, so a
 * future router that kept globals across a reload could not quietly pass this.
 */

/** The window, as the two helpers below need to see it. */
interface MarkedWindow extends Window {
  __documentMark?: string;
}

/** Mark the live document, so a replacement of it can be detected afterwards. */
async function mark(page: Page): Promise<void> {
  await page.evaluate(() => {
    (window as MarkedWindow).__documentMark = 'alive';
  });
}

/** What the document says about itself: the mark, and how many loads it has seen. */
async function survival(page: Page): Promise<{ mark: string; loads: number }> {
  return page.evaluate(() => ({
    mark: (window as MarkedWindow).__documentMark ?? 'replaced',
    loads: performance.getEntriesByType('navigation').length,
  }));
}

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? '');
});

test.describe('a link changes the screen without reloading the document', () => {
  test('opening an investigation expands it where it sits', async ({ page }) => {
    await page.goto('/runs');
    const first = page.getByTestId('run-card-toggle').first();
    await expect(first).toBeVisible();
    await mark(page);

    await first.click();
    await expect(page).toHaveURL(/[?&]selected=/);
    await expect(page.getByTestId('run-card-body')).toBeVisible();

    const after = await survival(page);
    expect(after.mark, 'the document was rebuilt to open a card').toBe('alive');
    expect(after.loads, 'a full page load was issued to open a card').toBe(1);
  });

  test('closing it again is the same navigation in reverse', async ({ page }) => {
    await page.goto('/runs');
    await page.getByTestId('run-card-toggle').first().click();
    await expect(page.getByTestId('run-card-body')).toBeVisible();
    await mark(page);

    await page.getByTestId('run-card-toggle').first().click();
    await expect(page.getByTestId('run-card-body')).toBeHidden();

    const after = await survival(page);
    expect(after.mark, 'the document was rebuilt to close a card').toBe('alive');
    expect(after.loads, 'a full page load was issued to close a card').toBe(1);
  });

  test('sorting a list re-orders it without reloading', async ({ page }) => {
    await page.goto('/knowledge?tab=learned');
    const sort = page.getByTestId('sort').first();
    await expect(sort).toBeVisible();
    await mark(page);

    await sort.click();
    await expect(page).toHaveURL(/[?&]sort=/);

    const after = await survival(page);
    expect(after.mark, 'the document was rebuilt to sort a list').toBe('alive');
    expect(after.loads, 'a full page load was issued to sort a list').toBe(1);
  });

  test('the way out of an empty panel is a transition too', async ({ page }) => {
    // A filter nothing matches, which is the cheapest empty state to reach on
    // a deployment with data in it — and its action is the one somebody in
    // front of an empty screen is most likely to press.
    await page.goto('/runs?status=nothing-matches-this');
    const wayBack = page.getByTestId('way-back').first();
    await expect(wayBack).toBeVisible();
    await mark(page);

    await wayBack.click();
    await expect(page.getByTestId('run-card').first()).toBeVisible();

    const after = await survival(page);
    expect(after.mark, 'the document was rebuilt to leave an empty state').toBe(
      'alive',
    );
    expect(after.loads, 'a full page load was issued to leave an empty state').toBe(1);
  });

  test('a second click while the first is still arriving does not undo it', async ({
    page,
  }) => {
    // The failure this is about: the click registered, the transition took a
    // few hundred milliseconds, nothing on the screen said so, and the reader
    // — reasonably — pressed again. The second press was the toggle's other
    // half, so the card they had just opened closed, and the gesture read as
    // "clicking does nothing". With a document reload the browser swallowed
    // the second press; a router transition does not, so the toggle has to.
    await page.goto('/runs');
    const toggle = page.getByTestId('run-card-toggle').first();
    await expect(toggle).toBeVisible();

    await toggle.click();
    await toggle.click({ delay: 0 });

    await expect(page.getByTestId('run-card-body')).toBeVisible();
    await expect(page).toHaveURL(/[?&]selected=/);
  });

  test('a row opens its own screen without reloading', async ({ page }) => {
    await page.goto('/knowledge?tab=learned');
    const row = page.getByTestId('row').first();
    await expect(row).toBeVisible();
    await mark(page);

    await row.getByRole('link').first().click();
    await expect(page).toHaveURL(/\/runs\//);

    const after = await survival(page);
    expect(after.mark, 'the document was rebuilt to open a row').toBe('alive');
    expect(after.loads, 'a full page load was issued to open a row').toBe(1);
  });
});
