import type { ReactNode } from 'react';

import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { FilterBar, type FilterChoice } from '../filters';
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
import { readViewState, type FilterName } from '../url-state';

/**
 * What the Catalogue used to be, for the write half of it: every integration
 * this deployment can hold a credential for, its real state, and a way to
 * test it.
 *
 * Extracted from Catalogue rather than kept as a second panel on it: the
 * first run points here, a blocked tool's "connect it" link points here, and
 * there is no third place a credential is entered from. What used to be the
 * Catalogue's own read half — tools and skills, in read mode, with search —
 * moved to The agent's own Tools tab instead, because reading what the agent
 * can do is a question about the agent, not about credentials.
 *
 * No permission branching inside this screen: `routes.ts` gates the whole
 * area on `integration.manage`, the same permission the gateway's own
 * `GET /v1/integrations` already requires, so anybody who can reach this
 * screen at all already holds what every card on it needs.
 *
 * **Eighty-five is a search, not a scroll.** The one filter this screen
 * offers is the same word every card already shows on its badge — narrowing
 * by state is narrowing by the thing an operator opened this screen to check
 * in the first place, so it needed no control the console had not already
 * built for exactly this shape (`FilterBar`, bound to the address the way
 * every other screen's filter is).
 */

/** The four words `health` can carry, and what each one means without expanding a card. */
const CREDENTIAL_STATES = ['unconfigured', 'unknown', 'healthy', 'degraded'] as const;

export const INTEGRATIONS_FILTERS: readonly FilterName[] = ['state'];

export async function IntegrationsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, search } = context;
  const state = readViewState(search, INTEGRATIONS_FILTERS);
  const init = authorised(credential);

  const integrations = await panelRead<unknown>('/v1/integrations', () =>
    read('/v1/integrations', init),
  );
  const installed = list(dataOf(integrations), 'integrations');
  // What this catalogue does not cover, and why. Rendered greyed rather than
  // omitted: an operator evaluating the platform against their own stack finds
  // an absence by looking for it, which is the worst moment and the worst way.
  const gaps = list(dataOf(integrations), 'known_gaps');

  const explanation = Object.fromEntries(
    CREDENTIAL_STATES.map((value) => [
      value,
      message(locale, `catalogue.credential.state.${value}`),
    ]),
  );

  const chosen = state.filters.state;
  const filtered =
    chosen === undefined
      ? installed
      : installed.filter((integration) => text(integration, 'health') === chosen);

  // Offered only for a state this dataset actually has, so the control never
  // promises a result nothing behind it can produce.
  const present = new Set(installed.map((integration) => text(integration, 'health')));
  const choices: readonly FilterChoice[] = [
    {
      name: 'state',
      label: message(locale, 'catalogue.integrations.state'),
      options: CREDENTIAL_STATES.filter((value) => present.has(value)).map((value) => ({
        value,
        label: message(locale, `catalogue.integrations.filter.state.${value}`),
      })),
    },
  ].filter((choice) => choice.options.length > 0);

  return (
    <>
      <AreaHeader area={areaFor('integrations')} locale={locale} />

      <FilterBar
        path="/integrations"
        state={state}
        filters={INTEGRATIONS_FILTERS}
        anyLabel={message(locale, 'surface.filter.any')}
        choices={choices}
      />

      <Panel
        title={message(locale, 'catalogue.integrations.title')}
        state={stateOf(integrations, filtered.length === 0)}
        dependency={dependencyOf(integrations)}
        labels={panelLabels(locale, message(locale, 'catalogue.integrations.title'))}
        empty={{
          heading: message(locale, 'catalogue.integrations.empty.heading'),
          body: message(locale, 'catalogue.integrations.empty.body'),
          actionLabel: message(locale, 'catalogue.integrations.empty.action'),
          href: '/configuration',
        }}
      >
        <ul className="flex flex-col gap-4">
          {filtered.map((integration) => {
            const name = text(integration, 'name');
            return (
              <IntegrationCard
                key={name}
                locale={locale}
                name={name}
                displayName={text(integration, 'display_name')}
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
    </>
  );
}
