import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// The router, for the components that navigate.
//
// `useRouter` asserts that the App Router is mounted, which it is not in a bare
// `jsdom` render, so every test that renders a panel would fail on the frame
// rather than on what it is testing. A file that is *about* the navigation
// declares its own mock and that one wins; this is the floor beneath it.
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    refresh: () => undefined,
    push: () => undefined,
    replace: () => undefined,
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
  notFound: () => {
    throw new Error('not found');
  },
  redirect: (href: string) => {
    throw new Error(`redirected to ${href}`);
  },
}));

// The library's own auto-cleanup only fires when the runner exposes globals,
// and this one deliberately does not: an import you can see beats a name that
// appears from nowhere. Without this, the second render in a file finds the
// first one's DOM still there and every query returns two of everything.
afterEach(() => {
  cleanup();
});
