import type { ReactNode } from 'react';

import { Skeleton } from '@/components/feedback';

/**
 * What fills the region while an area is being fetched.
 *
 * Every area here is a dynamic Server Component that reads live, authenticated
 * data on render, so a navigation genuinely waits on the gateway. Without this
 * file the router holds the *previous* page on screen for the whole of that
 * wait — so pressing Incidents while looking at the Overview showed the
 * Overview, unchanged, for as long as the read took, and the only way to tell
 * a slow navigation from a click that had missed was to press it again.
 *
 * One file, at the group root, rather than one per area. The shell around it —
 * the sidebar, the top bar, the search — is outside this boundary and is not
 * repainted, which is the property worth having: only the region below the
 * heading changes, and it changes into something the same shape as what is
 * coming rather than into nothing.
 *
 * The shape is deliberately generic: a heading, a band, a row of tiles, a
 * table. Every area in this console is some arrangement of those, so the
 * placeholder is close enough that the arriving content settles into it
 * instead of shoving it aside. A skeleton that matched one screen exactly
 * would be wrong on the other seventeen.
 */
export default function Loading(): ReactNode {
  return (
    <div role="status" aria-busy="true" data-testid="area-loading">
      <div className="flex flex-col gap-2 mb-5">
        <Skeleton width="row-title" ground="page" />
        <Skeleton width="row" ground="page" />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-5">
        {[0, 1, 2, 3].map((tile) => (
          <div
            key={tile}
            className="bg-raised edge border-border rounded-3 shadow-1 p-4 flex flex-col gap-2"
          >
            <Skeleton width="row" />
            <Skeleton width="figure" />
            <Skeleton width="row" />
          </div>
        ))}
      </div>

      <div className="bg-raised edge border-border rounded-3 shadow-1">
        <div className="px-4 py-3 edge border-border border-t-0 border-x-0">
          <Skeleton width="row-title" />
        </div>
        <div className="p-4 flex flex-col gap-3">
          {[0, 1, 2, 3, 4, 5].map((row) => (
            <Skeleton key={row} width="row" />
          ))}
        </div>
      </div>
    </div>
  );
}
