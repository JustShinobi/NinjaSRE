import { expect, test, type Page } from '@playwright/test';

import { signIn } from './session';

/**
 * The board's visual language, proved against a running console rather than
 * assumed from the token table alone.
 *
 * Sixteen claims, one block each: the two themes' resolved colours, the three
 * font stacks actually painting, the zero-egress property, the chip's new
 * outline, the seven status shapes, the live pulse, reduced motion silencing
 * every primitive, the shell's measurements and control order, the radius
 * scale as rendered, the contrast and name-parity properties measured against
 * what the browser actually resolves (not only what the source module
 * declares), and the theme toggle itself.
 *
 * **This spec is expected to be comprehensively red when it is written.** The
 * token table still carries the previous palette, radii, shell measurements
 * and font stacks; the chip has no border yet; the three motion primitives
 * are declared in part (`pulse-live` exists already) or not at all
 * (`slide-in`, `stage-shimmer`). Every task after this one exists to turn one
 * block of this file green.
 *
 * The theme is set by writing the same storage key `design/theme.ts` reads
 * before navigation (`page.addInitScript`), for every claim except the one
 * that is specifically about the topbar's own toggle — that one drives the
 * real button, because the button is what it is proving.
 */

const STAGING_SAFE_TAG = '@staging-safe';

/** The storage key `NO_FLASH_SCRIPT` reads before first paint. Mirrors `design/theme.ts`. */
const THEME_STORAGE_KEY = 'ninjasre.theme';

test.use({ viewport: { width: 1920, height: 1080 } });

test.beforeEach(async ({ context, baseURL }) => {
  await signIn(context, baseURL ?? 'http://127.0.0.1:8423');
});

/** Load `route` with `theme` already the stored choice, so the first paint carries it. */
async function gotoWithTheme(
  page: Page,
  route: string,
  theme: 'light' | 'dark',
): Promise<void> {
  await page.addInitScript(
    ([key, value]) => {
      window.localStorage.setItem(key, value);
    },
    [THEME_STORAGE_KEY, theme] as const,
  );
  await page.goto(route);
}

/** One token, read as the browser resolves it right now. */
async function tokenValue(page: Page, name: string): Promise<string> {
  return page.evaluate(
    (property) =>
      getComputedStyle(document.documentElement).getPropertyValue(property).trim(),
    `--${name}`,
  );
}

/** `#rrggbb` as the three-integer form a computed style reports. */
function rgbOf(hex: string): string {
  const value = hex.replace('#', '');
  const r = Number.parseInt(value.slice(0, 2), 16);
  const g = Number.parseInt(value.slice(2, 4), 16);
  const b = Number.parseInt(value.slice(4, 6), 16);
  return `rgb(${String(r)}, ${String(g)}, ${String(b)})`;
}

// =============================================================================
// AN-01 / AN-02 — the board's palette, resolved, in both themes
// =============================================================================

test.describe('the board palette resolves in both themes', () => {
  test(
    'dark: --sunken, --surface and --accent resolve to the board hexes',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await gotoWithTheme(page, '/', 'dark');
      expect(await tokenValue(page, 'sunken'), '--sunken in dark').toBe('#0a100e');
      expect(await tokenValue(page, 'surface'), '--surface in dark').toBe('#101815');
      expect(await tokenValue(page, 'accent'), '--accent in dark').toBe('#3ad195');
    },
  );

  test(
    'light: --sunken and --accent resolve to the board hexes',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await gotoWithTheme(page, '/', 'light');
      expect(await tokenValue(page, 'sunken'), '--sunken in light').toBe('#f2f6f4');
      expect(await tokenValue(page, 'accent'), '--accent in light').toBe('#0a7452');
    },
  );
});

// =============================================================================
// AN-03 / AN-04 / AN-05 — the three families, painting
// =============================================================================

