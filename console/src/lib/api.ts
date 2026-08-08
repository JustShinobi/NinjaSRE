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

/**
 * `GET` `path` and return its body, typed from the generated schema.
 *
 * Throws `ApiError` on anything but a 2xx. A failed read is a thing a screen
 * decides how to show; swallowing it here would leave every screen rendering an
 * empty state that means "no data" and "the gateway is down" at once.
 */
export async function read<P extends ReadablePath>(
  path: P,
  init?: RequestInit,
): Promise<Ok200<paths[P]>> {
  // Built rather than spread: `HeadersInit` is also an array of pairs and a
  // `Headers`, and spreading either of those into an object produces indices.
  const headers = new Headers(init?.headers);
  if (!headers.has('accept')) {
    headers.set('accept', 'application/json');
  }
  const response = await fetch(`${apiOrigin()}${path}`, { ...init, headers });
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
