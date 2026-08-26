'use client';

import { useMemo, useState, type ReactNode } from 'react';
import NextLink from 'next/link';
import { useRouter } from 'next/navigation';

import { Input } from '@/components/form';
import { StatusChip } from '@/components/status';
import { EmptyState } from '@/components/state';
import { message, type Locale } from '@/i18n/messages';
import { captureScrollPosition } from './scroll-memory';
import { ScrollCapturingLink } from './scroll-link';
import {
  hrefFor,
  withFilter,
  writeViewState,
  type FilterName,
  type ViewState,
} from './url-state';

/**
 * The catalogue's three sections and the one search box over all of them,
 * entirely on the client.
 *
 * Connected, Suggested and Available are three views of the same, already
 * fetched list — one read served the whole thing, so narrowing all three as
 * somebody types is arithmetic over arrays already in memory, never a second
 * request. What still reaches the address bar is the *result* of that
 * arithmetic: every keystroke updates the visible sections immediately and
 * replaces the address without a scroll jump, so a link somebody sends still
 * opens filtered the same way, and a reload resumes it.
 *
 * A section that has nothing left to show — whether nothing was ever in it or
 * nothing left matches — is absent rather than drawn empty. Only when every
 * section empties at once does the page say so, with the same action a bare
 * catalogue offers: clear the search, or read what left for the roadmap.
 */

export interface CatalogueSearchable {
  readonly displayName: string;
  readonly category: string;
  readonly summary: string;
  readonly capabilities: readonly string[];
}

export interface CatalogueConnectedItem extends CatalogueSearchable {
  readonly name: string;
  readonly categoryLabel: string;
  readonly health: string;
  readonly healthDetail: string;
}

export interface CatalogueSuggestedItem extends CatalogueSearchable {
  readonly name: string;
  readonly categoryLabel: string;
  /** The evidence sentence, already rendered — see `evidenceOf` in the screen. */
  readonly evidence: string;
  /** The estate's own identifier for the resource, recoverable as `data-resource`. */
  readonly fromResource: string;
}

export interface CatalogueGridItem extends CatalogueSearchable {
  readonly name: string;
  readonly categoryLabel: string;
}

export interface IntegrationCatalogueProps {
  readonly locale: Locale;
  readonly path: string;
  readonly state: ViewState;
  readonly filters: readonly FilterName[];
  readonly connected: readonly CatalogueConnectedItem[];
  readonly suggested: readonly CatalogueSuggestedItem[];
  readonly available: readonly CatalogueGridItem[];
  /** Where the "not covered" reference page is, resolved by the caller. */
  readonly notCoveredHref: string;
}

/** What a search matches against: display name, raw category, summary, capabilities. */
function haystack(item: CatalogueSearchable): string {
  return `${item.displayName} ${item.category} ${item.summary} ${item.capabilities.join(' ')}`.toLowerCase();
}

function narrow<T extends CatalogueSearchable>(
  items: readonly T[],
  needle: string,
): readonly T[] {
  return needle === ''
    ? items
    : items.filter((item) => haystack(item).includes(needle));
}