test.describe('the three type families paint, not only the fallback', () => {
  test(
    'the body computes IBM Plex Sans first',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/');
      const family = await page.evaluate(
        () => getComputedStyle(document.body).fontFamily,
      );
      expect(family, `body font-family is "${family}"`).toMatch(/^["']?IBM Plex Sans/);
    },
  );

  test(
    "a page's H1 computes Space Grotesk first",
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/');
      const h1 = page.locator('h1').first();
      await expect(h1).toBeVisible();
      const family = await h1.evaluate((node) => getComputedStyle(node).fontFamily);
      expect(family, `h1 font-family is "${family}"`).toMatch(/^["']?Space Grotesk/);
    },
  );

  test(
    'an identifier computes IBM Plex Mono first',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/runs');
      const identifier = page.locator('.font-mono').first();
      await expect(identifier).toBeVisible();
      const family = await identifier.evaluate(
        (node) => getComputedStyle(node).fontFamily,
      );
      expect(family, `identifier font-family is "${family}"`).toMatch(
        /^["']?IBM Plex Mono/,
      );
    },
  );
});

// =============================================================================
// AN-06 — zero egress, on the three routes SC-004 names
// =============================================================================

const LOCAL_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]', '0.0.0.0']);

/**
 * Every request the load made to somewhere this deployment does not serve.
 *
 * The origin has to come from the run rather than from a list of names. A
 * hard-coded set of loopback hosts answers "did this reach a non-localhost
 * host", which is the same question only while the console is served from a
 * laptop: against a real deployment every stylesheet, chunk and self-hosted
 * font counts as foreign, and the assertion fails while reporting its own
 * origin back as the offender. The property under test is third-party egress,
 * so the deployment's own host is what the list is measured against.
 */
function trackExternal(page: Page, baseURL: string | undefined): string[] {
  const external: string[] = [];
  const home = baseURL === undefined ? '' : new URL(baseURL).host;
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.protocol === 'data:' || url.protocol === 'blob:') return;
    if (url.host === home) return;
    if (!LOCAL_HOSTS.has(url.hostname)) external.push(request.url());
  });
  return external;
}

test.describe('no page load reaches a host this deployment does not run', () => {
  for (const route of ['/', '/incidents', '/runs'] as const) {
    test(
      `the load of ${route} issues no request outside the origin`,
      { tag: STAGING_SAFE_TAG },
      async ({ page, baseURL }) => {
        const external = trackExternal(page, baseURL);
        await page.goto(route);
        await page.waitForLoadState('networkidle');
        expect(external, `${route} requested ${external.join(', ')}`).toEqual([]);
      },
    );
  }
});

// =============================================================================
// AN-07 / AN-08 — the chip's outline, and the seven shapes
// =============================================================================

/** The role each `Badge` on `/gallery` carries, by the resource status it was given. */
const GALLERY_STATUS_ROLE: Readonly<Record<string, string>> = {
  healthy: 'success',
  degraded: 'warning',
  unhealthy: 'danger',
  unknown: 'neutral',
  stale: 'neutral',
  maintenance: 'info',
  absent: 'neutral',
};

/** The shape each of `RESOURCE_STATUSES` carries — see `design/status.ts#DECLARED`. */
const GALLERY_STATUS_SHAPE: Readonly<Record<string, string>> = {
  healthy: 'filled-circle',
  degraded: 'triangle',
  unhealthy: 'square',
  unknown: 'hollow-circle',
  stale: 'dimmed-circle',
  maintenance: 'rotated-square',
  absent: 'dash',
};

/** The board's own hex for `role`'s foreground, read from the token table's published values. */
const ROLE_HEX: Readonly<Record<string, string>> = {
  success: '#0a7452',
  warning: '#8a5a12',
  danger: '#a51f1f',
  info: '#0a5f8f',
  neutral: '#55645e',
};

test.describe('every status chip carries a 1px border in its own role colour', () => {
  test(
    'each badge on the design-system route carries its role border, in light',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await gotoWithTheme(page, '/gallery', 'light');
      for (const [status, role] of Object.entries(GALLERY_STATUS_ROLE)) {
        const badge = page.locator(`[data-role="${role}"][data-known="true"]`).first();
        // Several statuses share a role (unknown/stale/absent are all
        // neutral); each is still drawn as a chip that carries a border.
        void status;
        await expect(
          badge,
          `no rendered badge carries data-role="${role}"`,
        ).toHaveCount(1);
        const border = await badge.evaluate((node) => {
          const style = getComputedStyle(node);
          return { width: style.borderTopWidth, color: style.borderTopColor };
        });
        expect(border.width, `${role} chip border-width is "${border.width}"`).toBe(
          '1px',
        );
        const expectedHex = ROLE_HEX[role];
        if (expectedHex !== undefined) {
          expect(
            border.color,
            `${role} chip border-color is "${border.color}", expected ${rgbOf(expectedHex)}`,
          ).toBe(rgbOf(expectedHex));
        }
      }
    },
  );
});

