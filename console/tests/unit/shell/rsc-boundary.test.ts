import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * A server component may *render* a client component. It may not *call* one.
 *
 * Next refuses to invoke a client export from the server, and the refusal is not
 * a component misbehaving — it is the whole route throwing before it paints
 * anything. This console has shipped that defect three times, each on a
 * different screen, each surviving every unit test in the suite: the component
 * renders perfectly well under `vitest`, which has no boundary to enforce, and
 * only a production build finds it. Twice it reached a deployment.
 *
 * So the rule is checked here rather than hoped for. A pure function two sides
 * need lives in a module with no directive — `stoppage.ts`, `token-identity.ts`,
 * `first-run/tutorial-setting.ts` are the three that exist for exactly this —
 * and both sides import it. A re-export from the client module does not help;
 * it is still a client boundary.
 *
 * Rendering is untouched by this: `<TokenPanel />` in a server component is the
 * normal, correct thing, and the check only looks at call position.
 */

const SOURCE = resolve(__dirname, '../../../src');

/** Every `.ts`/`.tsx` file under `directory`, recursively. */
function sourceFiles(directory: string): readonly string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      found.push(...sourceFiles(path));
    } else if (path.endsWith('.ts') || path.endsWith('.tsx')) {
      found.push(path);
    }
  }
  return found;
}

/** Whether `path` opens with the client directive. */
function isClientModule(path: string): boolean {
  try {
    return /^\s*(['"])use client\1/.test(readFileSync(path, 'utf8'));
  } catch {
    return false;
  }
}

/** The file a relative specifier names, with the extension it is stored under. */
function resolveRelative(fromFile: string, specifier: string): string | null {
  const base = specifier.startsWith('@/')
    ? join(SOURCE, specifier.slice(2))
    : resolve(dirname(fromFile), specifier);
  for (const candidate of [`${base}.tsx`, `${base}.ts`, join(base, 'index.ts')]) {
    try {
      if (statSync(candidate).isFile()) return candidate;
    } catch {
      // Not this extension. The next candidate, or nothing.
    }
  }
  return null;
}

interface Import {
  readonly specifier: string;
  /** Value bindings only — a `type` import is erased and crosses nothing. */
  readonly bindings: readonly string[];
}

function importsOf(source: string): readonly Import[] {
  const found: Import[] = [];
  const pattern = /import\s+([^;]*?)\s+from\s+['"]([^'"]+)['"]/g;
  for (const match of source.matchAll(pattern)) {
    const clause = match[1] ?? '';
    const specifier = match[2] ?? '';
    if (clause.startsWith('type ')) continue;
    const braced = /\{([^}]*)\}/.exec(clause)?.[1] ?? '';
    const bindings = braced
      .split(',')
      .map((part) => part.trim())
      .filter((part) => part !== '' && !part.startsWith('type '))
      .map((part) => (part.split(/\s+as\s+/)[1] ?? part).trim());
    found.push({ specifier, bindings });
  }
  return found;
}

/** Whether `source` calls `name` as a function rather than rendering it. */
function callsIt(source: string, name: string): boolean {
  // Deliberately not "mentions": `<TokenPanel />` and `{TokenPanel}` are both
  // fine. Only `name(` is the thing Next refuses.
  return new RegExp(`(^|[^.\\w<])${name}\\s*\\(`, 'm').test(source);
}

describe('the server/client boundary', () => {
  const serverFiles = sourceFiles(SOURCE).filter((path) => !isClientModule(path));

  it('has server modules to check, so a green run means something', () => {
    expect(serverFiles.length).toBeGreaterThan(20);
  });

  it('never calls a client export from a server module', () => {
    const offences: string[] = [];
    for (const path of serverFiles) {
      const source = readFileSync(path, 'utf8');
      for (const { specifier, bindings } of importsOf(source)) {
        if (!specifier.startsWith('.') && !specifier.startsWith('@/')) continue;
        const target = resolveRelative(path, specifier);
        if (target === null || !isClientModule(target)) continue;
        for (const binding of bindings) {
          if (callsIt(source, binding)) {
            offences.push(
              `${path.slice(SOURCE.length + 1)} calls ${binding}(), which '${specifier}' exports from a 'use client' module`,
            );
          }
        }
      }
    }

    expect(offences, offences.join('\n')).toEqual([]);
  });
});
