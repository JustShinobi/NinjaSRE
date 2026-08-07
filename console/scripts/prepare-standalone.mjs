import { cp, mkdir, stat } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Finish the standalone build into something a deployment can actually run.
 *
 * The standalone output carries the server and the module graph it needs, but
 * not the static assets — the build leaves those where a CDN would have picked
 * them up. Nothing here is served by a CDN, so they are copied in, and what
 * comes out of `make console-build` is a directory the deployment runs with the
 * pinned Node and nothing else installed.
 */
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const standalone = join(root, '.next', 'standalone');

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

if (!(await exists(standalone))) {
  throw new Error(
    `${standalone} is missing; the build did not produce a standalone output`,
  );
}

await mkdir(join(standalone, '.next'), { recursive: true });
await cp(join(root, '.next', 'static'), join(standalone, '.next', 'static'), {
  recursive: true,
});

if (await exists(join(root, 'public'))) {
  await cp(join(root, 'public'), join(standalone, 'public'), { recursive: true });
}
