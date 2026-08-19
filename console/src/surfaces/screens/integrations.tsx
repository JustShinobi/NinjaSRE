import type { ReactNode } from 'react';
import NextLink from 'next/link';

import { resolveCta } from '@/design/empty-state';
import { message, type Locale } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import {
  AdvancedConfigSection,
  advancedConfigSectionId,
} from '../advanced-config-section';
import { FilterBar, type FilterChoice } from '../filters';
import type { CredentialFieldSpec } from '../credential';
import {
  IntegrationCatalogue,
  type CatalogueConnectedItem,
  type CatalogueGridItem,
  type CatalogueSuggestedItem,
} from '../integration-catalogue';
import { IntegrationPanel, type PermissionSpec } from '../integration-panel';
import { credentialLabels, panelLabels } from '../labels';
import { Panel } from '../panel';
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
import { placedTree } from '../tree';
import { hrefFor, readViewState, resolveNode, type FilterName } from '../url-state';

/**
 * What the Catalogue became: connected first, a suggestion the estate already
 * found in second place, and everything else named Available rather than
 * eighty-plus collapsed forms stacked one under another — no paging, because
 * the whole post-cut catalogue fits inside the scroll budget on its own.
 *
 * Three sections, always in this order, each absent rather than empty:
 * Connected (any health but `unconfigured`, the failing ones included —
 * losing a credential does not send an integration back to the catalogue),
 * Suggested (unconnected, and the estate found it running), and Available
 * (everything else). An integration is never drawn twice: once it is
 * suggested it leaves Available, and once it is connected it leaves both.
 * This module computes the three lists — view/category filtered, exactly as
 * the API and the address bar say — and hands them to `IntegrationCatalogue`,
 * which owns the one search box that narrows all three at once.
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

export const INTEGRATIONS_FILTERS: readonly FilterName[] = [
  'view',
  'category',
  'q',
  'node',
];

/** The permission the gateway requires to change the `integrations.active` list itself. */
const CONFIG_WRITE = 'config.write';

/** The one field this section owns: the configured-vendor list, as the schema declares it. */
const INTEGRATIONS_ADVANCED_PREFIX = 'integrations.';

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
  readonly suggested?: {
    readonly address: string;
    readonly fromResource: string;
    readonly resourceLabel: string;
    readonly resourceKind: string;
  };
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
 * The vendor permissions this integration's capabilities need, whole — read
 * from the catalogue's own declared permission entries rather than the
 * per-field `min_scope` a schema mostly leaves blank.
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
function suggestionOf(record: unknown): CatalogueItem['suggested'] {
  const found = field(record, 'suggested');
  if (found === null || found === undefined) return undefined;
  const address = text(found, 'address');
  return address === ''
    ? undefined
    : {
        address,
        fromResource: text(found, 'from_resource'),
        resourceLabel: text(found, 'resource_label'),
        resourceKind: text(found, 'resource_kind'),
      };
}

/**
 * The evidence sentence for one suggestion: the resource's own legible name
 * when the estate resolved one, and address-plus-kind — never the raw
 * identifier — when it did not. The identifier itself is never dropped: it
 * stays recoverable as `data-resource` on the row this renders inside, which
 * is where a technical reader looks for it rather than inside the sentence a
 * casual one reads.
 */
