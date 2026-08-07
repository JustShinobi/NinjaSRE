import nextWebVitals from 'eslint-config-next/core-web-vitals';
import tseslint from 'typescript-eslint';

/**
 * The console's lint rules.
 *
 * Type-aware rules are on. The whole reason a TypeScript surface was allowed
 * into this repository is that it can be held to the same standard as the
 * Python, and a lint configuration that never reads the type checker's output
 * is not that standard.
 *
 * `fixtures/` is excluded: it holds files that are broken on purpose, so that
 * the suite can prove each check actually fails rather than assuming it would.
 */
export default tseslint.config(
  {
    ignores: [
      '.next/**',
      '.toolchain/**',
      'coverage/**',
      'node_modules/**',
      'test-results/**',
      'playwright-report/**',
      'fixtures/**',
      'src/api/schema.ts',
      'next-env.d.ts',
    ],
  },
  ...nextWebVitals,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Angle-bracket assertions and asserted object literals are the two
      // kinds that hide a mistake rather than narrow a value: the first is
      // ambiguous with JSX, the second silently accepts a missing field.
      '@typescript-eslint/consistent-type-assertions': [
        'error',
        { assertionStyle: 'as', objectLiteralTypeAssertions: 'never' },
      ],
      '@typescript-eslint/explicit-module-boundary-types': 'error',
      '@typescript-eslint/no-non-null-assertion': 'error',
      // An unawaited promise in a component is a race nobody sees until it is
      // slow enough to lose.
      '@typescript-eslint/no-floating-promises': 'error',
      'no-restricted-syntax': [
        'error',
        {
          // Every asset is bundled and served by the deployment. A literal
          // external origin in source is how that stops being true.
          selector: 'Literal[value=/^https?:\\/\\/(?!localhost|127\\.0\\.0\\.1)/]',
          message:
            'No third-party origin in console source. Every asset is bundled and every request goes to the deployment.',
        },
      ],
    },
  },
  {
    // The configuration files are ES modules outside the TypeScript project, so
    // there is no type information to lint them against. Linting them without
    // it is still worth doing; pretending otherwise is what breaks the run.
    files: ['**/*.mjs'],
    ...tseslint.configs.disableTypeChecked,
  },
  {
    files: ['tests/**/*.ts', 'tests/**/*.tsx'],
    rules: {
      // A test asserting a rejected promise reads better with the assertion
      // holding the promise than with a floating await in front of it.
      '@typescript-eslint/no-floating-promises': 'off',
    },
  },
);
