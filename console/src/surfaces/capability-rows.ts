import { field, flag, list, text } from './read';

/**
 * What this deployment can do, joined with whether it can do it *here*.
 *
 * Named `capability-rows` rather than `capabilities` because the boundary check
 * that keeps this console from reaching into the Python tree matches a relative
 * path's first segment against the Python package names, and a sibling import
 * of a module called `capabilities` is one of them. A file name is cheaper to
 * change than a guard is to weaken.
 *
 * Two reads meet in this file: `/v1/capabilities`, which is what the build
 * declares, and `/v1/config/{node_id}/catalogue`, which is what that node
 * resolves — available or not, and the integration blocking anything that is
 * not. Two screens need the join and neither may compute its own: the catalogue
 * lists it as a table and the agent screen groups it by risk, and the day the
 * two disagreed one of them would be telling somebody a tool was available that
 * the other said was blocked.
 *
 * Nothing here decides anything the deployment has not already decided. The
 * availability, the reason and the side-effect level all arrive from the API;
 * what this adds is one shape, one order, and the read/write question — which is
 * a reading of the level rather than a second opinion about it.
 */

/**
 * The side-effect levels that only read.
 *
 * Everything else writes, including a level this console has never heard of:
 * "unknown means write" is the same default the platform takes for a capability
 * whose author declared nothing, and it is the only safe direction to be wrong
 * in. `tests/contract/console/test_console_surfaces.py` holds this list against
 * the platform's own scale, so a level added in Python fails in Python.
 */
export const READ_ONLY_LEVELS: readonly string[] = ['read', 'read_sensitive'];

/** The tag every capability bridged from an outside server carries. */
export const BRIDGED_TAG = 'bridged';

/** The separator between a bridged server and the tool it offers. */
const QUALIFIED_SEPARATOR = '.';

/** One capability, as both screens read it. */
export interface CapabilityRow {
  readonly name: string;
  /** `tool` or `skill`, as the deployment names it. */
  readonly kind: string;
  readonly summary: string;
  /** Where the tool reaches, as the build declares it. Empty for a skill. */
  readonly domain: string;
  readonly sideEffect: string;
  /** Whether this capability changes something. Unknown levels count as writes. */
  readonly writes: boolean;
  /** Whether this node may run it. Meaningless unless `known`. */
  readonly available: boolean;
  /** Whether the node's catalogue had an opinion at all. */
  readonly known: boolean;
  /** What is blocking it, in the deployment's own words. Empty when nothing is. */
  readonly reason: string;
  readonly requiredIntegrations: readonly string[];
  /** The bridged server this came from, empty for a capability of this build. */
  readonly origin: string;
  readonly tags: readonly string[];
}

/** Whether `level` only reads. */
export function readsOnly(level: string): boolean {
  return READ_ONLY_LEVELS.includes(level);
}

/**
 * The server a bridged capability came from, or empty for one of this build's own.
 *
 * Read from the tag rather than from the name's shape: every first-party
 * capability is also named `domain.tool`, so splitting on the dot alone would
 * report `estate` as an outside server for half the catalogue.
 */
export function originOf(entry: unknown): string {
  const tags = list(entry, 'tags').map(String);
  if (!tags.includes(BRIDGED_TAG)) return '';
  const name = text(entry, 'name');
  const cut = name.indexOf(QUALIFIED_SEPARATOR);
  return cut === -1 ? name : name.slice(0, cut);
}

/**
 * Every capability this deployment declares, joined with what this node says.
 *
 * `catalogue` is `/v1/capabilities` and `entries` is the node's catalogue read.
 * A node that resolved to nothing — a deployment with no organisation tree yet —
 * passes an empty `entries` and every row comes back `known: false`, which the
 * screens render as "we do not know" rather than as "nothing is blocking it".
 */
export function capabilityRows(
  catalogue: unknown,
  entries: unknown,
): readonly CapabilityRow[] {
  const resolved = new Map(
    list(entries, 'entries').map((entry) => [text(entry, 'name'), entry] as const),
  );

  const rows: CapabilityRow[] = [];
  for (const tool of list(catalogue, 'tools')) {
    const name = text(tool, 'name');
    rows.push(
      rowFor({
        name,
        kind: 'tool',
        summary: text(tool, 'description'),
        domain: text(tool, 'domain'),
        declared: text(tool, 'side_effect_level'),
        entry: resolved.get(name),
      }),
    );
  }
  for (const skill of list(catalogue, 'skills')) {
    const name = text(skill, 'name');
    rows.push(
      rowFor({
        name,
        kind: 'skill',
        summary: text(skill, 'description'),
        domain: '',
        declared: '',
        entry: resolved.get(name),
      }),
    );
  }

  // Anything the node resolved that the build's own listing did not name. In a
  // deployment the two walk the same discovery and agree; where they do not,
  // the node's answer is the one that decides what a run may call, and dropping
  // its extra entries would hide exactly the rows that say why something is
  // blocked.
  const listed = new Set(rows.map((row) => row.name));
  for (const [name, entry] of resolved) {
    if (listed.has(name)) continue;
    rows.push(
      rowFor({
        name,
        kind: text(entry, 'kind') || 'tool',
        summary: text(entry, 'summary'),
        domain: '',
        declared: '',
        entry,
      }),
    );
  }
  return rows;
}

function rowFor(source: {
  readonly name: string;
  readonly kind: string;
  readonly summary: string;
  readonly domain: string;
  readonly declared: string;
  readonly entry: unknown;
}): CapabilityRow {
  const { name, kind, summary, domain, declared, entry } = source;
  const missing = entry === undefined;
  // The node's catalogue is resolved *at the node*, so its answer leads. The
  // build's own declaration stands in where the node said nothing — which is
  // every row on a deployment that has no organisation tree yet.
  const level = (missing ? '' : text(entry, 'side_effect_level')) || declared;
  return {
    name,
    kind,
    summary: missing ? summary : text(entry, 'summary') || summary,
    domain,
    sideEffect: level,
    writes: level !== '' && !readsOnly(level),
    available: !missing && flag(entry, 'available'),
    known: !missing,
    reason: missing ? '' : text(entry, 'reason'),
    requiredIntegrations: missing
      ? []
      : list(entry, 'required_integrations').map(String),
    origin: missing ? '' : originOf(entry),
    tags: missing ? [] : list(entry, 'tags').map(String),
  };
}

/** One bridged server a team registered, as the tools tab shows it. */
export interface BridgedServer {
  readonly name: string;
  readonly protocol: string;
  readonly transport: string;
  readonly address: string;
  readonly enabled: boolean;
}

/**
 * The outside servers this node's configuration registers.
 *
 * Read from the configuration rather than from a catalogue, because that is
 * where the answer is: a server is registered by an operator and its tools are
 * enumerated by reaching it. A server that is registered and unreachable is
 * therefore still on this list, which is the case worth showing — an
 * investigation that quietly had fewer tools than the operator believes it has.
 */
export function bridgedServers(values: unknown): readonly BridgedServer[] {
  const capabilities = field(values, 'capabilities');
  return list(capabilities, 'protocol_servers').map((server) => ({
    name: text(server, 'name'),
    protocol: text(server, 'protocol'),
    transport: text(server, 'transport'),
    address: text(server, 'url') || list(server, 'command').map(String).join(' '),
    enabled: flag(server, 'enabled'),
  }));
}
