import { field, text } from '../read';

/**
 * What the estate knows about a resource beyond what the hypervisor reports.
 *
 * Both facts arrive in `attributes`. The zone is derived from the address
 * against the declared networks; the criticality is declared outright in the
 * operator's own inventory. Until that inventory was read, neither existed on
 * any resource, and this screen could only offer kind and state — which is what
 * a hypervisor knows rather than what an operator cares about.
 *
 * **A resource with no zone is unplaced, not blank.** The estate does know: no
 * declared network covers its address. A blank cell reads as "nobody looked".
 *
 * **A resource with no criticality stays ungraded.** Defaulting to a middle
 * value would rank every resource the inventory does not describe against the
 * ones it does, on a value nobody wrote.
 */

/** What a resource no declared network covers is shown as. */
export const UNPLACED = 'unplaced';

/** The attribute the sweep annotates a resource's zone under. */
const ZONE_ATTRIBUTE = 'zone';

/** The attribute the declared inventory annotates importance under. */
const CRITICALITY_ATTRIBUTE = 'criticality';

/**
 * Most important first. The order is the triage order, not the alphabet.
 *
 * A word this console has not met sorts after all of these and keeps itself —
 * the vocabulary belongs to whoever wrote the inventory, and folding
 * "business-critical" into "high" would show them a word they did not choose.
 */
const CRITICALITY_ORDER = ['critical', 'high', 'medium', 'low'];

function attribute(record: unknown, name: string): string {
  return text(field(record, 'attributes'), name).trim();
}

/** Return the zone a resource sits in, or `UNPLACED` when nothing placed it. */
export function zoneOf(record: unknown): string {
  return attribute(record, ZONE_ATTRIBUTE) || UNPLACED;
}

/** Return the criticality the inventory declared, or empty when it declared none. */
export function criticalityOf(record: unknown): string {
  return attribute(record, CRITICALITY_ATTRIBUTE);
}

/**
 * Return where a resource sorts by declared importance.
 *
 * Ungraded sorts last rather than first: a resource nobody wrote down is not
 * thereby the most urgent thing on the screen.
 */
export function criticalityRank(record: unknown): number {
  const declared = criticalityOf(record);
  if (declared === '') return CRITICALITY_ORDER.length + 1;
  const found = CRITICALITY_ORDER.indexOf(declared);
  return found === -1 ? CRITICALITY_ORDER.length : found;
}

/**
 * Return the resources gathered by zone, in the order somebody reads them.
 *
 * Zones alphabetically, and the unplaced last whatever they would sort as:
 * alphabetically `unplaced` lands in the middle, and the rows nothing placed
 * are the least useful thing to open the screen with.
 */
export function byZone<T>(records: readonly T[]): [string, T[]][] {
  const grouped = new Map<string, T[]>();
  for (const record of records) {
    const zone = zoneOf(record);
    const found = grouped.get(zone);
    if (found === undefined) grouped.set(zone, [record]);
    else found.push(record);
  }

  return [...grouped.entries()].sort(([left], [right]) => {
    if (left === UNPLACED) return 1;
    if (right === UNPLACED) return -1;
    return left.localeCompare(right);
  });
}
