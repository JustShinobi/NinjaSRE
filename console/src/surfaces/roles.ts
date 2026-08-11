import catalogue from '../../../fixtures/contract/roles.json';

/**
 * The role names this deployment declares, least privileged first.
 *
 * Read from the platform's own generated catalogue — the same file
 * `fixtures/contract/roles.json` the role matrix walks in
 * `tests/unit/shell/support.tsx` — rather than written here as a list. A role
 * the platform adds shows up as one more option on the grant form the moment
 * the catalogue is regenerated, without this module changing at all.
 *
 * A plain `import` rather than a runtime read: the JSON is inlined into the
 * compiled bundle at build time, so the grant form never depends on
 * `fixtures/` being present on the machine actually serving the console.
 */
export const ROLE_NAMES: readonly string[] = catalogue.order;