function evidenceOf(locale: Locale, suggestion: CatalogueItem['suggested']): string {
  const address = suggestion?.address ?? '';
  const resourceLabel = suggestion?.resourceLabel ?? '';
  return resourceLabel === ''
    ? message(locale, 'catalogue.integrations.suggested.evidence.unresolved', {
        address,
        kind: suggestion?.resourceKind ?? '',
      })
    : message(locale, 'catalogue.integrations.suggested.evidence', {
        address,
        resource: resourceLabel,
      });
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
  const configWritable = may(viewer, CONFIG_WRITE);

  const integrations = await panelRead<unknown>('/v1/integrations', () =>
    read('/v1/integrations', init),
  );
  const installed = list(dataOf(integrations), 'integrations').map(itemOf);
  const gaps = list(dataOf(integrations), 'known_gaps');

  // The configured-vendor list (`integrations.active`) is a field of the same
  // hierarchical configuration every Settings page edits — read the same way
  // every one of them does, so its advanced section below can offer the same
  // preview-before-save `ConfigEditor` rather than a second write path.
  const tree = await panelRead('/v1/config', () => read('/v1/config', init));
  const nodeId = resolveNode(state, viewer, placedTree(dataOf(tree)));
  const nothing = { status: 'ready' as const, data: {} as unknown };
  // Read regardless of `configWritable`: the advanced section's own
  // effective-value table shows every viewer of this page what a field
  // resolves to, not only one who may change it.
  const configFields =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/config/{node_id}/fields', () =>
          read('/v1/config/{node_id}/fields', { ...init, params: { node_id: nodeId } }),
        );

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
  // Read from the *detail* route's own address, not built here: closing the
  // panel returns to whatever `IntegrationCatalogue` has on the address bar
  // at that moment (including a search still mid-keystroke), never to a
  // snapshot of the address this render started with.
  const closeHref = hrefFor('/integrations', state, INTEGRATIONS_FILTERS);

  const panelItem =
    name === undefined ? null : (installed.find((item) => item.name === name) ?? null);

  const connectedItems: readonly CatalogueConnectedItem[] = visibleConnected.map(
    (item) => ({
      name: item.name,
      displayName: item.displayName,
      category: item.category,
      categoryLabel: categoryLabel(locale, item.category),
      summary: item.summary,
      capabilities: item.capabilities,
      health: item.health,
      healthDetail: item.healthDetail,
    }),
  );

  const suggestedItems: readonly CatalogueSuggestedItem[] = visibleSuggested.map(
    (item) => ({
      name: item.name,
      displayName: item.displayName,
      category: item.category,
      categoryLabel: categoryLabel(locale, item.category),
      summary: item.summary,
      capabilities: item.capabilities,
      evidence: evidenceOf(locale, item.suggested),
      fromResource: item.suggested?.fromResource ?? '',
    }),
  );

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
          // The raw list this same page now owns, below, rather than the
          // retired editor.
          href: `#${advancedConfigSectionId(INTEGRATIONS_ADVANCED_PREFIX)}`,
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

          <IntegrationCatalogue
            locale={locale}
            path="/integrations"
            state={state}
            filters={INTEGRATIONS_FILTERS}
            connected={connectedItems}
            suggested={suggestedItems}
            available={gridItems}
            notCoveredHref={notCoveredHref}
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

      <div className="mt-5">
        <AdvancedConfigSection
          title={message(locale, 'catalogue.integrations.advanced.title')}
          prefix={INTEGRATIONS_ADVANCED_PREFIX}
          nodeId={nodeId}
          locale={locale}
          writable={configWritable}
          fields={[]}
          rawFields={dataOf(configFields)}
        />
      </div>

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
                  // The estate's own discovery, never a vendor's default port
                  // or a constant on this screen — the same field the
                  // Suggested section above already reads. Empty for
                  // anything the estate has not found, which renders no
                  // placeholder at all rather than an invented one.
                  discoveredAddress: panelItem.suggested?.address ?? '',
                }
          }
          closeHref={closeHref}
          notCoveredHref={notCoveredHref}
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
            notFoundRoadmap: message(locale, 'catalogue.notCovered.title'),
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
            foundHere: message(locale, 'firstRun.integrations.foundHere'),
            storedInVault: message(
              locale,
              'catalogue.integrations.panel.storedInVault',
            ),
            testAgain: message(locale, 'catalogue.integrations.panel.testAgain'),
            replaceCredential: message(
              locale,
              'catalogue.integrations.panel.replaceCredential',
            ),
            cancel: message(locale, 'catalogue.integrations.panel.cancel'),
            disconnect: message(locale, 'catalogue.integrations.panel.disconnect'),
            disconnectConsequence: message(
              locale,
              'catalogue.integrations.panel.disconnect.consequence',
            ),
          }}
        />
      )}
    </>
  );
}
