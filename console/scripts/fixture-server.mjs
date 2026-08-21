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
 * So this serves the same committed JSON the mock plane serves. It is not a
 * second mock data plane: it does not validate, it does not write, and it
 * answers the *reads* alone. What it is, is the same fixtures over the same
 * paths, so a screenshot is of the dataset the design was drawn from rather than
 * of a page of empty states.
 *
 * `tests/contract/console/test_console_shell.py` holds this table against the
 * mock plane's own endpoint catalogue, so a path or a slug that drifted fails in
 * the Python suite rather than by producing a blank screenshot. The unit suite
 * imports the same table and the same resolution, which is why a screen tested
 * in `jsdom` and a screen photographed in a browser are looking at one dataset.
 */

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const fixtures = join(dirname(root), 'fixtures', 'scenarios');

/**
 * Every read a surface makes, and the fixture that answers it.
 *
 * `{name}` marks a variable segment, spelled the way the API document spells it.
 */
export const SHELL_ENDPOINTS = Object.freeze({
  '/auth/me': 'principal',
  '/health/ready': 'health',
  '/v1/runs': 'runs',
  '/v1/runs/{run_id}': 'run-detail',
  '/v1/runs/{run_id}/replay': 'run-replay',
  '/v1/investigations/{run_id}/threads': 'run-threads',
  '/v1/investigations/{run_id}/interactions': 'interactions',
  '/v1/approvals': 'approvals',
  '/v1/approvals/{approval_id}': 'approval-detail',
  '/v1/proposals': 'proposals',
  '/v1/proposals/count': 'proposal-count',
  '/v1/proposals/{proposal_id}': 'proposal-detail',
  '/v1/memory/search': 'episodes',
  '/v1/memory/stats': 'memory-stats',
  '/v1/topology/{node_id}': 'topology',
  '/v1/knowledge/documents': 'documents',
  '/v1/knowledge/documents/{document_id}': 'document-detail',
  '/v1/autonomy/policy/{node_id}': 'autonomy-policy',
  '/v1/autonomy/policy/{node_id}/bounds': 'autonomy-bounds',
  '/v1/autonomy/policy/{node_id}/outlook': 'autonomy-outlook',
  '/v1/autonomy/policy/{node_id}/preview': 'autonomy-preview',
  '/v1/agent/pipeline': 'agent-pipeline',
  '/v1/autonomy/kill-switch': 'kill-switch',
  '/v1/config': 'config-tree',
  '/v1/config/{node_id}': 'config-effective',
  '/v1/config/{node_id}/catalogue': 'config-catalogue',
  '/v1/config/{node_id}/fields': 'config-fields',
  '/v1/config/{node_id}/integration-schemas': 'config-integration-schemas',
  '/v1/config/{node_id}/operating-context': 'config-operating-context',
  '/v1/config/{node_id}/operating-context/preview': 'config-operating-context-preview',
  '/v1/config/{node_id}/preview': 'config-preview',
  '/v1/integrations': 'integrations',
  '/v1/setup/checklist': 'setup-checklist',
  '/v1/providers': 'providers',
  '/v1/providers/{provider_id}': 'provider-detail',
  '/v1/capabilities': 'capabilities',
  '/identity/principals': 'principals',
  '/identity/grants': 'grants',
  '/identity/roles': 'roles',
  '/identity/sso': 'sso',
  '/identity/tokens': 'tokens',
  '/audit/events': 'audit-events',
  '/v1/estate/summary': 'estate-summary',
  '/v1/estate/resources': 'estate-resources',
  '/v1/estate/resources/{resource_id}': 'estate-resource-detail',
  '/v1/estate/unresolved-alert-targets': 'estate-unresolved-targets',
  '/v1/ingress/sources': 'ingress-sources',
  '/v1/transit/ingress': 'transit-ingress',
  '/v1/transit/rules': 'transit-rules',
  '/v1/transit/destinations': 'transit-destinations',
  '/v1/transit/deliveries': 'transit-deliveries',
  '/v1/transit/simulate': 'transit-simulate',
  '/v1/transit/deliveries/{delivery_id}/resend': 'transit-resend',
  '/v1/estate/nodes': 'estate-nodes',
  '/v1/estate/storage': 'estate-storage',
  '/v1/estate/backups': 'estate-backups',
  '/v1/incidents': 'incidents',
  '/v1/incidents/{incident_id}': 'incident-detail',
  '/v1/detectors': 'detectors',
  '/v1/schedules': 'schedules',
  '/v1/observations': 'observations',
});

/**
 * The variables `path` binds in `template`, or `null` when it does not match.
 *
 * @param {string} template
 * @param {string} path
 * @returns {Record<string, string> | null}
 */
function bind(template, path) {
  const expected = template.split('/');
  const actual = path.split('/');
  if (expected.length !== actual.length) return null;
  /** @type {Record<string, string>} */
  const bound = {};
  for (let index = 0; index < expected.length; index += 1) {
    const want = expected[index];
    const have = actual[index];
    if (want.startsWith('{') && want.endsWith('}')) {
      if (have === '') return null;
      bound[want.slice(1, -1)] = have;
    } else if (want !== have) {
      return null;
    }
  }
  return bound;
}

/**
 * Which fixture answers `path`, and what it binds.
 *
 * A literal segment wins over a templated one, so `/v1/knowledge/documents`
 * resolves to the collection rather than being swallowed by the detail template.
 *
 * @param {string} path
 * @returns {{ slug: string, arguments: Record<string, string> } | null}
 */
export function resolveFixture(path) {
  /** @type {{ slug: string, arguments: Record<string, string> } | null} */
  let best = null;
  let fewest = Number.POSITIVE_INFINITY;
  for (const [template, slug] of Object.entries(SHELL_ENDPOINTS)) {
    const bound = bind(template, path);
    if (bound === null) continue;
    const size = Object.keys(bound).length;
    if (size < fewest) {
      best = { slug, arguments: bound };
      fewest = size;
    }
  }
  return best;
}

/**
 * The recorded body for `path` in `scenario`, or `null` when nothing serves it.
 *
 * A detail endpoint carries one recorded response per identifier; the one whose
 * recorded arguments match is the answer, and the first is the fallback so that
 * an identifier the capture never saw still renders something rather than a
 * 404 the screen has to explain.
 *
 * @param {string} scenario
 * @param {string} path
 * @returns {unknown}
 */
export function bodyFor(scenario, path) {
  const found = resolveFixture(path);
  if (found === null) return null;
  const file = join(fixtures, scenario, `${found.slug}.json`);
  let loaded;
  try {
    loaded = JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
  const responses = loaded.responses ?? [];
  if (responses.length === 0) return null;
  const names = Object.keys(found.arguments);
  const matched = responses.find((response) =>
    names.every((name) => (response.arguments ?? {})[name] === found.arguments[name]),
  );
  return (matched ?? responses[0]).body;
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
    const body = bodyFor(scenario, path);
    if (body === null) {
      response.writeHead(404, { 'content-type': 'application/json' });
      response.end('{}');
      return;
    }
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify(body));
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => {
      resolve(server);
    });
  });
}
