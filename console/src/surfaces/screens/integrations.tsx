import type { ReactNode } from 'react';
import NextLink from 'next/link';

import { StatusChip } from '@/components/status';
import { resolveCta } from '@/design/empty-state';
import { message, type Locale } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { FilterBar, type FilterChoice } from '../filters';
import type { CredentialFieldSpec } from '../credential';
import {
  INTEGRATIONS_CATALOGUE_PAGE_SIZE,
  IntegrationCatalogueGrid,
  type CatalogueGridItem,
} from '../integration-catalogue';
import { IntegrationPanel, type PermissionSpec } from '../integration-panel';
import { credentialLabels, panelLabels } from '../labels';
import { Panel } from '../panel';
import { ScrollCapturingLink } from '../scroll-link';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  flag,
  list,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { hrefFor, readViewState, writeViewState, type FilterName } from '../url-state';

/**
 * What the Catalogue became: connected first, a suggestion the estate already
 * found in second place, and everything else a compact, searchable grid
 * rather than eighty-plus collapsed forms stacked one under another.
 *
 * Three sections, always in this order, each absent rather than empty:
 * Connected (any health but `unconfigured`, the failing ones included —
 * losing a credential does not send an integration back to the catalogue),
 * Suggested (unconnected, and the estate found it running), and the catalogue
 * grid (everything else). An integration is never drawn twice: once it is
 * suggested it leaves the grid, and once it is connected it leaves both.
 *
 * The credential form itself lives one address over,
 * `/integrations/<name>`, opened as a drawer over this screen rather than a
 * fourth section — `integration-panel.tsx` is the write half, this is the
 * read half, and the split is what lets the panel deep-link while the
 * catalogue keeps its own scroll position and filters underneath it.
 */

/** Every category `IntegrationCategory` declares, each with its own label. */
const CATEGORY_LABEL_KEYS: Readonly<Record<string, string>> = {
  logstore: 'catalogue.integrations.category.logstore',
  metrics: 'catalogue.integrations.category.metrics',
  tracing: 'catalogue.integrations.category.tracing',
  cloud_control_plane: 'catalogue.integrations.category.cloud_control_plane',
  database: 'catalogue.integrations.category.database',
  vcs: 'catalogue.integrations.category.vcs',
  cicd: 'catalogue.integrations.category.cicd',
  ticketing: 'catalogue.integrations.category.ticketing',
  incident: 'catalogue.integrations.category.incident',
  communication: 'catalogue.integrations.category.communication',
  data_platform: 'catalogue.integrations.category.data_platform',
  model_provider: 'catalogue.integrations.category.model_provider',
};

/**
 * `category`'s own label, or the raw word when this catalogue has never heard
 * of it — the same rule `StatusChip` holds for a status word it does not
 * recognise: legible, never blank, never invented as one of the known ones.
 */
function categoryLabel(locale: Locale, category: string): string {
  const key = CATEGORY_LABEL_KEYS[category];
  return key === undefined
    ? category
    : message(locale, key as Parameters<typeof message>[1]);
}

export const INTEGRATIONS_FILTERS: readonly FilterName[] = ['view', 'category', 'q'];

interface CatalogueItem {
  readonly name: string;
  readonly displayName: string;
  readonly category: string;
  readonly summary: string;
  readonly health: string;
  readonly healthDetail: string;
  readonly fields: readonly CredentialFieldSpec[];
  readonly capabilities: readonly string[];
  readonly permissions: readonly PermissionSpec[];
  readonly suggested?: { readonly address: string; readonly fromResource: string };
}

/** `record.name` read as a list of strings, dropping anything that is not one. */
function strings(record: unknown, name: string): readonly string[] {
  return list(record, name).filter((each): each is string => typeof each === 'string');
}

