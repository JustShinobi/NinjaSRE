import { ApiError, ask, read, readProjected, type ProjectedPath } from '@/lib/api';
import type { PanelState } from './panel';

/**
 * How a surface reads, and why a failed read is a state rather than an
 * exception.
 *
 * Every panel makes its own read and catches its own failure. That is the
 * mechanism behind "panels fail alone": a page that awaited six reads together
 * would have one failure mode, and the failure mode would be a blank page. Here
 * a rejected read becomes `{ status: 'error' }` for one region, the other five
 * are unaffected, and the region says which dependency let it down.
 *
 * Nothing here interprets a payload. The accessors below pick fields out of an
 * `unknown` and are deliberately dull: a console that parsed a response into a
 * model of its own would be holding a second opinion about the API, and the
 * generated client exists so that it cannot.
 */

/** Present the credential this request carried, and nothing else. */
export function authorised(credential: string): RequestInit {
  return {
    headers: { authorization: `Bearer ${credential}` },
    // A surface is per-viewer and per-instant. A cached copy of one is somebody
    // else's permissions rendered for this person.
    cache: 'no-store',
  };
}

/** What one panel's read produced: the data, or the name of what failed. */
export type PanelData<T> =
  | { readonly status: 'ready'; readonly data: T }
  | { readonly status: 'error'; readonly dependency: string };

/**
 * `work`, contained.
 *
 * `ApiError` and `TypeError` are the two a read produces — a refusal from the
 * gateway and a connection that was never made. Anything else is a defect in
 * this console and is left to reach the route's own boundary, because swallowing
 * it here would turn a bug into a panel that says the gateway is down.
 */
export async function panelRead<T>(
  dependency: string,
  work: () => Promise<T>,
): Promise<PanelData<T>> {
  try {
    return { status: 'ready', data: await work() };
  } catch (error) {
    if (error instanceof ApiError || error instanceof TypeError) {
      return { status: 'error', dependency };
    }
    throw error;
  }
}

/**
 * A projected endpoint, read for one panel.
 *
 * The estate and the observation endpoints are not in the API document yet, so
 * an unpopulated deployment answers a 404 — which is a deployment that has not
 * been connected to anything rather than a failure. That distinction is the
 * whole reason this is a separate function: a 404 here becomes *empty*, and
 * every other refusal stays an error.
 */
export async function readProjectedPanel(
  path: ProjectedPath,
  credential: string,
  options: {
    readonly params?: Readonly<Record<string, string>>;
    readonly query?: string;
  } = {},
): Promise<PanelData<unknown>> {
  const dependency = path;
  try {
    return {
      status: 'ready',
      data: await readProjected(path, { ...authorised(credential), ...options }),
    };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return { status: 'ready', data: {} };
    }
    if (error instanceof ApiError || error instanceof TypeError) {
      return { status: 'error', dependency };
    }
    throw error;
  }
}

/**
 * A declared endpoint whose 404 means *nothing is set here yet*.
 *
 * Distinct from `readProjectedPanel`, which is about endpoints the document
 * does not declare. These are declared, served, and answer 404 for a node that
 * carries no configuration of its own — which is the ordinary state of a
 * deployment on its first day rather than a failure, and the state the guided
 * setup exists to move out of. Every other refusal stays an error.
 */
export async function optionalRead<T>(
  dependency: string,
  work: () => Promise<T>,
): Promise<PanelData<T | Record<string, never>>> {
  try {
    return { status: 'ready', data: await work() };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return { status: 'ready', data: {} };
    }
    if (error instanceof ApiError || error instanceof TypeError) {
      return { status: 'error', dependency };
    }
    throw error;
  }
}

/** The panel state `data` and its emptiness imply. */
export function stateOf(data: PanelData<unknown>, empty: boolean): PanelState {
  if (data.status === 'error') return 'error';
  return empty ? 'empty' : 'ready';
}

/** What failed, or nothing when nothing did. */
export function dependencyOf(data: PanelData<unknown>): string {
  return data.status === 'error' ? data.dependency : '';
}

/** The data, or `undefined` when the read failed. */
export function dataOf<T>(data: PanelData<T>): T | undefined {
  return data.status === 'ready' ? data.data : undefined;
}

