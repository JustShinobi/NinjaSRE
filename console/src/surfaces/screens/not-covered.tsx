import type { ReactNode } from 'react';
import NextLink from 'next/link';

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
  list,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';

/**
 * "Not covered, and why" — its own page, linked from the catalogue rather
 * than written out at the bottom of it.
 *
 * The data is the catalogue's own `known_gaps`, served alongside
 * `GET /v1/integrations` as it always has been; only where it renders moves.
 * Structured, per vendor: `cause` separates "the architecture cannot reach
 * this" from "this was weighed and decided against", because collapsing the
 * two turns a decision somebody can reopen into a limitation nobody can.
 */
export async function NotCoveredScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale } = context;
  const init = authorised(credential);

  const integrations = await panelRead<unknown>('/v1/integrations', () =>
    read('/v1/integrations', init),
  );
  const gaps = list(dataOf(integrations), 'known_gaps');

  return (
    <>
      <AreaHeader area={areaFor('integrations-not-covered')} locale={locale} />

      <Panel
        title={message(locale, 'catalogue.notCovered.title')}
        state={stateOf(integrations, gaps.length === 0)}
        dependency={dependencyOf(integrations)}
        labels={panelLabels(locale, message(locale, 'catalogue.notCovered.title'))}
        bare
        empty={{
          heading: message(locale, 'catalogue.notCovered.title'),
          body: message(locale, 'catalogue.notCovered.intro'),
          actionLabel: message(locale, 'catalogue.notCovered.back'),
          href: '/integrations',
        }}
      >
        <div className="flex flex-col gap-4">
          <p className="text-small text-muted max-w-prose">
            {message(locale, 'catalogue.notCovered.intro')}
          </p>

          <ul className="flex flex-col gap-3" data-testid="not-covered-list">
            {gaps.map((gap) => (
              <li
                key={text(gap, 'integration')}
                data-testid="known-gap"
                data-integration={text(gap, 'integration')}
                data-cause={text(gap, 'cause')}
                className="flex flex-col gap-1 rounded-3 edge border-border p-3 text-muted"
              >
                <span className="text-small text-strong">
                  {text(gap, 'display_name')}{' '}
                  <span className="text-meta text-muted font-normal">
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

          <NextLink
            href="/integrations"
            data-testid="back-to-integrations"
            className="text-accent underline underline-offset-2 motion-hover hover:opacity-80"
          >
            {message(locale, 'catalogue.notCovered.back')}
          </NextLink>
        </div>
      </Panel>
    </>
  );
}