function fieldsOf(record: unknown): readonly CredentialFieldSpec[] {
  return list(record, 'fields').map((declared) => {
    const minScope = text(declared, 'min_scope');
    const guideUrl = text(declared, 'guide_url');
    return {
      name: text(declared, 'name'),
      label: text(declared, 'label'),
      help: text(declared, 'help'),
      secret: flag(declared, 'secret'),
      required: flag(declared, 'required'),
      ...(minScope === '' ? {} : { minScope }),
      ...(guideUrl === '' ? {} : { guideUrl }),
    };
  });
}

/**
 * The vendor permissions this integration's capabilities need, whole — the
 * declared, sondada content FR-006's "minimum permission" is about, read
 * from the catalogue rather than the per-field `min_scope` a schema mostly
 * leaves blank.
 */
function permissionsOf(record: unknown): readonly PermissionSpec[] {
  return list(record, 'permissions').map((declared) => ({
    name: text(declared, 'name'),
    grants: text(declared, 'grants'),
    where: text(declared, 'where'),
    capabilities: strings(declared, 'capabilities'),
  }));
}

/** Where the estate already found this vendor running, read rather than derived. */
function suggestionOf(
  record: unknown,
): { readonly address: string; readonly fromResource: string } | undefined {
  const found = field(record, 'suggested');
  if (found === null || found === undefined) return undefined;
  const address = text(found, 'address');
  return address === ''
    ? undefined
    : { address, fromResource: text(found, 'from_resource') };
}

function itemOf(record: unknown): CatalogueItem {
  const suggested = suggestionOf(record);
  return {
    name: text(record, 'name'),
    displayName: text(record, 'display_name'),
    category: text(record, 'category'),
    summary: text(record, 'summary'),
    health: text(record, 'health'),
    healthDetail: text(record, 'health_detail'),
    fields: fieldsOf(record),
    capabilities: strings(record, 'capabilities'),
    permissions: permissionsOf(record),
    ...(suggested === undefined ? {} : { suggested }),
  };
}

/**
 * The catalogue, and — when `name` names one — the credential panel open over
 * it. `name` comes from the dynamic route segment
 * (`/integrations/[name]/page.tsx`); the plain `/integrations` route calls
 * this the same way with no name at all, so the two addresses render the
 * identical catalogue and differ only in whether the drawer is open.
 */
