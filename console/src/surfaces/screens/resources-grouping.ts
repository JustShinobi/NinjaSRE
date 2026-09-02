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
/**
 * Worse before better — the whole scale, not the binary `isUnhealthy` split
 * the default order uses. What the "worst first" chip sorts by.
 */
const WORST_RANK: Readonly<Record<string, number>> = {
  unhealthy: 0,
  degraded: 1,
  stale: 2,
  unknown: 3,
  absent: 4,
  maintenance: 5,
  healthy: 6,
};

function worstRank(resource: unknown): number {
  return WORST_RANK[text(resource, 'health')] ?? 3;
}

export function groupByNode(
  resources: readonly unknown[],
  worstFirst = false,
): readonly NodeGroup[] {
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
      const byHealth = worstFirst
        ? worstRank(left) - worstRank(right)
        : Number(isUnhealthy(right)) - Number(isUnhealthy(left));
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

/**
 * How many cards a node section draws before the grid gives way to a link —
 * one row (the grid's own four columns) when nothing on the node is
 * unhealthy, two rows when something is. A section with nothing wrong has
 * nothing urgent to earn the second row; a section with a problem gets the
 * extra space to show it without immediately reaching for the link.
 */
const NODE_SECTION_ROW = 4;
const NODE_SECTION_ROWS_WITH_PROBLEM = 2;

export interface SectionCap {
  /** The cards the grid actually draws — every one of the section's own
   * resources when nothing was hidden. */
  readonly shown: readonly unknown[];
  /**
   * Present only when the grid stopped short of the section's own total.
   * `count` is the unhealthy total when unhealthy ones are still hidden
   * behind the cap (`onlyUnhealthy: true`) — never the node's whole count,
   * which would bury the more urgent number under a bigger one — and the
   * node's whole count otherwise, once every unhealthy resource already
   * fits in what is shown.
   */
  readonly more?: {
    readonly count: number;
    readonly onlyUnhealthy: boolean;
  };
}

/**
 * `section`'s cards, capped for a grid that has to end — the same fact as
 * the wave's own inherited debt: nothing fit in a capture window because the
 * grid never stopped. `section.resources` is read as `groupByNode` already
 * sorted it, unhealthy first, so the cards this keeps are always the most
 * pressing ones the section has.
 */
export function capNodeSection(section: NodeGroup): SectionCap {
  const unhealthyCount = section.resources.filter(isUnhealthy).length;
  const capacity =
    unhealthyCount > 0
      ? NODE_SECTION_ROW * NODE_SECTION_ROWS_WITH_PROBLEM
      : NODE_SECTION_ROW;

  if (section.resources.length <= capacity) {
    return { shown: section.resources };
  }

  const onlyUnhealthy = unhealthyCount > capacity;
  return {
    shown: section.resources.slice(0, capacity),
    more: {
      count: onlyUnhealthy ? unhealthyCount : section.resources.length,
      onlyUnhealthy,
    },
  };
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
    (resource) =>
      text(resource, 'health') === 'unhealthy' &&
      field(resource, 'unhealthy_since') !== null,
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
        Date.parse(text(left, 'unhealthy_since')) -
        Date.parse(text(right, 'unhealthy_since')),
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
