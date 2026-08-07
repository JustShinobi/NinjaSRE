import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

/**
 * The unit runner: in process, with a DOM, and with a coverage floor that fails
 * rather than reports.
 *
 * The threshold is 90 and is asserted against `config/constants/console.py` by
 * the Python suite, so lowering it is a two-file change that shows up in review
 * rather than a number somebody edits on the way past.
 *
 * The generated API client is excluded from coverage: it is types, it is
 * generated, and a drift check already proves it is the current one. Counting
 * it would let the real modules' coverage fall while the number went up.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    include: ['tests/unit/**/*.test.ts', 'tests/unit/**/*.test.tsx'],
    setupFiles: ['tests/unit/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'lcov'],
      include: ['src/**/*.ts', 'src/**/*.tsx'],
      exclude: ['src/api/schema.ts'],
      thresholds: {
        lines: 90,
        statements: 90,
        functions: 90,
        branches: 90,
      },
    },
  },
});
