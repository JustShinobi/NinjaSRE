import nextWebVitals from 'eslint-config-next/core-web-vitals';
import tseslint from 'typescript-eslint';

import design from './eslint-rules/no-design-literals.mjs';
import i18n from './eslint-rules/no-untranslated-strings.mjs';

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
    // The no-literals rule, over the console's own source.
    //
    // Only `src/`: the tests state the values the design publishes and compare
    // them against the table, which is the opposite of hard-coding one, and a
    // rule that forbade it would forbid the assertion that keeps the table
    // honest.
    files: ['src/**/*.ts', 'src/**/*.tsx'],
    plugins: { design },
    rules: {
      'design/no-design-literals': 'error',
    },
  },
  {
    // The no-untranslated-strings rule, over every surface a viewer reaches.
    //
    // The three design-system modules listed alongside the surfaces are the ones
    // the shell renders *through* — the drawer's dismiss control, the account
    // menu's avatar, the route error boundary's panel. Their strings were lifted
    // to required props so that even those sentences come from the catalogue.
    // The primitives no surface renders yet keep theirs until the screen that
    // shows them arrives; a sentence nobody has been shown is not a sentence
    // anybody has read in the wrong language.
    files: [
      'src/app/**/*.tsx',
      'src/shell/**/*.ts',
      'src/shell/**/*.tsx',
      'src/session/**/*.ts',
      'src/i18n/**/*.ts',
      'src/live/**/*.ts',
      'src/live/**/*.tsx',
      'src/components/navigation.tsx',
      'src/components/overlay.tsx',
      'src/components/state.tsx',
      // The live layer is the first thing to render a toast, so the toast's own
      // sentence comes from the catalogue from here on.
      'src/components/feedback.tsx',
    ],
    plugins: { i18n },
    rules: {
      'i18n/no-untranslated-strings': 'error',
    },
  },
  {
    // The gallery is not part of the console: nothing links to it, a test
    // asserts that, and its whole job is to name and describe each primitive for
    // whoever is building a screen. Its labels are documentation, in the one
    // language this repository is written in.
    files: ['src/gallery/**/*.tsx', 'src/app/gallery/**/*.tsx'],
    rules: {
      'i18n/no-untranslated-strings': 'off',
    },
  },
  {
    // The two files where a value is *declared* rather than used. This is the
    // whole exemption: the token table is the design, and the renderer turns it
    // into custom properties. Everything downstream names a token.
    files: ['src/design/tokens.ts', 'src/design/css.ts'],
    rules: {
      'design/no-design-literals': 'off',
    },
  },
  {
    // The configuration files are ES modules outside the TypeScript project, so
    // there is no type information to lint them against. Linting them without
    // it is still worth doing; pretending otherwise is what breaks the run.
    files: ['**/*.mjs'],
    ...tseslint.configs.disableTypeChecked,
    rules: {
      ...tseslint.configs.disableTypeChecked.rules,
      // JavaScript has no type annotations to write, so the rule can only ever
      // be satisfied by moving the file into the TypeScript project — and an
      // ESLint rule module cannot live there, because the lint configuration
      // that loads it is itself JavaScript.
      '@typescript-eslint/explicit-module-boundary-types': 'off',
    },
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
