/**
 * The one place a dynamic route's own parameter is decoded.
 *
 * The router hands a page `params.<name>` still percent-encoded — Next does
 * not decode a dynamic segment on the way in — and `bind()`
 * (`src/lib/api.ts`) encodes exactly once on the way out to the gateway. A
 * page that used the raw parameter as-is and also let `bind()` encode it was
 * encoding whatever the router had already left encoded: double-encoded,
 * and a value the gateway had never stored under. This is the fix, applied
 * once at the edge every dynamic route parameter crosses, so the invariant
 * — decoded once here, encoded once in `bind()` — holds without each route
 * having to remember it.
 */

/**
 * Return `raw`, decoded exactly once.
 *
 * `raw` is expected to be whatever `params.<name>` carried: a router-owned
 * value, still percent-encoded. When decoding throws — `decodeURIComponent`
 * raises on a lone `%` that is not the start of a valid escape, which a
 * pasted or partially-typed address can easily contain — the original value
 * is returned rather than the render failing. A route whose parameter does
 * not resolve to anything real is a "not found", not a server error, and a
 * malformed escape must reach that same outcome rather than a crash.
 */
export function routeParam(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}
