import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { StatusDot } from '@/components/status';
import { formatNumber } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import type { PanelData } from '../read';
import { dependencyOf, stateOf } from '../read';
import {
  WIZARD_STEPS,
  currentStep,
  hrefFor,
  outstanding,
  planFor,
  type DeploymentSetup,
} from './plan';

/**
 * The setup state, where somebody is already working.
 *
 * This panel — not a redirect — is what stops a deployment being abandoned half
 * configured. The state is visible on the screen an operator opens anyway, the
 * outstanding step is one click, and the whole thing disappears the moment
 * there is nothing left. A door in front of the product achieves the same
 * completion rate only among people who were never going to leave.
 *
 * Absent rather than empty when the setup is finished. A panel that said
 * "nothing left to set up" would be permanent furniture on every dashboard in
 * every deployment, for a sentence that is true forever after the first day.
 */

export interface ChecklistPanelProps {
  readonly locale: Locale;
  readonly setup: DeploymentSetup;
  /** The read this panel is drawn from, so a failure is reported rather than hidden. */
  readonly source: PanelData<unknown>;
}

/** What is left to set up, with the outstanding step as a link. */
export function ChecklistPanel({
  locale,
  setup,
  source,
}: ChecklistPanelProps): ReactNode {
  const left = outstanding(setup);
  if (source.status === 'ready' && left === 0) return null;

  const plan = planFor(setup);
  const here = currentStep(setup);

  return (
    <Panel
      title={message(locale, 'setup.checklist.title')}
      state={stateOf(source, false)}
      dependency={dependencyOf(source)}
      labels={panelLabels(locale, message(locale, 'setup.checklist.title'))}
      empty={{
        heading: message(locale, 'setup.checklist.empty.heading'),
        body: message(locale, 'setup.checklist.empty.body'),
        actionLabel: message(locale, 'setup.checklist.empty.action'),
        href: '/first-run',
      }}
    >
      <div data-testid="setup-checklist" className="flex flex-col gap-3">
        <p className="text-meta text-muted">
          {message(locale, 'setup.checklist.remaining', {
            count: formatNumber(locale, left),
            total: formatNumber(locale, WIZARD_STEPS.length),
          })}
        </p>
        <ol className="flex flex-col gap-1 text-small">
          {plan.map((entry) => (
            <li
              key={entry.step}
              data-testid="checklist-step"
              data-step={entry.step}
              data-done={entry.done}
              className="flex items-center gap-2"
            >
              <StatusDot status={entry.done ? 'healthy' : 'unknown'} />
              <span className="min-w-0 truncate">
                {message(locale, `firstRun.step.${entry.step}`)}
              </span>
            </li>
          ))}
        </ol>
        <Link href={hrefFor(here)} data-testid="checklist-next">
          {message(locale, 'setup.checklist.open')}
        </Link>
      </div>
    </Panel>
  );
}

/**
 * The one thing a deployment with no provider has to be told, where it is.
 *
 * A line inside the page rather than a door in front of it. It is actionable —
 * it links to the step that fixes it — and it is exact: "no provider" is a
 * different sentence from "nothing has been verified", and the second is not a
 * reason to stop anybody.
 */
export function NoProviderNotice({
  locale,
  setup,
}: {
  readonly locale: Locale;
  readonly setup: DeploymentSetup;
}): ReactNode {
  if (setup.provider !== 'absent') return null;
  return (
    <div
      role="status"
      data-testid="no-provider"
      className="mb-5 flex flex-col gap-1 rounded-3 edge border-warning bg-warning-bg p-4"
    >
      <p className="text-strong text-warning">
        {message(locale, 'setup.noProvider.heading')}
      </p>
      <p className="text-small text-muted">
        {message(locale, 'setup.noProvider.body')}
      </p>
      <Link href="/first-run?step=provider" data-testid="no-provider-action">
        {message(locale, 'setup.noProvider.action')}
      </Link>
    </div>
  );
}

/** The three destinations the checklist is asking for, one click from here. */
export function QuickActions({ locale }: { readonly locale: Locale }): ReactNode {
  const actions: readonly (readonly [string, string])[] = [
    ['/knowledge', 'setup.actions.knowledge'],
    // Until the agent's own screen lands, what the agent may do is the autonomy
    // posture, and that is where this points rather than nowhere.
    ['/autonomy', 'setup.actions.agent'],
    ['/memory', 'setup.actions.memory'],
  ];
  return (
    <Panel
      title={message(locale, 'setup.actions.title')}
      state="ready"
      labels={panelLabels(locale, message(locale, 'setup.actions.title'))}
      empty={{
        heading: message(locale, 'setup.actions.empty.heading'),
        body: message(locale, 'setup.actions.empty.body'),
        actionLabel: message(locale, 'setup.actions.empty.action'),
        href: '/',
      }}
    >
      <ul data-testid="quick-actions" className="flex flex-col gap-2 text-small">
        {actions.map(([href, key]) => (
          <li key={href}>
            <Link href={href} data-testid="quick-action">
              {message(locale, key as 'setup.actions.knowledge')}
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
