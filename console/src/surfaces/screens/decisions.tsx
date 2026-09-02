import type { ReactNode } from 'react';
import NextLink from 'next/link';

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

/**
 * The tab bar, in the artboard's own chips rather than the shared
 * underline-tab pattern (`TabLinks`, `@/components`).
 *
 * A local composition rather than a shared-component reskin: `TabLinks` is
 * used across many screens this feature does not own, and the artboard's
 * pill treatment is a per-screen visual choice, not (here) a change to what
 * a tab *is*. Kept to the same contract `TabLinks` already gave this screen
 * — `tab-links`/`tab-link` test ids, `data-tab`, `aria-current="page"` on
 * the selected one, an address-driven `href` — so nothing downstream of the
 * tab bar's own markup had to change. Each chip is the router's link with
 * prefetching off, for the reason `TabLinks` gives: a plain anchor is a
 * document navigation that tears the shell down and repeats its reads for a
 * change of tab.
 *
 * No live count on the "Ações" chip the artboard draws one on: that number
 * is the same one the sidebar badge already carries, and getting it here
 * would mean fetching approvals regardless of which tab is open — the exact
 * "a reader looking at Changes should not wait on an Actions fetch nobody
 * asked for" cost this screen's own read already avoids for the reverse
 * case. Left for the badge to carry alone; named in the feature's own report
 * rather than fetched around silently.
 */
function DecisionsTabBar({
  locale,
  tab,
}: {
  readonly locale: Parameters<typeof message>[0];
  readonly tab: DecisionsTab;
}): ReactNode {
  return (
    <nav aria-label={message(locale, 'decisions.tabs')} data-testid="tab-links">
      <ul className="flex gap-2">
        {DECISIONS_TABS.map((each) => {
          const selected = each === tab;
          return (
            <li key={each}>
              <NextLink
                href={`?tab=${each}`}
                prefetch={false}
                data-testid="tab-link"
                data-tab={each}
                aria-current={selected ? 'page' : undefined}
                className={cx(
                  CHIP_SHAPE,
                  'px-3 py-2',
                  selected
                    ? 'font-semibold edge border-success bg-success-bg text-success'
                    : 'text-muted',
                )}
              >
                {message(locale, `decisions.tab.${each}`)}
              </NextLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
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

      <DecisionsTabBar locale={locale} tab={tab} />

      <div className="mt-4">{content}</div>
    </>
  );
}