export async function IntegrationsScreen(
  context: SurfaceContext,
  name?: string,
): Promise<ReactNode> {
  const { credential, locale, search, viewer } = context;
  const state = readViewState(search, INTEGRATIONS_FILTERS);
  const init = authorised(credential);
  const writable = may(viewer, 'integration.manage');

  const integrations = await panelRead<unknown>('/v1/integrations', () =>
    read('/v1/integrations', init),
  );
  const installed = list(dataOf(integrations), 'integrations').map(itemOf);
  const gaps = list(dataOf(integrations), 'known_gaps');

  // Connected is every health but `unconfigured` — `unknown` (stored, never
  // checked) and `degraded` (failing) both count. A stored-but-unverified or
  // a failing credential never falls back to the catalogue grid; only the
  // absence of one does.
  const connected = installed.filter((item) => item.health !== 'unconfigured');
  const notConnected = installed.filter((item) => item.health === 'unconfigured');
  // An integration the estate found running is never also connected — that
  // combination cannot reach this filter, because `connected` already took it.
  const suggested = notConnected.filter((item) => item.suggested !== undefined);
  const catalogueRest = notConnected.filter((item) => item.suggested === undefined);

  const chosenView = state.filters.view;
  const chosenCategory = state.filters.category;
  const matchesCategory = (item: CatalogueItem): boolean =>
    chosenCategory === undefined || item.category === chosenCategory;

  const visibleConnected = (chosenView === 'suggested' ? [] : connected).filter(
    matchesCategory,
  );
  const visibleSuggested = (chosenView === 'connected' ? [] : suggested).filter(
    matchesCategory,
  );
  const visibleCatalogueRest = (chosenView === undefined ? catalogueRest : []).filter(
    matchesCategory,
  );

  const presentCategories = Array.from(
    new Set(installed.map((item) => item.category)),
  ).sort();
  const choices: readonly FilterChoice[] = [
    ...(connected.length === 0 && suggested.length === 0
      ? []
      : [
          {
            name: 'view' as const,
            label: message(locale, 'catalogue.integrations.state'),
            options: [
              ...(connected.length > 0
                ? [
                    {
                      value: 'connected',
                      label: message(
                        locale,
                        'catalogue.integrations.filter.view.connected',
                        {
                          count: connected.length,
                        },
                      ),
                    },
                  ]
                : []),
              ...(suggested.length > 0
                ? [
                    {
                      value: 'suggested',
                      label: message(
                        locale,
                        'catalogue.integrations.filter.view.suggested',
                        {
                          count: suggested.length,
                        },
                      ),
                    },
                  ]
                : []),
            ],
          },
        ]),
    ...(presentCategories.length === 0
      ? []
      : [
          {
            name: 'category' as const,
            label: message(locale, 'catalogue.integrations.filter.category'),
            options: presentCategories.map((category) => ({
              value: category,
              label: categoryLabel(locale, category),
            })),
          },
        ]),
  ];

  const notCoveredHref = resolveCta({ route: '/integrations/not-covered' }).href;
  const closeHref = hrefFor('/integrations', state, INTEGRATIONS_FILTERS);
  // A card's own link carries the current filters, so closing the panel it
  // opens returns to the same view rather than to the address with nothing
  // on it: `closeHref` is read from the *detail* route's own address, and a
  // link that dropped the query here is a link that closes back to "All".
  const catalogueQuery = writeViewState(state, INTEGRATIONS_FILTERS);
  const detailHref = (integration: string): string =>
    `/integrations/${encodeURIComponent(integration)}${catalogueQuery === '' ? '' : `?${catalogueQuery}`}`;

  const panelItem =
    name === undefined ? null : (installed.find((item) => item.name === name) ?? null);

  const gridItems: readonly CatalogueGridItem[] = visibleCatalogueRest.map((item) => ({
    name: item.name,
    displayName: item.displayName,
    category: item.category,
    categoryLabel: categoryLabel(locale, item.category),
    summary: item.summary,
    capabilities: item.capabilities,
  }));

  return (
    <>
      <AreaHeader area={areaFor('integrations')} locale={locale} />

      <Panel
        title={message(locale, 'catalogue.integrations.title')}
        state={stateOf(integrations, installed.length === 0)}
        dependency={dependencyOf(integrations)}
        labels={panelLabels(locale, message(locale, 'catalogue.integrations.title'))}
        bare
        empty={{
          heading: message(locale, 'catalogue.integrations.empty.heading'),
          body: message(locale, 'catalogue.integrations.empty.body'),
          actionLabel: message(locale, 'catalogue.integrations.empty.action'),
          href: '/configuration',
        }}
      >
        <div className="flex flex-col gap-5">
          <p className="text-meta text-muted" data-testid="catalogue-summary">
            {suggested.length > 0
              ? message(locale, 'catalogue.integrations.summary.suggested', {
                  total: installed.length,
                  connected: connected.length,
                  suggested: suggested.length,
                })
              : message(locale, 'catalogue.integrations.summary', {
                  total: installed.length,
                  connected: connected.length,
                })}
          </p>

          {choices.length === 0 ? null : (
            <FilterBar
              path="/integrations"
              state={state}
              filters={INTEGRATIONS_FILTERS}
              anyLabel={message(locale, 'surface.filter.any')}
              choices={choices}
            />
          )}

          {visibleConnected.length === 0 ? null : (
            <section data-testid="connected-section" className="flex flex-col gap-2">
              <h2 className="text-micro uppercase tracking-wide text-muted">
                {message(locale, 'catalogue.integrations.connected.title')}
              </h2>
              <ul className="flex flex-col gap-2">
                {visibleConnected.map((item) => (
                  <li
                    key={item.name}
                    data-testid="connected-integration"
                    data-integration={item.name}
                    className="flex flex-wrap items-center gap-3 rounded-3 edge border-border p-3"
                  >
                    <span className="text-strong">{item.displayName}</span>
                    <span className="text-meta text-muted">
                      {categoryLabel(locale, item.category)} · {item.summary}
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
                      href={detailHref(item.name)}
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

          {visibleSuggested.length === 0 ? null : (
            <section
              data-testid="suggested-section"
              className="flex flex-col gap-2 rounded-3 edge border-accent p-3"
            >
              <h2 className="text-micro uppercase tracking-wide text-accent">
                {message(locale, 'catalogue.integrations.suggested.title')}
              </h2>
              <ul className="flex flex-col gap-2">
                {visibleSuggested.map((item) => (
                  <li
                    key={item.name}
                    data-testid="suggested-integration"
                    data-integration={item.name}
                    className="flex flex-wrap items-center gap-3"
                  >
                    <span className="text-strong">{item.displayName}</span>
                    <span
                      className="text-meta text-accent"
                      data-testid="suggestion-evidence"
                    >
                      {message(locale, 'catalogue.integrations.suggested.evidence', {
                        address: item.suggested?.address ?? '',
                        resource: item.suggested?.fromResource ?? '',
                      })}
                    </span>
                    <ScrollCapturingLink
                      href={detailHref(item.name)}
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

          <IntegrationCatalogueGrid
            locale={locale}
            path="/integrations"
            state={state}
            filters={INTEGRATIONS_FILTERS}
            items={gridItems}
            pageSize={INTEGRATIONS_CATALOGUE_PAGE_SIZE}
            notCoveredHref={notCoveredHref}
            labels={{
              search: message(locale, 'catalogue.integrations.search.label'),
              emptyHeading: message(
                locale,
                'catalogue.integrations.search.empty.heading',
              ),
              emptyBody: message(locale, 'catalogue.integrations.search.empty.body'),
              emptyClear: message(locale, 'catalogue.integrations.search.empty.clear'),
              notCovered: message(locale, 'catalogue.notCovered.title'),
            }}
          />

          {gaps.length === 0 ? null : (
            <p className="text-meta text-muted">
              <NextLink
                href={notCoveredHref}
                data-testid="not-covered-link"
                className="text-accent underline underline-offset-2 motion-hover hover:opacity-80"
              >
                {message(locale, 'catalogue.integrations.footer.gaps', {
                  count: gaps.length,
                })}
              </NextLink>
            </p>
          )}
        </div>
      </Panel>

      {name === undefined ? null : (
        <IntegrationPanel
          locale={locale}
          requestedName={name}
          item={
            panelItem === null
              ? null
              : {
                  name: panelItem.name,
                  displayName: panelItem.displayName,
                  categoryLabel: categoryLabel(locale, panelItem.category),
                  summary: panelItem.summary,
                  health: panelItem.health,
                  healthDetail: panelItem.healthDetail,
                  fields: panelItem.fields,
                  permissions: panelItem.permissions,
                }
          }
          closeHref={closeHref}
          writable={writable}
          labels={{
            close: message(locale, 'catalogue.integrations.panel.close'),
            credential: {
              ...credentialLabels(locale),
              submit: message(locale, 'catalogue.integrations.panel.saveAndTest'),
              sending: message(locale, 'catalogue.integrations.panel.testing'),
            },
            security: message(locale, 'catalogue.integrations.panel.security'),
            notFound: message(locale, 'catalogue.integrations.panel.notFound'),
            notFoundAction: message(
              locale,
              'catalogue.integrations.panel.notFound.action',
            ),
            testing: message(locale, 'catalogue.integrations.panel.testing'),
            unreachable: message(locale, 'firstRun.unreachable'),
            readOnly: message(locale, 'catalogue.integrations.panel.readOnly'),
            permissionsHeading: message(
              locale,
              'catalogue.integrations.panel.permissions.heading',
            ),
            grantedAt: message(
              locale,
              'catalogue.integrations.panel.permissions.grantedAt',
            ),
          }}
        />
      )}
    </>
  );
}