test.describe('the seven status shapes render, and stay distinct', () => {
  test(
    'the seven declared shapes each appear at least once, on the design-system route',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/gallery');
      const shapes = new Set(Object.values(GALLERY_STATUS_SHAPE));
      expect(shapes.size, 'the seven shapes are not seven distinct names').toBe(7);
      for (const shape of shapes) {
        const mark = page.locator(`[data-shape="${shape}"]`).first();
        await expect(
          mark,
          `no element on /gallery carries data-shape="${shape}"`,
        ).toHaveCount(1);
      }
    },
  );
});

// =============================================================================
// AN-09 — the "live" chip's pulsing mark
// =============================================================================

test.describe('the freshness chip pulses while the stream is connected', () => {
  test(
    'the live state carries the pulsing mark',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/');
      const freshness = page.getByTestId('freshness');
      await expect(freshness).toBeVisible();
      // The state starts live and only degrades on a failed re-read, so the
      // freshly loaded page is the moment to look.
      await expect(freshness).toHaveAttribute('data-state', 'live');
      const pulse = freshness.locator('.pulse-live');
      await expect(pulse, 'the live mark carries no .pulse-live class').toHaveCount(1);
      const ring = freshness.locator('.pulse-live-ring');
      await expect(ring, 'the live mark has no expanding ring child').toHaveCount(1);
    },
  );
});

// =============================================================================
// AN-10 — prefers-reduced-motion silences all three primitives
// =============================================================================

/** Create a bare probe element carrying `className`, appended to `<body>`, and return its id. */
async function probe(page: Page, className: string): Promise<string> {
  return page.evaluate((cls) => {
    const node = document.createElement('div');
    const id = `probe-${cls}`;
    node.id = id;
    node.className = cls;
    document.body.appendChild(node);
    return id;
  }, className);
}

async function animationNameOf(page: Page, id: string): Promise<string> {
  return page.evaluate(
    (elementId) =>
      getComputedStyle(document.getElementById(elementId) as Element).animationName,
    id,
  );
}

test.describe('every motion primitive is real motion, until reduced motion asks otherwise', () => {
  test('pulse-live, slide-in and stage-shimmer each carry a real animation name', async ({
    page,
  }) => {
    await page.goto('/');
    for (const className of ['pulse-live-ring', 'slide-in', 'stage-shimmer']) {
      const id = await probe(page, className);
      const name = await animationNameOf(page, id);
      expect(name, `.${className} computes animation-name "${name}"`).not.toBe('none');
    }
  });

  test('prefers-reduced-motion: reduce resolves all three to animation: none', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');
    for (const className of ['pulse-live-ring', 'slide-in', 'stage-shimmer']) {
      const id = await probe(page, className);
      const name = await animationNameOf(page, id);
      expect(name, `under reduced motion, .${className} still computes "${name}"`).toBe(
        'none',
      );
    }
  });
});

// =============================================================================
// AN-11 / AN-12 — the shell's measurements, groups and control order
// =============================================================================

test.describe('the sidebar measures 232px, with three named groups and the guardian footer', () => {
  test(
    'sidebar width, group labels and the guardian mark',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/');
      const sidebar = page.getByTestId('sidebar');
      await expect(sidebar).toBeVisible();
      const width = await sidebar.evaluate(
        (node) => node.getBoundingClientRect().width,
      );
      expect(width, `sidebar width is ${String(width)}px`).toBe(232);

      const labels = await sidebar.locator('p.text-micro').allInnerTexts();
      expect(labels.length, 'the sidebar does not render three group labels').toBe(3);

      const guardian = page.getByTestId('guardian');
      await expect(guardian, 'no guardian footer renders in the sidebar').toHaveCount(
        1,
      );
      await expect(guardian.locator('[data-shape]')).toHaveCount(1);
    },
  );
});

test.describe('the topbar measures 60px and keeps the board control order', () => {
  test(
    'topbar height, and the eight controls left to right',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/');
      const topbar = page.getByTestId('topbar');
      await expect(topbar).toBeVisible();
      const height = await topbar.evaluate(
        (node) => node.getBoundingClientRect().height,
      );
      expect(height, `topbar height is ${String(height)}px`).toBe(60);

      const order = [
        'open-palette',
        'freshness',
        'theme-switch',
        'density-switch',
        'open-notifications',
        // Whichever the kill-switch draws for the dataset's current state.
        'engage-stop, stop-banner',
        'investigate',
        'account',
      ];
      const xs: number[] = [];
      for (const testId of order) {
        const selector = testId.includes(',')
          ? testId
              .split(',')
              .map((part) => `[data-testid="${part.trim()}"]`)
              .join(', ')
          : `[data-testid="${testId}"]`;
        const control = page.locator(selector).first();
        await expect(control, `no control matches ${selector}`).toBeVisible();
        const box = await control.boundingBox();
        expect(box, `${selector} has no bounding box`).not.toBeNull();
        xs.push(box?.x ?? Number.NaN);
      }
      for (let index = 1; index < xs.length; index += 1) {
        expect(
          (xs[index] ?? Number.NaN) > (xs[index - 1] ?? Number.NaN),
          `control ${String(index)} (${order[index] ?? ''}) does not sit to the right of the previous one — order is ${JSON.stringify(xs)}`,
        ).toBe(true);
      }
    },
  );
});

