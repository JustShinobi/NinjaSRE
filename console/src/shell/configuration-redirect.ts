import { CONFIG_FIELD_OWNERS, CONFIG_FIELDS_NO_CONTROL } from './config-ownership';
import { AREAS, SETTINGS_PAGES } from './routes';

/**
 * Where a visitor with nothing more specific to say ends up.
 *
 * The Settings hub rather than the dashboard: everything the retired editor
 * used to reach is a configuration concern, and the hub is where every one of
 * its successors lives.
 */
export const CONFIGURATION_REDIRECT_HOME = '/settings';

/**
 * The dotted path of the mapping `path` sits in.
 *
 * The same rule `platform/config_service/fields.py`'s `_walk` assigns a leaf
 * when it appends it: everything but the field's own last segment. A field
 * declared at the schema's root, if one ever were, has no section at all —
 * but nothing in either list below is, so the empty string never has to be
 * resolved by this module.
 */
function sectionOf(path: string): string {
  const at = path.lastIndexOf('.');
  return at === -1 ? '' : path.slice(0, at);
}

/**
 * The anchor id the retired editor's table of contents wrote for `section`.
 *
 * Restated from `console/src/surfaces/preview.tsx`'s own `sectionId`, which is
 * private to the component it scopes. The two have to keep agreeing in one
 * direction only: this reads a fragment a browser already carries, produced
 * long ago by that function, and never writes one itself.
 */
function sectionAnchor(section: string): string {
  return `config-section-${section.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`;
}

/** `page`, resolved to the address a browser can open — an area or a Settings page alike. */
function pathForPage(page: string): string | undefined {
  return (
    AREAS.find((area) => area.id === page)?.path ??
    SETTINGS_PAGES.find((settingsPage) => settingsPage.id === page)?.path
  );
}

/**
 * Every section anchor the retired editor could link to, and the address
 * that now owns it.
 *
 * Derived from the parity map rather than written a second time: a field's
 * `page` is its section's owner, because the map's own invariant — held by
 * `tests/contract/console/test_console_config_ownership.py` — is that every
 * field a schema section holds is assigned to exactly one page. Fields with
 * no working control yet are read too: each still names the page responsible
 * for it, so a fragment naming a section that is only a stub today still
 * lands somewhere real rather than at the bare hub. Fields the console writes
 * about itself are not: nothing links to a section that offers no form for
 * anybody, old editor included.
 */
function sectionDestinations(): ReadonlyMap<string, string> {
  const table = new Map<string, string>();
  for (const { path, page } of [...CONFIG_FIELD_OWNERS, ...CONFIG_FIELDS_NO_CONTROL]) {
    const anchor = sectionAnchor(sectionOf(path));
    if (table.has(anchor)) continue;
    const destination = pathForPage(page);
    if (destination !== undefined) {
      table.set(anchor, destination);
    }
  }
  return table;
}

/** Built once: the map does not change within a running process. */
const SECTION_DESTINATIONS = sectionDestinations();

/**
 * Where a request for the retired editor's address now belongs.
 *
 * `hash` is the browser's own fragment, exactly as `window.location.hash`
 * reports it — empty, or starting with `#`. A server can never be handed this:
 * a fragment is not sent in an HTTP request, which is why this is a plain
 * function a client component calls after it has mounted, rather than
 * something the route's own `page.tsx` could read.
 *
 * A node the old address carried (`?node=<id>`) plays no part here — it named
 * *which* node's configuration to show, never *which group of fields*, and
 * none of the pages this table resolves to accept an arbitrary node the way
 * the retired editor did.
 *
 * A recognised section keeps its fragment on the way out, so the page that
 * now owns it opens at the very control the old table of contents pointed
 * to: the shared `ConfigEditor` this migration scoped to every owning page
 * draws the identical anchor id wherever it is mounted, so the id a bookmark
 * carries still resolves once it arrives.
 */
export function configurationRedirectTarget(hash: string): string {
  const id = hash.startsWith('#') ? hash.slice(1) : hash;
  if (id === '') return CONFIGURATION_REDIRECT_HOME;
  const destination = SECTION_DESTINATIONS.get(id);
  return destination === undefined
    ? CONFIGURATION_REDIRECT_HOME
    : `${destination}#${id}`;
}
