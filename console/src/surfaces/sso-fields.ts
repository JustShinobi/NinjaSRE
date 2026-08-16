/**
 * The eight fields an identity provider is described by, told apart from any
 * component that renders them.
 *
 * Its own module, with no `'use client'`, for the reason `token-identity.ts`
 * and `stoppage.ts` exist: `settings/sso.tsx` is a server component building
 * the settings record this array indexes, and `sso-setup.tsx` is the client
 * form walking the same array to render one field each. A value exported from
 * a `'use client'` module does not survive a production build the way it
 * survives `vitest` — `tsc`, `eslint` and every unit test pass on it, and only
 * `next build`'s server bundle turns the import into something that is not an
 * array, `SSO_FIELDS.map is not a function`, at request time. Both sides
 * import the one declared here instead.
 */

export const SSO_FIELDS = [
  'provider',
  'issuer',
  'client_id',
  'authorisation_endpoint',
  'token_endpoint',
  'jwks_uri',
  'redirect_uri',
  'default_node_id',
] as const;

export type SsoField = (typeof SSO_FIELDS)[number];