// =============================================================================
// AN-13 — the radius scale, as the browser actually renders it
// =============================================================================

test.describe('the radius scale renders 6 / 8 / 12 / 16, chip through panel', () => {
  test(
    'a rectangular chip, a control, a card and a panel each carry their step',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/');

      const chip = page.getByTestId('open-palette').locator('kbd');
      await expect(chip, 'the search shortcut kbd is not rendered').toHaveCount(1);
      expect(await chip.evaluate((node) => getComputedStyle(node).borderRadius)).toBe(
        '6px',
      );

      const control = page.getByTestId('open-palette');
      expect(
        await control.evaluate((node) => getComputedStyle(node).borderRadius),
      ).toBe('8px');

      await page.getByTestId('account').locator('summary').click();
      const card = page.getByTestId('account').locator('> div');
      await expect(card).toBeVisible();
      expect(await card.evaluate((node) => getComputedStyle(node).borderRadius)).toBe(
        '12px',
      );

      await page.getByTestId('investigate').click();
      const panel = page.getByRole('dialog');
      await expect(panel, 'the investigate control opened no dialog').toBeVisible();
      expect(await panel.evaluate((node) => getComputedStyle(node).borderRadius)).toBe(
        '16px',
      );
    },
  );
});

// =============================================================================
// AN-14 — contrast, measured against what the browser resolves
// =============================================================================

const SEMANTIC = ['success', 'warning', 'danger', 'info', 'neutral'] as const;
const GROUNDS = ['surface', 'sunken', 'raised', 'hover'] as const;

/**
 * WCAG 2.1 contrast, computed client-side against rendered `rgb(r, g, b)`
 * strings — ordinary nested functions inside the page, not a string eval:
 * this is the same arithmetic `design/contrast.ts` carries, reproduced here
 * so the claim is proved against what the browser actually painted (a real
 * element's resolved `color`), not only against the source module.
 */
async function resolvedPairs(
  page: Page,
): Promise<{ readonly body: number; readonly boundary: number }> {
  return page.evaluate(
    ({ semantic, grounds }) => {
      function channels(rgb: string): readonly [number, number, number] {
        const match = /rgba?\(([^)]+)\)/.exec(rgb);
        if (match === null) throw new Error(`not an rgb() colour: ${rgb}`);
        const parts = (match[1] ?? '')
          .split(',')
          .map((part) => Number.parseFloat(part.trim()));
        return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0];
      }
      function linear(channel: number): number {
        const p = channel / 255;
        return p <= 0.04045 ? p / 12.92 : ((p + 0.055) / 1.055) ** 2.4;
      }
      function luminance(rgb: string): number {
        const [r, g, b] = channels(rgb);
        return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
      }
      function ratio(fg: string, bg: string): number {
        const a = luminance(fg);
        const b = luminance(bg);
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
      }

      const style = getComputedStyle(document.documentElement);
      const at = (name: string): string => style.getPropertyValue(`--${name}`).trim();
      // The token stylesheet publishes hex; resolve each through a throwaway
      // element so the same arithmetic reads what a real border or text
      // colour would actually be painted as.
      const probeEl = document.createElement('div');
      document.body.appendChild(probeEl);
      const asRgb = (hex: string): string => {
        probeEl.style.color = hex;
        return getComputedStyle(probeEl).color;
      };
      let worstBody = Number.POSITIVE_INFINITY;
      for (const ground of grounds) {
        const bg = asRgb(at(ground));
        worstBody = Math.min(worstBody, ratio(asRgb(at('text')), bg));
        worstBody = Math.min(worstBody, ratio(asRgb(at('muted')), bg));
        for (const role of semantic) {
          worstBody = Math.min(worstBody, ratio(asRgb(at(role)), bg));
        }
        worstBody = Math.min(worstBody, ratio(asRgb(at('accent')), bg));
      }
      worstBody = Math.min(
        worstBody,
        ratio(asRgb(at('on-accent')), asRgb(at('accent'))),
      );
      for (const role of semantic) {
        worstBody = Math.min(
          worstBody,
          ratio(asRgb(at(`on-${role}`)), asRgb(at(role))),
        );
        worstBody = Math.min(
          worstBody,
          ratio(asRgb(at(role)), asRgb(at(`${role}-bg`))),
        );
      }
      // `border-strong` against a ground is excluded here: the board
      // publishes it at a value that does not clear 3:1 against any of the
      // four grounds, and the operator ruled the palette stands — nowhere
      // does the board carry a control or a state by this boundary alone.
      // `tests/unit/design/contrast.test.ts` measures and pins the exact
      // ratio as a named exemption; this browser-level check covers every
      // boundary pair the exemption does not touch.
      let worstBoundary = Number.POSITIVE_INFINITY;
      for (const role of semantic) {
        worstBoundary = Math.min(
          worstBoundary,
          ratio(asRgb(at(role)), asRgb(at(`${role}-bg`))),
        );
      }
      probeEl.remove();
      return { body: worstBody, boundary: worstBoundary };
    },
    { semantic: SEMANTIC, grounds: GROUNDS },
  );
}

