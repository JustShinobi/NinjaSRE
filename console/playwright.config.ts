import { defineConfig, devices } from '@playwright/test';

/**
 * Two projects, because they answer two different questions and only one of
 * them can be trusted on an arbitrary machine.
 *
 * `behaviour` drives a browser against a running console and a running gateway.
 * It asserts what the console does, and it runs anywhere.
 *
 * `visual` compares rendered pixels against committed baselines. Font
 * rasterisation differs between operating systems and between font packages on
 * the same operating system, so a baseline captured anywhere but one pinned
 * container produces differences that mean nothing. `make console-visual` runs
 * this project inside that image and refuses to run it anywhere else.
 *
 * Neither project starts a server. The harness that starts the console and the
 * data behind it is `tools/console_e2e.py` — it is Python because a compose
 * bring-up, a mock data plane and a controlled clock are all things this
 * repository already knows how to do in Python, and because a browser test that
 * also owns process lifecycle is a browser test that hangs.
 */
const baseURL = process.env.NINJASRE_CONSOLE_BASE_URL ?? 'http://127.0.0.1:8423';

export default defineConfig({
  testDir: 'tests',
  // A retry hides a flake, and a hidden flake is why suites get disabled. Any
  // failure here is a defect in the console or in the harness.
  retries: 0,
  workers: 1,
  forbidOnly: true,
  reporter:
    process.env.CI === undefined ? [['list']] : [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    // Fixed, so a viewport that differs between machines cannot be the reason a
    // screenshot differs between machines.
    viewport: { width: 1440, height: 900 },
    timezoneId: 'UTC',
    locale: 'en-GB',
    colorScheme: 'light',
  },
  expect: {
    toHaveScreenshot: {
      // Zero, because a pixel threshold is where a visual gate goes to become
      // advisory. A change that is genuinely fine is accepted as a baseline,
      // in a commit somebody reviewed.
      maxDiffPixels: 0,
      animations: 'disabled',
      caret: 'hide',
      scale: 'css',
    },
  },
  projects: [
    {
      name: 'behaviour',
      testDir: 'tests/e2e',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      // A deployment on its first day, which is a different *dataset* rather
      // than a different kind of test. It needs its own project because one
      // mock plane serves one scenario: the sixty tests in `behaviour` are
      // about a deployment mid-operation and would all fail against an empty
      // one, and these are about the empty one and prove nothing against a
      // full one.
      name: 'first-day',
      testDir: 'tests/first-day',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'visual',
      testDir: 'tests/visual',
      // One directory, not one per platform: the baselines are captured in one
      // image and compared in that same image, so a per-platform directory
      // would only be a place for meaningless captures to accumulate.
      snapshotPathTemplate: 'visual/baselines/{arg}{ext}',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
