import { areaByPath, settingsPageByPath } from '@/shell/routes';

/**
 * Where an empty state's, or a warning's, action goes — declared rather than
 * typed as a bare `href`.
 *
 * `EmptyState` already refuses to render with a blank verb; what it cannot
 * check is whether the destination is real, because a string is a string.
 * `route` is checked against `routes.ts` — the one list of what this console
 * serves — so a CTA aimed at a page that has been renamed or removed fails
 * where it is built rather than at the click three screens later. `anchor` or
 * `query` narrows the destination further, which is what turns "the
 * catalogue" into "the catalogue, filtered to chat integrations".
 */
export interface CtaTarget {
  readonly route: string;
  /** A field, a section, or a tab on that route. */
  readonly anchor?: string;
  /** A filter carried as a query string, for a destination narrowed by state. */
  readonly query?: Readonly<Record<string, string>>;
}

/** A CTA target, resolved: the address to link to, and the permission it needs. */
export interface ResolvedCta {
  readonly href: string;
  /** The permission `routes.ts` declares for this destination's area. */
  readonly permission: string;
}

/**
 * `target`, checked against the route manifest and turned into an address.
 *
 * Throws for a route this console does not serve — the same invariant
 * `IntegrationProfile` holds for a blank summary and `EmptyState` holds for a
 * blank action: the failure belongs at construction, not at the moment
 * somebody clicks a dead link three screens away.
 */
export function resolveCta(target: CtaTarget): ResolvedCta {
  // Both lists, because the hybrid navigation made "a route this console
  // serves" two lists rather than one: the areas in the sidebar, and the
  // settings pages behind Settings. A destination in the second is no less
  // real than one in the first — "the model each role uses" only exists
  // there — and refusing it would push screens back to the bare `href` this
  // function exists to replace.
  const area = areaByPath(target.route) ?? settingsPageByPath(target.route);
  if (area === undefined) {
    throw new Error(
      `"${target.route}" is not a route this console serves. An empty state's action has to ` +
        `land somewhere real — check routes.ts for the address this destination should carry.`,
    );
  }
  const search = new URLSearchParams(target.query ?? {}).toString();
  const anchor =
    target.anchor === undefined || target.anchor === '' ? '' : `#${target.anchor}`;
  return {
    href: `${area.path}${search === '' ? '' : `?${search}`}${anchor}`,
    permission: area.permission,
  };
}
