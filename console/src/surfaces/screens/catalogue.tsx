import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { CredentialField } from '../credential';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  flag,
  list,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';

/**
 * What this deployment can do, what each of those needs, and whether this team
 * may run it.
 *
 * The last column is the one that makes the screen worth having. A catalogue of
 * everything the software could theoretically do is documentation; a catalogue
 * that says which entries are available *here*, and names the integration
 * blocking each one that is not, is an answer to "why did it not try that".
 */

/** The permission the gateway requires to manage an integration. */
const MANAGE = 'integration.manage';

export async function CatalogueScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer } = context;
  const init = authorised(credential);
  const node = viewer.teamNodeId;

  const [capabilities, entries, integrations] = await Promise.all([
    panelRead('/v1/capabilities', () => read('/v1/capabilities', init)),
    panelRead('/v1/config/{node_id}/catalogue', () =>
      read('/v1/config/{node_id}/catalogue', { ...init, params: { node_id: node } }),
    ),
    may(viewer, MANAGE)
      ? panelRead<unknown>('/v1/integrations', () => read('/v1/integrations', init))
      : Promise.resolve({ status: 'ready' as const, data: {} }),
  ]);

  const tools = list(dataOf(capabilities), 'tools');
  const skills = list(dataOf(capabilities), 'skills');
  const available = new Map(
    list(dataOf(entries), 'entries').map((entry) => [
      text(entry, 'name'),
      { available: flag(entry, 'available'), reason: text(entry, 'reason') },
    ]),
  );
  const installed = list(dataOf(integrations), 'integrations');
  const none = message(locale, 'surface.none');

  return (
    <>
      <AreaHeader area={areaFor('catalogue')} locale={locale} />

      <div className="flex flex-col gap-5">
        <Panel
          title={message(locale, 'catalogue.tools')}
          state={stateOf(capabilities, tools.length === 0 && skills.length === 0)}
          dependency={dependencyOf(capabilities)}
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
                {tools.map((tool) => {
                  const name = text(tool, 'name');
                  const held = available.get(name);
                  return (
                    <tr key={name} data-testid="capability" data-capability={name}>
                      <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-all">
                        {name}
                      </td>
                      <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                        {text(tool, 'domain') === '' ? none : text(tool, 'domain')}
                      </td>
                      <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                        <Badge status={text(tool, 'side_effect_level')} />
                      </td>
                      <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                        {held === undefined ? (
                          <span className="text-muted text-meta">{none}</span>
                        ) : held.available ? (
                          <Badge status="healthy" />
                        ) : (
                          <span className="text-meta text-muted">
                            {message(locale, 'catalogue.blocked', {
                              integration: held.reason === '' ? none : held.reason,
                            })}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {skills.map((skill) => (
                  <tr key={text(skill, 'name')} data-testid="capability">
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-all">
                      {text(skill, 'name')}
                    </td>
                    <td
                      className="px-3 py-2 edge border-border border-t-0 border-x-0 text-muted"
                      colSpan={3}
                    >
                      {message(locale, 'catalogue.skills')} —{' '}
                      {text(skill, 'description')}
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
                      required={list(integration, 'required_credentials').map(String)}
                      labels={{
                        title: message(locale, 'catalogue.credential.title'),
                        replace: message(locale, 'catalogue.credential.replace'),
                        stored: message(locale, 'catalogue.credential.stored'),
                        absent: message(locale, 'catalogue.credential.absent'),
                        verify: message(locale, 'catalogue.integrations.verify'),
                      }}
                    />
                  </li>
                );
              })}
            </ul>
          </Panel>
        ) : null}
      </div>
    </>
  );
}
