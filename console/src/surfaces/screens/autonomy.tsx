import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  pairs,
  panelRead,
  read,
  stateOf,
} from '../read';
import { readViewState, type FilterName } from '../url-state';

/**
 * What this deployment may do on its own, and why.
 *
 * The rules that would fill this screen come from the policy engine, which is
 * separate work; what is here today is the part that is already true and is the
 * part that matters most — **the footer**. Absence of a rule resolves to
 * propose-only, and saying so permanently is not decoration: an operator reading
 * an empty rules table has to know whether empty means "anything goes" or
 * "nothing happens without me", and guessing the permissive answer is the one
 * direction this must never be wrong in.
 *
 * The configured bounds beside it are read from the effective configuration,
 * which does serve them.
 */

export const AUTONOMY_FILTERS: readonly FilterName[] = ['node'];

/** The settings that bound what may happen unattended, whatever a rule says. */
const BOUND_SETTINGS = ['approval.required_above', 'investigation.max_loops'];

export async function AutonomyScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, search } = context;
  const state = readViewState(search, AUTONOMY_FILTERS);
  const nodeId = state.filters.node ?? viewer.teamNodeId;

  const effective = await panelRead('/v1/config/{node_id}', () =>
    read('/v1/config/{node_id}', {
      ...authorised(credential),
      params: { node_id: nodeId },
    }),
  );

  const values = pairs(dataOf(effective), 'values');
  const provenance = new Map(pairs(dataOf(effective), 'provenance'));
  const bounds = values.filter(([name]) => BOUND_SETTINGS.includes(name));

  return (
    <>
      <AreaHeader
        area={areaFor('autonomy')}
        locale={locale}
        nested={[{ label: nodeId }]}
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 min-w-0">
          <Panel
            title={message(locale, 'autonomy.rules.title')}
            // Nothing serves rules yet. The empty state says what the absence of
            // a rule *means*, which is the fact an operator actually needs.
            state={stateOf(effective, true)}
            dependency={dependencyOf(effective)}
            labels={panelLabels(locale, message(locale, 'autonomy.rules.title'))}
            empty={{
              heading: message(locale, 'autonomy.empty.heading'),
              body: message(locale, 'autonomy.empty.body'),
              actionLabel: message(locale, 'autonomy.empty.action'),
              href: '/configuration',
            }}
          />
          <p data-testid="autonomy-footer" className="text-meta text-muted mt-3">
            {message(locale, 'autonomy.footer')}
          </p>
        </div>

        <div className="min-w-0 flex flex-col gap-5">
          <Panel
            title={message(locale, 'autonomy.bounds.title')}
            state={stateOf(effective, bounds.length === 0)}
            dependency={dependencyOf(effective)}
            labels={panelLabels(locale, message(locale, 'autonomy.bounds.title'))}
            empty={{
              heading: message(locale, 'autonomy.empty.heading'),
              body: message(locale, 'autonomy.empty.body'),
              actionLabel: message(locale, 'autonomy.empty.action'),
              href: '/configuration',
            }}
          >
            <dl className="flex flex-col gap-2 text-small">
              {bounds.map(([name, value]) => (
                <div key={name} className="flex items-center gap-3" data-testid="bound">
                  <dt className="font-mono min-w-0 truncate">{name}</dt>
                  <dd className="ml-auto flex items-center gap-2">
                    <span className="tabular-nums">{value}</span>
                    <Badge status={provenance.get(name) ?? 'unknown'} />
                  </dd>
                </div>
              ))}
            </dl>
          </Panel>
        </div>
      </div>
    </>
  );
}
