import type { ReactNode } from 'react';

import { CHIP_SHAPE } from '@/components/status';
import { cx } from '@/design/cx';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { readViewState, type FilterName } from '../url-state';
import { ApprovalsTab } from './approvals';
import { ProposalsTab } from './proposals';

/**
 * Everything waiting on a human: what the agent wants to do now, and what it
 * wants the deployment to become.
 *
 * Two tabs rather than two menu entries. The question each answers is real and
 * stays real — "may the agent do this now" is not "should the deployment be
 * different from tomorrow on" — but a queue that only exists behind somebody
 * else's screen is a queue that grows until it is discovered, and a tab bar on
 * one screen says "the other queue exists" more directly than a paragraph of
 * prose above a list ever did. Reading either tab already shows the other is
 * there.
 *
 * The badge in the sidebar is the sum of both: a decision waiting is a decision
 * waiting, whichever tab it would open to (`countsFrom` in `shell/load.ts`).
 */

export const DECISIONS_TABS = ['actions', 'changes'] as const;

export type DecisionsTab = (typeof DECISIONS_TABS)[number];

export const DECISIONS_FILTERS: readonly FilterName[] = ['tab'];

/** The tab the address names, and the first one when it names nothing known. */
export function tabFrom(value: string): DecisionsTab {
  return DECISIONS_TABS.find((tab) => tab === value) ?? DECISIONS_TABS[0];
}

export async function DecisionsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { locale, search } = context;
  const state = readViewState(search, DECISIONS_FILTERS);
  const tab = tabFrom(state.filters.tab ?? '');

  // Only the selected tab reads anything: the two donor screens each make
  // their own requests, and a reader looking at Actions should not wait on a
  // Changes-proposed fetch nobody asked for, the same "fetch what the active
  // tab needs" rule `agent.tsx` already follows for its own three tabs.
  const content =
    tab === 'actions' ? await ApprovalsTab(context) : await ProposalsTab(context);

  return (
    <>
      <AreaHeader area={areaFor('decisions')} locale={locale} />

      <TabLinks
        label={message(locale, 'decisions.tabs')}
        selected={tab}
        tabs={DECISIONS_TABS.map((each) => ({
          id: each,
          label: message(locale, `decisions.tab.${each}`),
          href: `?tab=${each}`,
        }))}
      />

      <div className="mt-4">{content}</div>
    </>
  );
}
