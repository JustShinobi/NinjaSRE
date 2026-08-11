import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import { capabilityRows } from '../capability-rows';
import type { SurfaceContext } from '../context';
import { CredentialField } from '../credential';
import { DeliveryToken } from '../ingress';
import { credentialLabels, panelLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  list,
  optionalRead,
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

export async function CatalogueScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, search } = context;
  const state = readViewState(search, CATALOGUE_FILTERS);
  const init = authorised(credential);

  const [capabilities, tree, integrations, ingress] = await Promise.all([
    panelRead('/v1/capabilities', () => read('/v1/capabilities', init)),
    panelRead('/v1/config', () => read('/v1/config', init)),
    may(viewer, MANAGE)
      ? panelRead<unknown>('/v1/integrations', () => read('/v1/integrations', init))
      : Promise.resolve({ status: 'ready' as const, data: {} }),
    // Where an alert router posts. Optional and manage-only: a viewer has no
    // use for a map of every way into the deployment, and a build serving it is
    // not something a deployment has to have configured.
    may(viewer, MANAGE)
      ? optionalRead('/v1/ingress/sources', () => read('/v1/ingress/sources', init))
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
  // The receivers this build serves, and what to paste into each sender. The
  // one step of the alert loop that happens outside this deployment, so the
  // most it can do is be exact about it.
  const receivers = list(dataOf(ingress), 'sources');
  const deliveryPermission = text(dataOf(ingress), 'delivery_permission');
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
                {tools.map((tool) => (
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

        {receivers.length === 0 ? null : (
          <Panel
            title={message(locale, 'ingress.title')}
            state="ready"
            labels={panelLabels(locale, message(locale, 'ingress.title'))}
            empty={{
              heading: message(locale, 'ingress.title'),
              body: message(locale, 'ingress.body'),
              actionLabel: message(locale, 'catalogue.empty.action'),
              href: '/configuration',
            }}
          >
            <div className="flex flex-col gap-3" data-testid="ingress">
              <p className="text-meta text-muted">{message(locale, 'ingress.body')}</p>
              <ul className="flex flex-col gap-3">
                {receivers.map((receiver) => (
                  <li
                    key={text(receiver, 'source')}
                    data-testid="ingress-source"
                    data-source={text(receiver, 'source')}
                    className="flex flex-col gap-1"
                  >
                    <span className="text-small text-strong">
                      {text(receiver, 'source')}
                    </span>
                    <code className="text-meta break-all">{text(receiver, 'url')}</code>
                    <span className="text-meta text-muted">
                      {text(receiver, 'expects')}
                    </span>
                    <span className="text-meta text-muted">
                      {message(locale, 'ingress.verification')}{' '}
                      {text(receiver, 'verification')}
                    </span>
                  </li>
                ))}
              </ul>
              {deliveryPermission === '' ? null : (
                <DeliveryToken
                  permission={deliveryPermission}
                  labels={{
                    issue: message(locale, 'ingress.token.issue'),
                    issuing: message(locale, 'ingress.token.issuing'),
                    shownOnce: message(locale, 'ingress.token.shownOnce'),
                    failed: message(locale, 'ingress.token.failed'),
                    unreachable: message(locale, 'ingress.token.unreachable'),
                  }}
                />
              )}
            </div>
          </Panel>
        )}

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
