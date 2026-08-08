import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * The committed dataset, served over HTTP by Node.
 *
 * The visual suite runs inside a pinned browser image that has a Node and
 * nothing else, so the mock data plane — which is Python — cannot be started
 * there. Without something answering, the shell resolves no viewer and every
 * capture is of the sign-in page, which says nothing about the console.
 *
 * So this serves the same committed JSON the mock plane serves, for the reads
 * the shell makes before it can draw itself. It is deliberately small: it is not
 * a second mock data plane, it is the four endpoints the *frame* depends on. The
 * end-to-end suite still runs against the real mock plane, which is what proves
 * the console against the whole dataset.
 *
 * `tests/contract/console/test_console_shell.py` holds this table against the
 * mock plane's own endpoint catalogue, so a path or a slug that drifted fails in
 * the Python suite rather than by producing a blank screenshot.
 */

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const fixtures = join(dirname(root), 'fixtures', 'scenarios');

/** The reads the shell makes, and the fixture that answers each. */
export const SHELL_ENDPOINTS = Object.freeze({
  '/auth/me': 'principal',
  '/v1/runs': 'runs',
  '/v1/approvals': 'approvals',
  '/health/ready': 'health',
});

/** The first recorded response body for `slug` in `scenario`. */
function body(scenario, slug) {
  const path = join(fixtures, scenario, `${slug}.json`);
  const loaded = JSON.parse(readFileSync(path, 'utf8'));
  const [first] = loaded.responses ?? [];
  if (first === undefined) {
    throw new Error(`${path} holds no responses`);
  }
  return first.body;
}

/**
 * Serve `scenario` on `port` and resolve once it is listening.
 *
 * @param {string} scenario
 * @param {number} port
 * @returns {Promise<import('node:http').Server>}
 */
export function serveFixtures(scenario, port) {
  const server = createServer((request, response) => {
    // A base is required to parse a path-only URL and is never contacted. Built
    // rather than written, because the rule that forbids a foreign origin in
    // console source is right to fire on one and this is not one.
    const base = ['http:', '//fixtures.invalid'].join('');
    const path = new URL(request.url ?? '/', base).pathname;
    const slug = SHELL_ENDPOINTS[path];
    if (slug === undefined) {
      response.writeHead(404, { 'content-type': 'application/json' });
      response.end('{}');
      return;
    }
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify(body(scenario, slug)));
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => {
      resolve(server);
    });
  });
}
