import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { serveFixtures } from './fixture-server.mjs';

/**
 * Serve the built console and screenshot it. Runs inside the pinned capture
 * image and nowhere else — `tools/console_visual.py` is what puts it there.
 *
 * The API it hands the console is the committed dataset, served by Node on
 * loopback. It has to be a real address rather than a dead port: the shell
 * resolves the viewer on the *server*, so a console with nothing to talk to
 * captures the sign-in page and proves nothing about the console.
 *
 * The dataset is fixed — every timestamp in it is shifted to one instant — so
 * two runs a week apart produce identical images, which is the property a
 * baseline needs and a live backend cannot give.
 */
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const port = 8425;
const accept = process.argv.includes('--accept');

const fixturePort = 8426;
const scenario = process.env.NINJASRE_FIXTURE_SCENARIO ?? 'populated';

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

const fixtures = await serveFixtures(scenario, fixturePort);

const console_ = spawn(process.execPath, [server], {
  cwd: dirname(server),
  stdio: 'inherit',
  env: {
    ...process.env,
    HOSTNAME: '127.0.0.1',
    PORT: String(port),
    NINJASRE_CONSOLE_API_URL: `http://127.0.0.1:${fixturePort}`,
    NINJASRE_CONSOLE_DEPLOYMENT: 'HAL9000',
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
  fixtures.close();
}

process.exit(status);
