/**
 * The half of the no-literals rule that ESLint cannot see.
 *
 * ESLint parses JavaScript. The console's stylesheets are CSS, and a stylesheet
 * is the easiest place in the tree to write `#0f6f5c` and have nobody notice —
 * which would leave the lint rule policing the components and blind to the file
 * that styles them.
 *
 * So the same detection runs over every stylesheet, with one exception that is
 * the point rather than a hole: a line declaring a custom property is where a
 * value is allowed to be written, because that is what a token is. Anything
 * else has to reference one.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

import { findings } from '../eslint-rules/no-design-literals.mjs';

const ROOT = new URL('..', import.meta.url).pathname;
const SOURCE = join(ROOT, 'src');

/** Every stylesheet under `directory`. */
function stylesheets(directory) {
  const found = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      found.push(...stylesheets(path));
    } else if (entry.endsWith('.css')) {
      found.push(path);
    }
  }
  return found;
}

/**
 * Whether `line` is where a value is allowed to be written.
 *
 * A custom-property declaration is a token being defined. A Tailwind theme
 * entry is a token being exposed, and it is asserted separately to contain no
 * value at all. Everything else is a component, and a component names tokens.
 */
function declaresAToken(line) {
  return /^\s*--[a-z0-9-]+\s*:/.test(line);
}

let failures = 0;
for (const path of stylesheets(SOURCE)) {
  const lines = readFileSync(path, 'utf8').split('\n');
  lines.forEach((line, index) => {
    if (declaresAToken(line)) return;
    for (const [kind, value] of findings(line, { styled: true })) {
      failures += 1;
      process.stderr.write(
        `${relative(ROOT, path)}:${String(index + 1)}  ${kind}  ${value}\n` +
          `  A stylesheet may write a value only when declaring a token. Reference one instead.\n`,
      );
    }
  });
}

if (failures > 0) {
  process.stderr.write(
    `\n${String(failures)} design literal(s) in the console's stylesheets.\n`,
  );
  process.exit(1);
}