/**
 * Whether a fact a read carries exists, distinguishing "it does not" from
 * "the read that would say so failed" — the third answer `stateOf` and
 * `dependencyOf` give for the panel around it, given here for the fact
 * inside it.
 *
 * A chip, a badge, or any short label that would otherwise say "No X" from
 * a read that never answered derives from this instead: `unknown` names the
 * dependency that failed, and only a `status: 'ready'` read is ever allowed
 * to say `present` or `absent`. A screen deriving its own boolean from
 * `dataOf(...) !== undefined` cannot tell "confirmed absent" from "never
 * asked" apart — this function exists so nothing has to.
 */
export type Existence =
  | { readonly kind: 'unknown'; readonly dependency: string }
  | { readonly kind: 'absent' }
  | { readonly kind: 'present' };

/**
 * The existence `data` implies for one fact inside it, given whether the
 * caller found it once the read succeeded.
 *
 * `present`, mirroring `stateOf`'s own second parameter: the caller has
 * already looked at the body and knows whether the fact is there, because
 * only the caller knows which field of which shape it is looking for.
 */
export function existenceOf(data: PanelData<unknown>, present: boolean): Existence {
  if (data.status === 'error') return { kind: 'unknown', dependency: data.dependency };
  return present ? { kind: 'present' } : { kind: 'absent' };
}

// --- Picking fields out of a payload ---------------------------------------------

/** One field of `record`, whatever it turns out to be. */
export function field(record: unknown, name: string): unknown {
  return Reflect.get(Object(record), name);
}

/** `record.name` when it is a string, and the empty string when it is not. */
export function text(record: unknown, name: string): string {
  const found = field(record, name);
  return typeof found === 'string' ? found : '';
}

/** `record.name` when it is a finite number, and nought when it is not. */
export function number(record: unknown, name: string): number {
  const found = field(record, name);
  return typeof found === 'number' && Number.isFinite(found) ? found : 0;
}

/** Whether `record.name` is exactly `true`. Never truthiness. */
export function flag(record: unknown, name: string): boolean {
  return field(record, name) === true;
}

/** `record.name` when it is a list, and an empty one when it is not. */
export function list(record: unknown, name: string): readonly unknown[] {
  const found = field(record, name);
  return Array.isArray(found) ? found : [];
}

/**
 * `record.name` read as a counted breakdown: name to how many, sorted by name.
 *
 * The estate's `by_kind` and `by_health` are objects rather than lists, because
 * an integration registers its own resource kinds and the keys are therefore
 * open. Sorting here rather than at each call site keeps two panels showing the
 * same breakdown in the same order.
 */
export function counts(
  record: unknown,
  name: string,
): readonly (readonly [string, number])[] {
  const found: unknown = field(record, name);
  if (typeof found !== 'object' || found === null || Array.isArray(found)) return [];
  return Object.entries(found)
    .filter((entry): entry is [string, number] => typeof entry[1] === 'number')
    .sort((left, right) => left[0].localeCompare(right[0]));
}

/** One count out of a breakdown, and nought when it holds none. */
export function countOf(record: unknown, name: string, key: string): number {
  return counts(record, name).find((entry) => entry[0] === key)?.[1] ?? 0;
}

/** Every name and value of `record.name`, as strings, in the order it carries them. */
export function pairs(
  record: unknown,
  name: string,
): readonly (readonly [string, string])[] {
  const found = field(record, name);
  if (typeof found !== 'object' || found === null || Array.isArray(found)) return [];
  return Object.entries(found).map(([key, value]): readonly [string, string] => [
    key,
    typeof value === 'string' ? value : JSON.stringify(value),
  ]);
}

/**
 * What the sign-in and first-run screens need before anybody is signed in:
 * whether this deployment has an owner yet, and — only when it does not —
 * the command that gives it one.
 *
 * Read with no credential at all: the route is public by declaration, and
 * this is the one read in the whole console that is ever made without one.
 * A failed read returns `command: ''`, the same shape as an administered
 * deployment — this is the one fact where "could not tell" and "nothing to
 * show" have to render identically, because a wrong guess in the other
 * direction would print a stale invitation on a deployment that already has
 * an owner.
 */
export async function localAdministratorAvailability(): Promise<{ readonly command: string }> {
  try {
    const body = await read('/v1/setup/local-administrator', { cache: 'no-store' });
    return { command: text(body, 'command') };
  } catch (error) {
    if (error instanceof ApiError || error instanceof TypeError) {
      return { command: '' };
    }
    throw error;
  }
}

/** The gateway read every surface makes, so the credential is applied in one place. */
export { ask, read };
