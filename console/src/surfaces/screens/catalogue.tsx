import { Fragment, type ReactNode } from 'react';

import { Badge } from '@/components/status';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import { capabilityRows, type CapabilityRow } from '../capability-rows';
import type { SurfaceContext } from '../context';
import { CredentialField } from '../credential';
import { credentialLabels, panelLabels } from '../labels';
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
 */

/** The permission the gateway requires to manage an integration. */
const MANAGE = 'integration.manage';

export const CATALOGUE_FILTERS: readonly FilterName[] = ['node'];

/** One domain's tools, in the order the domain was first seen. */
interface DomainGroup {
  readonly domain: string;
  readonly tools: readonly CapabilityRow[];
}

/**
 * Group `tools` by domain, first-seen order.
 *
 * A deployment declares its whole tool surface here — hundreds of rows for a
 * platform with several vendor integrations — and a flat table that long is
 * read by scrolling rather than by looking. The domain a tool already carries
 * is what an operator orients by ("what can it do against Kubernetes"), so it
 * becomes a heading instead of just a column value.
 */
function groupedByDomain(tools: readonly CapabilityRow[]): readonly DomainGroup[] {
  const order: string[] = [];
  const byDomain = new Map<string, CapabilityRow[]>();
  for (const tool of tools) {
    if (!byDomain.has(tool.domain)) {
      order.push(tool.domain);
      byDomain.set(tool.domain, []);
    }
    byDomain.get(tool.domain)?.push(tool);
  }
  return order.map((domain) => ({ domain, tools: byDomain.get(domain) ?? [] }));
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
  const skills = rows.filter((row) => row.kind === 'skill');
  const installed = list(dataOf(integrations), 'integrations');
  // What this catalogue does not cover, and why. Rendered greyed rather than
  // omitted: an operator evaluating the platform against their own stack finds
  // an absence by looking for it, which is the worst moment and the worst way.
  const gaps = list(dataOf(integrations), 'known_gaps');
  // Where an alert router posts is no longer here. 062 gave it the Data screen,
  // beside the deliveries it produces and the rules that decide what happens to
  // them — which is where somebody asking "why did nothing arrive" is standing.
  const none = message(locale, 'surface.none');

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
          <div className="w-full overflow-x-auto">
            <table className="w-full text-small">
              <caption className="sr-only">
                {message(locale, 'catalogue.title')}
              </caption>
              <thead>
                <tr>
                  {[
                    message(locale, 'catalogue.column.name'),
                    message(locale, 'catalogue.column.domain'),
                    message(locale, 'catalogue.column.effect'),
                    message(locale, 'catalogue.column.enabled'),
                  ].map((header) => (
                    <th
                      key={header}
                      scope="col"
                      className="text-left text-micro uppercase text-muted px-3 pb-2 edge border-border border-t-0 border-x-0"
                    >
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groupedByDomain(tools).map(({ domain, tools: domainTools }) => (
                  <Fragment key={domain === '' ? ' ' : domain}>
                    {domain === '' ? null : (
                      <tr data-testid="capability-domain" data-domain={domain}>
                        <th
                          scope="rowgroup"
                          colSpan={4}
                          className="text-left text-meta font-semibold text-strong bg-hover px-3 py-2 edge border-border border-t-0 border-x-0"
                        >
                          {domain}{' '}
                          <span className="text-muted font-normal">
                            ({domainTools.length})
                          </span>
                        </th>
                      </tr>
                    )}
                    {domainTools.map((tool) => (
                      <tr
                        key={tool.name}
                        data-testid="capability"
                        data-capability={tool.name}
                      >
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-all">
                          {tool.name}
                        </td>
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                          {tool.domain === '' ? none : tool.domain}
                        </td>
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                          <Badge status={tool.sideEffect} />
                        </td>
                        <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                          {!tool.known ? (
                            <span className="text-muted text-meta">{none}</span>
                          ) : tool.available ? (
                            <Badge status="healthy" />
                          ) : (
                            <span className="text-meta text-muted">
                              {message(locale, 'catalogue.blocked', {
                                integration: tool.reason === '' ? none : tool.reason,
                              })}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
                {skills.map((skill) => (
                  <tr key={skill.name} data-testid="capability">
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-all">
                      {skill.name}
                    </td>
                    <td
                      className="px-3 py-2 edge border-border border-t-0 border-x-0 text-muted"
                      colSpan={3}
                    >
                      {message(locale, 'catalogue.skills')} — {skill.summary}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
                  <li
                    key={name}
                    data-testid="integration"
                    data-integration={name}
                    className="flex flex-col gap-2"
                  >
                    <span className="flex items-center gap-2 flex-wrap">
                      <span className="text-strong">{name}</span>
                      <Badge status={text(integration, 'health')} />
                      <span className="text-meta text-muted">
                        {text(integration, 'health_detail')}
                      </span>
                    </span>
                    <CredentialField
                      integration={name}
                      // The catalogue knows the field *names* a vendor
                      // requires and nothing else about them; the guided
                      // first run reads the declared schema and has the
                      // labels and the help. Both are secret and required,
                      // which is what `required_credentials` means.
                      fields={list(integration, 'required_credentials').map(
                        (field) => ({
                          name: String(field),
                          label: String(field),
                          help: '',
                          secret: true,
                          required: true,
                        }),
                      )}
                      labels={credentialLabels(locale)}
                    />
                  </li>
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
