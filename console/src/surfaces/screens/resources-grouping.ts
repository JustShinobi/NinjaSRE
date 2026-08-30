import { field, text } from '../read';

/**
 * The three shapes `/resources` folds its listing into: a health bar's
 * segments, the sections by hosting node, and the batch synthesis of
 * unhealthy resources that share a cause.
 *
 * All three read the response as it already arrives — `node`/`unhealthy_since`
 * on each resource, per this feature's own contract fix — and derive nothing
 * the deployment has not already reported.
 */

/** Most useful order to read a health breakdown in: good news, unknowns,
 * then worse news, absence last because it is not "watched" at all. */
const HEALTH_ORDER = [
  'healthy',
  'unknown',
  'unhealthy',
  'degraded',
  'stale',
  'maintenance',
  'absent',
];

export interface HealthSegment {
  readonly health: string;
  readonly count: number;
}

/** `byHealth`, ordered and with every zero-count state dropped. */
export function healthSegments(
  byHealth: Readonly<Record<string, number>>,
): readonly HealthSegment[] {
  const known = HEALTH_ORDER.filter((health) => (byHealth[health] ?? 0) > 0).map(
    (health) => ({ health, count: byHealth[health] ?? 0 }),
  );
  const rest = Object.entries(byHealth)
    .filter(([health, count]) => count > 0 && !HEALTH_ORDER.includes(health))
    .map(([health, count]) => ({ health, count }));
  return [...known, ...rest];
}

const PROBLEM_HEALTH = new Set(['degraded', 'unhealthy']);

function isUnhealthy(resource: unknown): boolean {
  return PROBLEM_HEALTH.has(text(resource, 'health'));
}

/** Where nothing placed a resource — grouped on its own, sorted alphabetically last. */
export const NO_NODE = '';

export interface NodeGroup {
  readonly nodeId: string;
  readonly nodeName: string;
  readonly hasUnhealthy: boolean;
  readonly resources: readonly unknown[];
}

/** `resources`, sectioned by hosting node — unhealthy sections first. */
export function groupByNode(resources: readonly unknown[]): readonly NodeGroup[] {
  const byNode = new Map<string, unknown[]>();
  const names = new Map<string, string>();
  for (const resource of resources) {
    const nodeId = text(resource, 'parent_id') || NO_NODE;
    const found = byNode.get(nodeId);
    if (found === undefined) byNode.set(nodeId, [resource]);
    else found.push(resource);
    if (!names.has(nodeId)) names.set(nodeId, text(resource, 'parent_name'));
  }

  const groups: NodeGroup[] = [];
  for (const [nodeId, members] of byNode) {
    const sorted = [...members].sort((left, right) => {
      const byHealth = Number(isUnhealthy(right)) - Number(isUnhealthy(left));
      if (byHealth !== 0) return byHealth;
      return text(left, 'display_name').localeCompare(text(right, 'display_name'));
    });
    groups.push({
      nodeId,
      nodeName: names.get(nodeId) ?? '',
      hasUnhealthy: sorted.some(isUnhealthy),
      resources: sorted,
    });
  }

  return groups.sort((left, right) => {
    if (left.hasUnhealthy !== right.hasUnhealthy) return left.hasUnhealthy ? -1 : 1;
    if (left.nodeId === NO_NODE) return 1;
    if (right.nodeId === NO_NODE) return -1;
    return left.nodeName.localeCompare(right.nodeName);
  });
}

/** How close two instants have to be to count as "the same window". */
const SYNTHESIS_WINDOW_MINUTES = 30;

/** The minimum a batch needs before it earns its own synthesis line. */
const SYNTHESIS_MINIMUM = 3;

export interface UnhealthySynthesis {
  readonly nodeId: string;
  readonly nodeName: string;
  readonly kind: string;
  readonly count: number;
  /** The oldest `unhealthy_since` in the batch — how long the whole group has been out. */
  readonly since: string;
}

/**
 * Unhealthy resources folded into batches sharing a node, a kind, and a
 * 30-minute start window — the same fact drawn three or more times is a
 * single event, not three.
 */
export function unhealthySynthesis(
  resources: readonly unknown[],
): readonly UnhealthySynthesis[] {
  const candidates = resources.filter(
    (resource) => text(resource, 'health') === 'unhealthy' && field(resource, 'unhealthy_since') !== null,
  );

  const byGroup = new Map<string, unknown[]>();
  for (const resource of candidates) {
    const key = `${text(resource, 'parent_id')}::${text(resource, 'kind')}`;
    const found = byGroup.get(key);
    if (found === undefined) byGroup.set(key, [resource]);
    else found.push(resource);
  }

  const result: UnhealthySynthesis[] = [];
  for (const members of byGroup.values()) {
    const sorted = [...members].sort(
      (left, right) =>
        Date.parse(text(left, 'unhealthy_since')) - Date.parse(text(right, 'unhealthy_since')),
    );
    // A window anchored on the oldest member: everyone within
    // SYNTHESIS_WINDOW_MINUTES of when the first of the batch went
    // unhealthy is the same event; anything later is its own story.
    const anchor = Date.parse(text(sorted[0], 'unhealthy_since'));
    const inWindow = sorted.filter(
      (resource) =>
        Date.parse(text(resource, 'unhealthy_since')) - anchor <=
        SYNTHESIS_WINDOW_MINUTES * 60 * 1000,
    );
    if (inWindow.length < SYNTHESIS_MINIMUM) continue;
    result.push({
      nodeId: text(sorted[0], 'parent_id'),
      nodeName: text(sorted[0], 'parent_name'),
      kind: text(sorted[0], 'kind'),
      count: inWindow.length,
      since: text(sorted[0], 'unhealthy_since'),
    });
  }

  return result;
}
