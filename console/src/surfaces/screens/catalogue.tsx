import type { ReactNode } from 'react';

import { message, type Locale } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import {
  type BrowsableSkill,
  type BrowsableTool,
  CapabilityBrowser,
} from '../capability-browser';
import { capabilityRows, type CapabilityRow } from '../capability-rows';
import type { SurfaceContext } from '../context';
import { IntegrationCard } from '../integration-card';
import { credentialLabels, panelLabels, verifyLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  list,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { placedTree } from '../tree';
import { readViewState, resolveNode, type FilterName } from '../url-state';

/**
 * What this deployment can do, what each of those needs, and whether this team
 * may run it.
 *
 * The last column is the one that makes the screen worth having. A catalogue of
 * everything the software could theoretically do is documentation; a catalogue
 * that says which entries are available *here*, and names the integration
 * blocking each one that is not, is an answer to "why did it not try that".
 *
 * "Here" is a node, which is why this screen reads the organisation tree before
 * it reads anything scoped. A deployment whose tree is empty resolves to no
 * node, and then the availability column is simply not asked for — asking would
 * mean building `/v1/config/{node_id}/catalogue` with nothing to put in it,
 * which is a broken request rather than an empty answer.
 *
 * Read-only browsing (233 tools, ~100 skills) and the write surface (85
 * credential forms) share this one route rather than a route each, for now —
 * splitting the write surface into its own screen under Settings is a bigger
 * change than this pass makes. What this pass does is stop the write surface
 * from *reading* like the browsing surface: every credential form is collapsed
 * behind a card that already says what state that integration is in, and
 * opening one is a decision rather than the default.
 */

/** The permission the gateway requires to manage an integration. */
const MANAGE = 'integration.manage';

/** The four words `health` can carry, and what each one means without expanding a card. */
const CREDENTIAL_STATES = ['unconfigured', 'unknown', 'healthy', 'degraded'] as const;

export const CATALOGUE_FILTERS: readonly FilterName[] = ['node'];

/** `rows`, restricted to the tools this node has an opinion about and blocking, rendered once. */
function browsableTools(
  rows: readonly CapabilityRow[],
  locale: Locale,
  none: string,
): readonly BrowsableTool[] {
  return rows
    .filter((row) => row.kind === 'tool')
    .map((row) => {
      if (!row.known || row.available) {
        return {
          name: row.name,
          domain: row.domain,
          sideEffect: row.sideEffect,
          known: row.known,
          available: row.available,
          blockedText: '',
          blockedLinked: false,
        };
      }
      // Structured data leads: what the node actually declares this tool
      // needs, not a parse of the deployment's own free-text reason — the
      // defect this replaces was exactly that free text ("needs the X
      // integration") concatenated after a second phrase ("Blocked by ").
      const linked = row.requiredIntegrations.length > 0;
      const blockedText = linked
        ? message(locale, 'catalogue.blocked', {
            integration: row.requiredIntegrations.join(', '),
          })
        : row.reason === ''
          ? none
          : row.reason;
      return {
        name: row.name,
        domain: row.domain,
        sideEffect: row.sideEffect,
        known: row.known,
        available: row.available,
        blockedText,
        blockedLinked: linked,
      };
    });
}

export async function CatalogueScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, search } = context;
  const state = readViewState(search, CATALOGUE_FILTERS);
  const init = authorised(credential);

  const [capabilities, tree, integrations] = await Promise.all([
    panelRead('/v1/capabilities', () => read('/v1/capabilities', init)),
    panelRead('/v1/config', () => read('/v1/config', init)),
    may(viewer, MANAGE)
      ? panelRead<unknown>('/v1/integrations', () => read('/v1/integrations', init))
      : Promise.resolve({ status: 'ready' as const, data: {} }),
  ]);

  const node = resolveNode(state, viewer, placedTree(dataOf(tree)));
  // Where a blocked tool's "connect it" link and a card's own credential form
  // both lead: this node's own Configuration, never a field-level anchor —
  // the idiom `autonomy.tsx` and `agent.tsx` already use for "go to where
  // this is controlled" (022 Detectors' confrontation names this pattern).
  const configurationHref =
    node === '' ? '/configuration' : `/configuration?node=${encodeURIComponent(node)}`;

  const entries =
    node === ''
      ? { status: 'ready' as const, data: {} as unknown }
      : await panelRead<unknown>('/v1/config/{node_id}/catalogue', () =>
          read('/v1/config/{node_id}/catalogue', {
            ...init,
            params: { node_id: node },
          }),
        );

  // The join both this screen and the agent screen read. Computed once, in one
  // module, because two screens holding two answers about which tools are
  // blocked is two answers an operator has to choose between.
  const rows = capabilityRows(dataOf(capabilities), dataOf(entries));
  const tools = rows.filter((row) => row.kind === 'tool');
  const skills: readonly BrowsableSkill[] = rows
    .filter((row) => row.kind === 'skill')
    .map((row) => ({ name: row.name, summary: row.summary }));
  const installed = list(dataOf(integrations), 'integrations');
  // What this catalogue does not cover, and why. Rendered greyed rather than
  // omitted: an operator evaluating the platform against their own stack finds
  // an absence by looking for it, which is the worst moment and the worst way.
  const gaps = list(dataOf(integrations), 'known_gaps');
  // Where an alert router posts is no longer here. 062 gave it the Data screen,
  // beside the deliveries it produces and the rules that decide what happens to
  // them — which is where somebody asking "why did nothing arrive" is standing.
  const none = message(locale, 'surface.none');

  const enabledCount = tools.filter((row) => row.known && row.available).length;
  const count = message(locale, 'catalogue.count', {
    enabled: enabledCount,
    total: tools.length,
  });

  const explanation = Object.fromEntries(
    CREDENTIAL_STATES.map((value) => [
      value,
      message(locale, `catalogue.credential.state.${value}`),
    ]),
  );

  // One panel, two reads. Without this the availability column renders "—" for
  // every entry when the catalogue read failed, which is the same thing it
  // renders for an entry nobody has an opinion about — a panel saying "we do
  // not know" in the words of "there is nothing to know".
  const catalogue = capabilities.status === 'error' ? capabilities : entries;

  return (
    <>
      <AreaHeader area={areaFor('catalogue')} locale={locale} />

      <div className="flex flex-col gap-5">
        <Panel
          title={message(locale, 'catalogue.tools')}
          state={stateOf(catalogue, tools.length === 0 && skills.length === 0)}
          dependency={dependencyOf(catalogue)}
          labels={panelLabels(locale, message(locale, 'catalogue.tools'))}
          empty={{
            heading: message(locale, 'catalogue.empty.heading'),
            body: message(locale, 'catalogue.empty.body'),
            actionLabel: message(locale, 'catalogue.empty.action'),
            href: '/configuration',
          }}
        >
          <CapabilityBrowser
            tools={browsableTools(rows, locale, none)}
            skills={skills}
            count={count}
            configurationHref={configurationHref}
            labels={{
              tableCaption: message(locale, 'catalogue.title'),
              search: message(locale, 'catalogue.search'),
              searchEmpty: message(locale, 'catalogue.search.empty'),
              domainsNav: message(locale, 'catalogue.domains.nav'),
              skillsHeading: message(locale, 'catalogue.skills'),
              columnName: message(locale, 'catalogue.column.name'),
              columnDomain: message(locale, 'catalogue.column.domain'),
              columnEffect: message(locale, 'catalogue.column.effect'),
              columnEnabled: message(locale, 'catalogue.column.enabled'),
              none,
              blockedAction: message(locale, 'catalogue.blocked.action'),
            }}
          />
        </Panel>

        {/* Absent, not disabled, for a viewer who may not manage integrations. */}
        {may(viewer, MANAGE) ? (
          <Panel
            title={message(locale, 'catalogue.integrations.title')}
            state={stateOf(integrations, installed.length === 0)}
            dependency={dependencyOf(integrations)}
            labels={panelLabels(
              locale,
              message(locale, 'catalogue.integrations.title'),
            )}
            empty={{
              heading: message(locale, 'catalogue.integrations.empty.heading'),
              body: message(locale, 'catalogue.integrations.empty.body'),
              actionLabel: message(locale, 'catalogue.integrations.empty.action'),
              href: '/configuration',
            }}
          >
            <ul className="flex flex-col gap-4">
              {installed.map((integration) => {
                const name = text(integration, 'name');
                return (
                  <IntegrationCard
                    key={name}
                    name={name}
                    health={text(integration, 'health')}
                    healthDetail={text(integration, 'health_detail')}
                    // The catalogue knows the field *names* a vendor requires
                    // and nothing else about them; the guided first run reads
                    // the declared schema and has the labels and the help.
                    // Both are secret and required, which is what
                    // `required_credentials` means.
                    fields={list(integration, 'required_credentials').map((field) => ({
                      name: String(field),
                      label: String(field),
                      help: '',
                      secret: true,
                      required: true,
                    }))}
                    labels={{
                      expand: message(locale, 'catalogue.integrations.expand'),
                      collapse: message(locale, 'catalogue.integrations.collapse'),
                      explanation,
                      credential: credentialLabels(locale),
                      verify: verifyLabels(locale),
                    }}
                  />
                );
              })}
            </ul>

            {gaps.length === 0 ? null : (
              <div className="flex flex-col gap-2 pt-4" data-testid="known-gaps">
                <p className="text-meta text-muted">
                  {message(locale, 'catalogue.gaps.title')}
                </p>
                <ul className="flex flex-col gap-2">
                  {gaps.map((gap) => (
                    <li
                      key={text(gap, 'integration')}
                      data-testid="known-gap"
                      data-integration={text(gap, 'integration')}
                      data-cause={text(gap, 'cause')}
                      className="flex flex-col gap-1 text-muted"
                    >
                      <span className="text-small">
                        {text(gap, 'display_name')}{' '}
                        <span className="text-meta">
                          {message(
                            locale,
                            text(gap, 'cause') === 'not_built'
                              ? 'catalogue.gaps.decided'
                              : 'catalogue.gaps.unreachable',
                          )}
                        </span>
                      </span>
                      <span className="text-meta">{text(gap, 'reason')}</span>
                      <span className="text-meta">
                        {message(locale, 'catalogue.gaps.resolution')}{' '}
                        {text(gap, 'resolution')}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Panel>
        ) : null}
      </div>
    </>
  );
}