test.describe('the tokens as served reach their contrast minimums, in both themes', () => {
  for (const theme of ['light', 'dark'] as const) {
    test(`${theme}: every body pair reaches 4.5:1 and every non-exempt boundary reaches 3:1`, async ({
      page,
    }) => {
      await gotoWithTheme(page, '/', theme);
      const { body, boundary } = await resolvedPairs(page);
      expect(
        body,
        `${theme} worst body pair is ${body.toFixed(3)}:1`,
      ).toBeGreaterThanOrEqual(4.5);
      expect(
        boundary,
        `${theme} worst boundary pair is ${boundary.toFixed(3)}:1`,
      ).toBeGreaterThanOrEqual(3);
    });
  }
});

// =============================================================================
// AN-15 — both themes declare exactly the same token names
// =============================================================================

/** The `--name` declarations inside one `[data-theme="…"]` block of the rendered stylesheet. */
function namesIn(css: string, theme: 'light' | 'dark'): string[] {
  const opening = css.indexOf(`[data-theme="${theme}"]`);
  const start = css.indexOf('{', opening);
  let depth = 0;
  let end = start;
  for (let index = start; index < css.length; index += 1) {
    if (css[index] === '{') depth += 1;
    if (css[index] === '}') {
      depth -= 1;
      if (depth === 0) {
        end = index;
        break;
      }
    }
  }
  const block = css.slice(start + 1, end);
  return [...block.matchAll(/--([a-z0-9-]+):/g)].map((match) => match[1] ?? '');
}

test.describe('both themes declare exactly the same token names', () => {
  test('the light and dark blocks of the rendered stylesheet name the same set', async ({
    page,
  }) => {
    await page.goto('/');
    const css = await page.evaluate(
      () => document.querySelector('[data-testid="tokens"]')?.textContent ?? '',
    );
    expect(css.length, 'the token stylesheet is not in the document').toBeGreaterThan(
      0,
    );
    const light = new Set(namesIn(css, 'light'));
    const dark = new Set(namesIn(css, 'dark'));
    expect(light.size, 'the light block declares no token names').toBeGreaterThan(20);
    expect([...light].sort()).toEqual([...dark].sort());
  });
});

// =============================================================================
// AN-16 — the theme toggle itself, without a reload
// =============================================================================

test.describe('the topbar theme button swaps --accent without a reload', () => {
  test(
    'clicking the theme control cycles --accent between the board hexes, in place',
    { tag: STAGING_SAFE_TAG },
    async ({ page }) => {
      await page.goto('/');
      // A marker a real navigation would clear, so "no reload" is measured
      // rather than assumed.
      await page.evaluate(() => {
        (
          window as unknown as { __fundacaoVisualMarker?: boolean }
        ).__fundacaoVisualMarker = true;
      });

      const button = page.getByTestId('theme-switch');
      const seen = new Set<string>();
      for (let clicks = 0; clicks < 3 && seen.size < 2; clicks += 1) {
        await button.click();
        seen.add(await tokenValue(page, 'accent'));
      }
      expect(
        [...seen].sort(),
        `cycling the theme control only ever produced --accent values ${JSON.stringify([...seen])}`,
      ).toEqual(['#0a7452', '#3ad195']);

      const survived = await page.evaluate(
        () =>
          (window as unknown as { __fundacaoVisualMarker?: boolean })
            .__fundacaoVisualMarker,
      );
      expect(survived, 'the marker did not survive — the page reloaded').toBe(true);
    },
  );
});
