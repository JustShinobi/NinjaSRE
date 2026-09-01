/**
 * The component filter of the Learned tab, grouped by type rather than
 * listed as one flat alphabet.
 *
 * `container:lxc/122` and `guest:lxc/122` are the same guest, seen through
 * two different observation paths — the staging audit that opened this
 * feature found both listed as separate options. Anything with a `type:id`
 * shape merges on `id` within its type; anything without one is classified
 * by shape, never invented.
 *
 * **The canonical value is always one of the raw strings actually seen,
 * never synthesised.** The search endpoint filters by exact match
 * server-side (`by_component`, still called with a single raw component
 * string — this module changes what a person sees, never how the search is
 * made), so a value this module invented — `guest:<id>` when only
 * `container:<id>` was ever observed — would be a filter link that matches
 * nothing at the server. `raw` carries every spelling that resolved to one
 * option, so a caller whose corpus really does use both can query each of
 * them and merge, instead of trusting a fabricated string.
 */

export type ComponentType = 'service' | 'node' | 'guest' | 'cluster';

const PREFIX_TYPE: Readonly<Record<string, ComponentType>> = {
  container: 'guest',
  guest: 'guest',
  node: 'node',
  cluster: 'cluster',
  service: 'service',
};

/** Preferred first, when more than one raw spelling names the same id. */
const PREFIX_PRIORITY = ['guest', 'container'];

/** A bare node name this build already knows the shape of. */
const NODE_PATTERN = /^node\d+$/iu;

/** A bare guest identifier this build already knows the shape of. */
const GUEST_PATTERN = /^(ct|vm|lxc)[-/]?\d+$/iu;

export interface ComponentOption {
  /**
   * The value a filter link queries the server with — always one of `raw`,
   * chosen by `PREFIX_PRIORITY` when more than one spelling was observed.
   */
  readonly canonical: string;
  /** What the person reads — never the raw prefixed form. */
  readonly display: string;
  /** Every raw spelling this option folds — one entry, ordinarily. */
  readonly raw: readonly string[];
}

export interface ComponentGroup {
  readonly type: ComponentType;
  readonly options: readonly ComponentOption[];
}

interface Resolved {
  readonly type: ComponentType;
  readonly id: string;
  readonly prefix: string;
}

/** `type:id`, split — or `null` when `component` carries no such prefix. */
function prefixed(component: string): Resolved | null {
  const cut = component.indexOf(':');
  if (cut === -1) return null;
  const prefix = component.slice(0, cut).toLowerCase();
  const type = PREFIX_TYPE[prefix];
  if (type === undefined) return null;
  return { type, id: component.slice(cut + 1), prefix };
}

/** `component`, classified by shape when it carries no `type:` prefix. */
function classified(component: string): Resolved {
  if (component === 'cluster') return { type: 'cluster', id: component, prefix: '' };
  if (NODE_PATTERN.test(component)) return { type: 'node', id: component, prefix: '' };
  if (GUEST_PATTERN.test(component))
    return { type: 'guest', id: component, prefix: '' };
  return { type: 'service', id: component, prefix: '' };
}

/** The raw spelling to send the server, when a merged option carries more than one. */
function preferredRaw(entries: ReadonlyMap<string, string>): string {
  for (const prefix of PREFIX_PRIORITY) {
    const found = entries.get(prefix);
    if (found !== undefined) return found;
  }
  return [...entries.values()][0] ?? '';
}

const TYPE_ORDER: readonly ComponentType[] = ['service', 'node', 'guest', 'cluster'];

/**
 * `components`, deduplicated by canonical identifier and grouped by type, in
 * a fixed, readable order. Every option's `canonical` is a value this
 * function saw in `components`, never one it built.
 */
/**
 * `component`'s own short name — the id without its type prefix, which is
 * what a chip prints in place of the raw `service:runner-orchestrator`
 * spelling. The same resolution `normaliseComponents` uses per option.
 */
export function displayComponent(component: string): string {
  const resolved = prefixed(component) ?? classified(component);
  return resolved.id;
}

export function normaliseComponents(
  components: readonly string[],
): readonly ComponentGroup[] {
  // type -> id -> (prefix -> the raw string that carried it)
  const byType = new Map<ComponentType, Map<string, Map<string, string>>>();
  for (const component of components) {
    const resolved = prefixed(component) ?? classified(component);
    const byId = byType.get(resolved.type) ?? new Map<string, Map<string, string>>();
    if (!byType.has(resolved.type)) byType.set(resolved.type, byId);
    const byPrefix = byId.get(resolved.id) ?? new Map<string, string>();
    if (!byId.has(resolved.id)) byId.set(resolved.id, byPrefix);
    byPrefix.set(resolved.prefix, component);
  }

  return TYPE_ORDER.filter((type) => byType.has(type)).map((type) => {
    const byId = byType.get(type) ?? new Map<string, Map<string, string>>();
    const options = [...byId.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([id, byPrefix]) => ({
        canonical: preferredRaw(byPrefix),
        display: id,
        raw: [...new Set(byPrefix.values())],
      }));
    return { type, options };
  });
}