/** The catalogue: search, then Connected, Suggested and Available, in that order. */
export function IntegrationCatalogue({
  locale,
  path,
  state,
  filters,
  connected,
  suggested,
  available,
  notCoveredHref,
}: IntegrationCatalogueProps): ReactNode {
  const router = useRouter();
  const [query, setQuery] = useState(state.filters.q ?? '');
  const needle = query.trim().toLowerCase();

  const matchingConnected = useMemo(
    () => narrow(connected, needle),
    [connected, needle],
  );
  const matchingSuggested = useMemo(
    () => narrow(suggested, needle),
    [suggested, needle],
  );
  const matchingAvailable = useMemo(
    () => narrow(available, needle),
    [available, needle],
  );

  // What the address actually carries right now — the live search, composed
  // with whatever else is already in `state` (`view`, `category`). A card's
  // own link is built from this, not from `state` alone, so opening one while
  // a search is still mid-keystroke still returns to it: closing the panel
  // reads the detail route's own address, and a card link with a stale query
  // would close back to a filter nobody is looking at any more.
  const liveState = withFilter(state, 'q', query);
  const liveQuery = writeViewState(liveState, filters);
  const hrefTo = (name: string): string =>
    `/integrations/${encodeURIComponent(name)}${liveQuery === '' ? '' : `?${liveQuery}`}`;

  function sync(nextQuery: string): void {
    router.replace(hrefFor(path, withFilter(state, 'q', nextQuery), filters), {
      scroll: false,
    });
  }

  const nothingMatches =
    matchingConnected.length === 0 &&
    matchingSuggested.length === 0 &&
    matchingAvailable.length === 0;

  return (
    <div className="flex flex-col gap-5">
      <div data-testid="catalogue-search">
        <Input
          label={message(locale, 'catalogue.integrations.search.label')}
          name="catalogue-search"
          type="search"
          value={query}
          onValueChange={(value) => {
            setQuery(value);
            sync(value);
          }}
        />
      </div>

      {nothingMatches ? (
        <div className="flex flex-col items-center gap-3">
          <EmptyState
            heading={message(locale, 'catalogue.integrations.search.empty.heading')}
            body={message(locale, 'catalogue.integrations.search.empty.body')}
            action={{
              label: message(locale, 'catalogue.integrations.search.empty.clear'),
              href: hrefFor(path, withFilter(state, 'q', ''), filters),
            }}
          />
          <NextLink
            href={notCoveredHref}
            data-testid="empty-not-covered-link"
            className="text-accent underline underline-offset-2 motion-hover hover:opacity-80"
          >
            {message(locale, 'catalogue.notCovered.title')}
          </NextLink>
        </div>
      ) : (
        <>
          {matchingConnected.length === 0 ? null : (
            <section data-testid="connected-section" className="flex flex-col gap-2">
              <h2 className="text-micro tracking-wide text-muted">
                {message(locale, 'catalogue.integrations.connected.title')}
              </h2>
              <ul className="flex flex-col gap-2">
                {matchingConnected.map((item) => (
                  <li
                    key={item.name}
                    data-testid="connected-integration"
                    data-integration={item.name}
                    className="flex flex-wrap items-center gap-3 rounded-3 edge border-border p-3"
                  >
                    <span className="text-strong">{item.displayName}</span>
                    <span className="text-meta text-muted">
                      {item.categoryLabel} · {item.summary}
                    </span>
                    {item.healthDetail === '' ? null : (
                      <span
                        className="text-meta text-muted"
                        data-testid="connected-health-detail"
                      >
                        {item.healthDetail}
                      </span>
                    )}
                    <StatusChip
                      locale={locale}
                      status={item.health}
                      className="ml-auto"
                    />
                    <ScrollCapturingLink
                      href={hrefTo(item.name)}
                      data-testid="manage-integration"
                      className="text-accent underline underline-offset-2 motion-hover hover:opacity-80"
                    >
                      {message(locale, 'catalogue.integrations.connected.manage')}
                    </ScrollCapturingLink>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {matchingSuggested.length === 0 ? null : (
            <section
              data-testid="suggested-section"
              className="flex flex-col gap-2 rounded-3 edge border-accent p-3"
            >
              <h2 className="text-micro tracking-wide text-accent">
                {message(locale, 'catalogue.integrations.suggested.title')}
              </h2>
              <ul className="flex flex-col gap-2">
                {matchingSuggested.map((item) => (
                  <li
                    key={item.name}
                    data-testid="suggested-integration"
                    data-integration={item.name}
                    // The estate's own identifier for the resource this
                    // suggestion came from — never in the evidence sentence
                    // below, always recoverable here for a technical reader.
                    data-resource={item.fromResource}
                    className="flex flex-wrap items-center gap-3"
                  >
                    <span className="text-strong">{item.displayName}</span>
                    <span
                      className="text-meta text-accent"
                      data-testid="suggestion-evidence"
                    >
                      {item.evidence}
                    </span>
                    <ScrollCapturingLink
                      href={hrefTo(item.name)}
                      data-testid="connect-suggested"
                      className="ml-auto text-on-accent bg-accent rounded-2 edge border-accent px-3 py-1 text-meta motion-hover hover:opacity-90"
                    >
                      {message(locale, 'catalogue.integrations.suggested.connect')}
                    </ScrollCapturingLink>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {matchingAvailable.length === 0 ? null : (
            <section data-testid="available-section" className="flex flex-col gap-2">
              <h2 className="text-micro tracking-wide text-muted">
                {message(locale, 'catalogue.integrations.available.title')}
              </h2>
              <ul
                data-testid="catalogue-grid"
                className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
              >
                {matchingAvailable.map((item) => (
                  <li
                    key={item.name}
                    data-testid="catalogue-item"
                    data-integration={item.name}
                    className="rounded-3 edge border-border p-3"
                  >
                    <NextLink
                      href={hrefTo(item.name)}
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
            </section>
          )}
        </>
      )}
    </div>
  );
}
