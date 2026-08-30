/**
 * The component filter of the Learned tab, grouped by type rather than
 * listed as one flat alphabet.
 *
 * `container:lxc/122` and `guest:lxc/122` are the same guest, seen through
 * two different observation paths — the staging audit that opened this
 * feature found both listed as separate options. Anything with a `type:id`
 * shape merges on `id` within its type; anything without one is classified
 * by shape, never invented.
 */

export type ComponentType = 'service' | 'node' | 'guest' | 'cluster';

const PREFIX_TYPE: Readonly<Record<string, ComponentType>> = {
  container: 'guest',
  guest: 'guest',
  node: 'node',
  cluster: 'cluster',
  service: 'service',
};

/** A bare node name this build already knows the shape of. */
const NODE_PATTERN = /^node\d+$/iu;

/** A bare guest identifier this build already knows the shape of. */
const GUEST_PATTERN = /^(ct|vm|lxc)[-/]?\d+$/iu;

export interface ComponentOption {
  /** What the query carries — the value a filter link is built from. */
  readonly canonical: string;
  /** What the person reads — never the raw prefixed form. */
  readonly display: string;
}

export interface ComponentGroup {
  readonly type: ComponentType;
  readonly options: readonly ComponentOption[];
}

/** `type:id`, split — or `null` when `component` carries no such prefix. */
function prefixed(component: string): { readonly type: ComponentType; readonly id: string } | null {
  const cut = component.indexOf(':');
  if (cut === -1) return null;
  const prefix = component.slice(0, cut).toLowerCase();
  const type = PREFIX_TYPE[prefix];
  if (type === undefined) return null;
  return { type, id: component.slice(cut + 1) };
}

/** `component`, classified by shape when it carries no `type:` prefix. */
function classified(component: string): { readonly type: ComponentType; readonly id: string } {
  if (component === 'cluster') return { type: 'cluster', id: component };
  if (NODE_PATTERN.test(component)) return { type: 'node', id: component };
  if (GUEST_PATTERN.test(component)) return { type: 'guest', id: component };
  return { type: 'service', id: component };
}

const TYPE_ORDER: readonly ComponentType[] = ['service', 'node', 'guest', 'cluster'];

/**
 * `components`, deduplicated by canonical identifier and grouped by type, in
 * a fixed, readable order.
 */
export function normaliseComponents(
  components: readonly string[],
): readonly ComponentGroup[] {
  const byType = new Map<ComponentType, Map<string, string>>();
  for (const component of components) {
    const resolved = prefixed(component) ?? classified(component);
    const canonical = `${resolved.type}:${resolved.id}`;
    const found = byType.get(resolved.type);
    const bucket = found ?? new Map<string, string>();
    if (found === undefined) byType.set(resolved.type, bucket);
    if (!bucket.has(canonical)) bucket.set(canonical, resolved.id);
  }

  return TYPE_ORDER.filter((type) => byType.has(type)).map((type) => {
    const bucket = byType.get(type);
    const options = [...(bucket ?? new Map<string, string>()).entries()]
      .sort(([, left], [, right]) => left.localeCompare(right))
      .map(([canonical, display]) => ({ canonical, display }));
    return { type, options };
  });
}
