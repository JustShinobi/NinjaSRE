'use client';

import { useMemo, useState, type ReactNode } from 'react';
import NextLink from 'next/link';
import { useRouter } from 'next/navigation';

import { Input } from '@/components/form';
import { Pagination } from '@/components/navigation';
import { EmptyState } from '@/components/state';
import { message, type Locale } from '@/i18n/messages';
import { captureScrollPosition } from './scroll-memory';
import {
  hrefFor,
  withFilter,
  withPage,
  writeViewState,
  type FilterName,
  type ViewState,
} from './url-state';

/**
 * The catalogue grid: search and paging, entirely on the client.
 *
 * The eighty-plus not-yet-connected integrations are already on the page —
 * one read served the whole catalogue — so narrowing them as somebody types
 * is arithmetic over an array already in memory, never a second request. What
 * still reaches the address bar is the *result* of that arithmetic: every
 * keystroke updates the visible grid immediately and replaces the address
 * without a scroll jump, so a link somebody sends still opens filtered the
 * same way, and a reload resumes it.
 *
 * Paging is the same story. `next`/`previous` never asks the deployment for
 * another page; it re-slices what is already held and writes the new page
 * number to the address, because a long list here is arithmetic, not a
 * network trip.
 */

/**
 * How many catalogue cards one page shows.
 *
 * This is a display choice, not a limit the deployment enforces — nothing
 * here is ever sent to the gateway, so it is not read from a backend cap the
 * way a page size that becomes a query parameter would be. It mirrors
 * `INTEGRATIONS_CATALOGUE_PAGE_SIZE` in `config/constants/surfaces.py`, which
 * a contract test holds this literal against, so the two cannot drift apart
 * silently.
 */
export const INTEGRATIONS_CATALOGUE_PAGE_SIZE = 24;

export interface CatalogueGridItem {
  readonly name: string;
  readonly displayName: string;
  readonly category: string;
  readonly categoryLabel: string;
  readonly summary: string;
  readonly capabilities: readonly string[];
}

export interface CatalogueGridLabels {
  readonly search: string;
  readonly emptyHeading: string;
  readonly emptyBody: string;
  readonly emptyClear: string;
  /** The reference page's own link text, offered beside "clear the search". */
  readonly notCovered: string;
}

export interface IntegrationCatalogueGridProps {
  readonly locale: Locale;
  readonly path: string;
  readonly state: ViewState;
  readonly filters: readonly FilterName[];
  readonly items: readonly CatalogueGridItem[];
  readonly pageSize: number;
  readonly labels: CatalogueGridLabels;
  /** Where the "not covered" reference page is, resolved by the caller. */
  readonly notCoveredHref: string;
}

/** The compact grid: a search box, a bounded set of cards, and paging. */
export function IntegrationCatalogueGrid({
  locale,
  path,
  state,
  filters,
  items,
  pageSize,
  labels,
  notCoveredHref,
}: IntegrationCatalogueGridProps): ReactNode {
  const router = useRouter();
  const [query, setQuery] = useState(state.filters.q ?? '');
  const [page, setPage] = useState(state.page);

  const matching = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle === '') return items;
    return items.filter((item) =>
      `${item.displayName} ${item.category} ${item.summary} ${item.capabilities.join(' ')}`
        .toLowerCase()
        .includes(needle),
    );
  }, [items, query]);

  const pages = Math.max(1, Math.ceil(matching.length / pageSize));
  const boundedPage = Math.min(Math.max(page, 1), pages);
  const shown = matching.slice((boundedPage - 1) * pageSize, boundedPage * pageSize);

  // What the address actually carries right now — the live search and page,
  // composed with whatever else is already in `state` (`view`, `category`).
  // A card's own link is built from this, not from `state` alone, so opening
  // one while a search is still mid-keystroke still returns to it: closing
  // the panel reads the detail route's own address, and a card link with a
  // stale query would close back to a filter nobody is looking at any more.
  const liveState = withPage(withFilter(state, 'q', query), boundedPage);
  const liveQuery = writeViewState(liveState, filters);

  function sync(nextState: ViewState): void {
    router.replace(hrefFor(path, nextState, filters), { scroll: false });
  }

  return (
    <div className="flex flex-col gap-4">
      <div data-testid="catalogue-search">
        <Input
          label={labels.search}
          name="catalogue-search"
          type="search"
          value={query}
          onValueChange={(value) => {
            setQuery(value);
            setPage(1);
            sync(withPage(withFilter(state, 'q', value), 1));
          }}
        />
      </div>

      {shown.length === 0 ? (
        <div className="flex flex-col items-center gap-3">
          <EmptyState
            heading={labels.emptyHeading}
            body={labels.emptyBody}
            action={{
              label: labels.emptyClear,
              href: hrefFor(path, withPage(withFilter(state, 'q', ''), 1), filters),
            }}
          />
          <NextLink
            href={notCoveredHref}
            data-testid="empty-not-covered-link"
            className="text-accent underline underline-offset-2 motion-hover hover:opacity-80"
          >
            {labels.notCovered}
          </NextLink>
        </div>
      ) : (
        <>
          <ul
            data-testid="catalogue-grid"
            className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
          >
            {shown.map((item) => (
              <li
                key={item.name}
                data-testid="catalogue-item"
                data-integration={item.name}
                className="rounded-3 edge border-border p-3"
              >
                <NextLink
                  href={`/integrations/${encodeURIComponent(item.name)}${liveQuery === '' ? '' : `?${liveQuery}`}`}
                  scroll={false}
                  onClick={captureScrollPosition}
                  className="flex flex-col gap-1 motion-hover hover:opacity-80"
                >
                  <span className="text-strong">{item.displayName}</span>
                  <span className="text-meta text-muted">
                    {item.categoryLabel} · {item.summary}
                  </span>
                </NextLink>
              </li>
            ))}
          </ul>
          {pages > 1 ? (
            <Pagination
              page={boundedPage}
              pages={pages}
              onPage={(next) => {
                setPage(next);
                sync(withPage(state, next));
              }}
              labels={{
                landmark: message(locale, 'pagination.landmark'),
                previous: message(locale, 'pagination.previous'),
                next: message(locale, 'pagination.next'),
                position: message(locale, 'pagination.position', {
                  page: boundedPage,
                  pages,
                }),
              }}
            />
          ) : null}
        </>
      )}
    </div>
  );
}
