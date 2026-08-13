import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { message, type Locale } from '@/i18n/messages';
import { panelLabels } from './labels';
import { Panel } from './panel';

/**
 * Three destinations, named the way the place they go is named.
 *
 * "Load what your team already knows" is a sentence with no subject: a reader
 * cannot tell whether it opens a form, a list or a chat window. Every screen
 * this console has already has a name and a one-line description in its own
 * header — `page.<area>.title` and `page.<area>.context` — so this reuses
 * exactly those rather than inventing a second, poetic description that would
 * drift from the first the day either one is edited alone.
 */

/** One destination the setup checklist is asking somebody to visit. */
interface QuickAction {
  readonly href: string;
  readonly titleKey:
    'page.knowledge.title' | 'page.autonomy.title' | 'page.memory.title';
  readonly contextKey:
    'page.knowledge.context' | 'page.autonomy.context' | 'page.memory.context';
}

const ACTIONS: readonly QuickAction[] = [
  {
    href: '/knowledge',
    titleKey: 'page.knowledge.title',
    contextKey: 'page.knowledge.context',
  },
  // Until the agent's own screen lands, what the agent may do is the autonomy
  // posture, and that is where this points rather than nowhere.
  {
    href: '/autonomy',
    titleKey: 'page.autonomy.title',
    contextKey: 'page.autonomy.context',
  },
  { href: '/memory', titleKey: 'page.memory.title', contextKey: 'page.memory.context' },
];

/** The destinations the checklist is asking for, each named and described. */
export function DashboardQuickActions({
  locale,
}: {
  readonly locale: Locale;
}): ReactNode {
  return (
    <Panel
      title={message(locale, 'dashboard.quickActions.title')}
      state="ready"
      labels={panelLabels(locale, message(locale, 'dashboard.quickActions.title'))}
      empty={{
        heading: message(locale, 'dashboard.quickActions.empty.heading'),
        body: message(locale, 'dashboard.quickActions.empty.body'),
        actionLabel: message(locale, 'dashboard.quickActions.empty.action'),
        href: '/',
      }}
    >
      <ul data-testid="quick-actions" className="flex flex-col gap-3 text-small">
        {ACTIONS.map((action) => (
          <li key={action.href}>
            <Link href={action.href} data-testid="quick-action">
              <span className="flex flex-col gap-1">
                <span className="text-strong">{message(locale, action.titleKey)}</span>
                <span className="text-meta text-muted no-underline">
                  {message(locale, action.contextKey)}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
