import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Serve the built console and screenshot it. Runs inside the pinned capture
 * image and nowhere else — `tools/console_visual.py` is what puts it there.
 *
 * The API address it hands the console is a loopback port nothing listens on.
 * That is deliberate: the visual suite intercepts every request in the browser
 * and answers from the committed dataset, so a screen that reached past the
 * interception would render its failure state and the difference would say so
 * loudly. A capture suite that quietly fell back to a live backend is one whose
 * baselines drift with the data.
 */
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const port = 8425;
const accept = process.argv.includes('--accept');

const server = join(root, '.next', 'standalone', 'server.js');
if (!existsSync(server)) {
  console.error(`${server} is missing; run the build before capturing.`);
  process.exit(2);
}

/** Resolve once the port answers, or reject after `attempts` quarter-seconds. */
async function waitFor(url, attempts = 240) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      await fetch(url);
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
  throw new Error(`${url} did not answer`);
}

const console_ = spawn(process.execPath, [server], {
  cwd: dirname(server),
  stdio: 'inherit',
  env: {
    ...process.env,
    HOSTNAME: '127.0.0.1',
    PORT: String(port),
    NINJASRE_CONSOLE_API_URL: 'http://127.0.0.1:9',
  },
});

let status = 1;
try {
  await waitFor(`http://127.0.0.1:${port}/`);
  status = await new Promise((resolve) => {
    const suite = spawn(
      process.execPath,
      [
        join(root, 'node_modules', '@playwright', 'test', 'cli.js'),
        'test',
        '--project=visual',
        ...(accept ? ['--update-snapshots'] : []),
      ],
      {
        cwd: root,
        stdio: 'inherit',
        env: {
          ...process.env,
          NINJASRE_CONSOLE_BASE_URL: `http://127.0.0.1:${port}`,
        },
      },
    );
    suite.on('exit', (code) => {
      resolve(code ?? 1);
    });
  });
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  status = 2;
} finally {
  console_.kill();
}

process.exit(status);
