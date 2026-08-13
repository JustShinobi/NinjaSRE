import type { ReactNode } from 'react';

import { cx } from '@/design/cx';
import { formatNumber } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';
import { StatusDot } from '@/components/status';
import { CONTROL_SHAPE, STATE_SKIN, VARIANT_SKIN } from '@/components/action';
import { panelLabels } from './labels';
import { Panel } from './panel';
import type { PanelData } from './read';
import { dependencyOf, stateOf } from './read';
import {
  WIZARD_STEPS,
  currentStep,
  hrefFor,
  outstanding,
  planFor,
  type DeploymentSetup,
} from './first-run/plan';

/**
 * What a half-configured deployment sees before anything else.
 *
 * Three of seven steps outstanding used to leave the centre of this page
 * empty, with the only mention of setup a small card in the sidebar. This is
 * the opposite bet: while anything remains, finishing it *is* the page — one
 * block, the whole plan visible, the next step impossible to miss, and one
 * button. It disappears entirely the moment nothing is left, which is what
 * keeps it from being permanent furniture on a deployment that finished
 * setting up months ago.
 */

export interface SetupHeroProps {
  readonly locale: Locale;
  readonly setup: DeploymentSetup;
  /** The read this hero is drawn from, so a failure is reported rather than hidden. */
  readonly source: PanelData<unknown>;
}

/** The whole remaining plan, the next step highlighted, one way forward. */
export function SetupHero({ locale, setup, source }: SetupHeroProps): ReactNode {
  const left = outstanding(setup);
  if (source.status === 'ready' && left === 0) return null;

  const plan = planFor(setup);
  const here = currentStep(setup);

  return (
    <div className="mb-5" data-testid="setup-hero">
      <Panel
        title={message(locale, 'dashboard.hero.title')}
        state={stateOf(source, false)}
        dependency={dependencyOf(source)}
        labels={panelLabels(locale, message(locale, 'dashboard.hero.title'))}
        empty={{
          heading: message(locale, 'dashboard.hero.empty.heading'),
          body: message(locale, 'dashboard.hero.empty.body'),
          actionLabel: message(locale, 'dashboard.hero.empty.action'),
          href: '/first-run',
        }}
      >
        <div className="flex flex-col items-center gap-4 py-4 text-center">
          <p className="text-muted text-small">
            {message(locale, 'dashboard.hero.remaining', {
              count: formatNumber(locale, left),
              total: formatNumber(locale, WIZARD_STEPS.length),
            })}
          </p>
          <ol className="flex w-full max-w-md flex-col gap-1 text-left text-small">
            {plan.map((entry) => (
              <li
                key={entry.step}
                data-testid="setup-hero-step"
                data-step={entry.step}
                data-current={entry.current}
                className={cx(
                  'flex items-center gap-2 rounded-2 px-3 py-2',
                  entry.current ? 'bg-sunken edge border-border-strong' : '',
                )}
              >
                <StatusDot status={entry.done ? 'healthy' : 'unknown'} />
                <span className="min-w-0 flex-1 truncate">
                  {message(locale, `firstRun.step.${entry.step}`)}
                </span>
                {entry.current ? (
                  <span className="text-micro text-accent">
                    {message(locale, 'dashboard.hero.next')}
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
          <a
            href={hrefFor(here)}
            data-testid="setup-hero-cta"
            data-variant="primary"
            data-state="default"
            className={cx(CONTROL_SHAPE, VARIANT_SKIN.primary, STATE_SKIN.default)}
          >
            {message(locale, 'dashboard.hero.action')}
          </a>
        </div>
      </Panel>
    </div>
  );
}
