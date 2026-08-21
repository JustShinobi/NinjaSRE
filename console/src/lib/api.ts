/**
 * The only way out of the console.
 *
 * Every request goes through here, at an origin the deployment configures, and
 * every response shape comes from `src/api/schema.ts` — which is generated from
 * the gateway's own OpenAPI document and compared against a fresh generation by
 * the gate. The console therefore cannot hold a second opinion about what the
 * API returns: a route that changed shape fails type checking rather than
 * failing in a browser.
 */
import type { paths } from '@/api/schema';
import { reportUnauthorized } from '@/session/controller';

/**
 * Where the gateway is, as the running console sees it.
 *
 * Read at request time rather than inlined at build time, so one built image
 * serves every deployment. A build that baked the address in would make the
 * artefact CI produced un-runnable anywhere but the machine that built it.
 */
export function apiOrigin(): string {
  return process.env.NINJASRE_CONSOLE_API_URL ?? '';
}

/** The one status that is a statement about the session rather than the request. */
const UNAUTHORIZED = 401;

/** A request the gateway refused, carrying the status so a caller can act on it. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

type Ok200<P> = P extends {
  get: { responses: { 200: { content: { 'application/json': infer B } } } };
}
  ? B
  : never;

/** A path the gateway answers with a JSON body on `GET`. */
export type ReadablePath = {
  [P in keyof paths]: Ok200<paths[P]> extends never ? never : P;
}[keyof paths];

/** What a read may carry beyond a plain request: the path's variables and a query. */
export interface ReadOptions extends RequestInit {
  /** One value per `{name}` in the path. A missing one is an error, never a literal. */
  readonly params?: Readonly<Record<string, string>>;
  /** Appended after the path, already encoded, including its leading `?`. */
  readonly query?: string;
}

/**
 * `path` with each `{name}` replaced by `params[name]`.
 *
 * Throws when one is missing rather than sending the brace to the gateway. A
 * request to `/v1/runs/%7Brun_id%7D` comes back 404, which reads on a screen as
 * "there is no such run" — the one message that would send somebody looking in
 * exactly the wrong place.
 */
function bind(path: string, params: Readonly<Record<string, string>>): string {
  return path
    .split('/')
    .map((segment) => {
      if (!segment.startsWith('{') || !segment.endsWith('}')) return segment;
      const name = segment.slice(1, -1);
      const value = params[name];
      if (value === undefined || value === '') {
        throw new Error(`${path} needs a value for {${name}}`);
      }
      return encodeURIComponent(value);
    })
    .join('/');
}

/**
 * `GET` `path` and return its body, typed from the generated schema.
 *
 * Throws `ApiError` on anything but a 2xx. A failed read is a thing a screen
 * decides how to show; swallowing it here would leave every screen rendering an
 * empty state that means "no data" and "the gateway is down" at once.
 */
export async function read<P extends ReadablePath>(
  path: P,
  init?: ReadOptions,
): Promise<Ok200<paths[P]>> {
  // Built rather than spread: `HeadersInit` is also an array of pairs and a
  // `Headers`, and spreading either of those into an object produces indices.
  const headers = new Headers(init?.headers);
  if (!headers.has('accept')) {
    headers.set('accept', 'application/json');
  }
  const address = `${apiOrigin()}${bind(path, init?.params ?? {})}${init?.query ?? ''}`;
  const response = await fetch(address, { ...init, headers });
  if (response.status === UNAUTHORIZED) {
    // Published rather than handled. Every refusal reaches one controller, so
    // three concurrent 401s end the session once — because there is one place
    // that can end it, not because each of the three checked first.
    reportUnauthorized();
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      `GET ${path} returned ${String(response.status)}`,
    );
  }
  // The one assertion in the console, and it is the seam where an untyped
  // wire format becomes a typed one. What makes it safe is not this line but
  // the drift check: `schema.ts` is generated from the gateway's own document,
  // so the type on the left is the shape the gateway declares it sends.
  const body: unknown = await response.json();
  return body as Ok200<paths[P]>;
}

type Posted200<P> = P extends {
  post: { responses: { 200: { content: { 'application/json': infer B } } } };
}
  ? B
  : never;

/** A path the gateway answers with a JSON body on `POST`. */
export type AskablePath = {
  [P in keyof paths]: Posted200<paths[P]> extends never ? never : P;
}[keyof paths];

/**
 * `POST` a question and read the answer, for a route that computes and stores nothing.
 *
 * Separate from `read` because the type is different — the answer is declared
 * under `post` — and separate from the write proxies under `src/app/api/`
 * because those exist for one reason only: a *browser* cannot present a
 * credential that lives in an HTTP-only cookie. A server component already
 * holds it, so a courier here would be a hop that adds nothing.
 *
 * What keeps this from being a write path is the caller, not the verb. Every
 * use of it is a question — an explanation, a preview, a replay — and a route
 * that changes something is reached through the proxies, where the closed
 * operation table is.
 */
export async function ask<P extends AskablePath>(
  path: P,
  body: unknown,
  init?: ReadOptions,
): Promise<Posted200<paths[P]>> {
  const headers = new Headers(init?.headers);
  if (!headers.has('accept')) headers.set('accept', 'application/json');
  headers.set('content-type', 'application/json');
  const address = `${apiOrigin()}${bind(path, init?.params ?? {})}${init?.query ?? ''}`;
  const response = await fetch(address, {
    ...init,
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (response.status === UNAUTHORIZED) {
    reportUnauthorized();
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      `POST ${path} returned ${String(response.status)}`,
    );
  }
  const answered: unknown = await response.json();
  return answered as Posted200<paths[P]>;
}

/**
 * The endpoints a deployment will serve and the API document does not declare
 * yet.
 *
 * What is left is the Proxmox-shaped views: the cluster's nodes, its storage,
 * its backup jobs. Their shapes are already decided — the mock data plane
 * serves them, and its own catalogue is the authority — but nothing has
 * generated them into `schema.ts`, so `read` cannot name them and should not be
 * made to. The estate inventory and continuous observation used to be here and
 * have since landed, which is the list doing what it is supposed to do.
 *
 * This is therefore a *narrow, enumerated* seam rather than an escape hatch:
 * the list is closed, the body comes back untyped so every reader has to say
 * what it expects, and `tests/contract/console/test_console_surfaces.py` holds
 * this tuple against the mock plane's projected endpoints. **The list shrinks.**
 * When an endpoint lands in the document it moves to `read` and comes out of
 * here, and the contract test fails until it does.
 */
export const PROJECTED_PATHS = [
  '/v1/estate/nodes',
  '/v1/estate/storage',
  '/v1/estate/backups',
] as const;

export type ProjectedPath = (typeof PROJECTED_PATHS)[number];

/**
 * `GET` a projected endpoint.
 *
 * Untyped on purpose. A hand-written interface for a shape no document declares
 * would be exactly the second opinion about the API that the generated client
 * exists to prevent; a reader that has to pick fields out of `unknown` is a
 * reader that cannot silently disagree.
 */
export async function readProjected(
  path: ProjectedPath,
  init?: ReadOptions,
): Promise<unknown> {
  const headers = new Headers(init?.headers);
  if (!headers.has('accept')) {
    headers.set('accept', 'application/json');
  }
  const address = `${apiOrigin()}${bind(path, init?.params ?? {})}${init?.query ?? ''}`;
  const response = await fetch(address, { ...init, headers });
  if (response.status === UNAUTHORIZED) {
    reportUnauthorized();
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      `GET ${path} returned ${String(response.status)}`,
    );
  }
  return response.json();
}
