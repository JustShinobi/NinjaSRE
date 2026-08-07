import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// The library's own auto-cleanup only fires when the runner exposes globals,
// and this one deliberately does not: an import you can see beats a name that
// appears from nowhere. Without this, the second render in a file finds the
// first one's DOM still there and every query returns two of everything.
afterEach(() => {
  cleanup();
});
