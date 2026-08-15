/**
 * Reading a nested effective-configuration document by a dotted path.
 *
 * A module with no client directive, deliberately: both a server screen (which
 * reads a role's current provider straight off `GET /v1/config/{node_id}`) and
 * the client editors in this group (which read the same shape out of a
 * preview's own answer) call this as a function, and `tests/unit/shell/
 * rsc-boundary.test.ts` refuses a server module that calls a function a
 * `'use client'` module exports — the same reasoning `stoppage.ts` and
 * `token-identity.ts` already follow.
 */

/** The value at a dotted `path` inside a nested document, or `undefined`. */
export function valueAt(values: unknown, path: string): unknown {
  let cursor: unknown = values;
  for (const segment of path.split('.')) {
    cursor =
      typeof cursor === 'object' && cursor !== null
        ? Reflect.get(cursor, segment)
        : undefined;
  }
  return cursor;
}
