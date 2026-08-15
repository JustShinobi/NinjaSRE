import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { message, type Locale } from '@/i18n/messages';
import { currentStep, hrefFor, outstanding, type DeploymentSetup } from './plan';

/**
 * "Continue setup", on a screen a wizard step handed over to.
 *
 * Two steps of the wizard are not pages of their own: they are satisfied by
 * screens that already exist for other reasons (Resources, Alert intake), and
 * a wizard that sent somebody there with no way back was a wizard whose trail
 * ended at the first step it did not own. This is the way back — carried by
 * the address rather than remembered, the same rule every other piece of this
 * wizard's state already follows.
 */

/** The query parameter a handed-over screen carries, naming who sent it. */
export const SETUP_RETURN_PARAM = 'return';

/** The one value that parameter takes: the wizard sent this visitor here. */
export const SETUP_RETURN_VALUE = 'setup';

/** `path`, with the parameter that asks its screen to offer the way back. */
export function withSetupReturn(path: string): string {
  return `${path}?${SETUP_RETURN_PARAM}=${SETUP_RETURN_VALUE}`;
}

/** Whether `value` — an address's own `return` parameter — asked to come back. */
export function requestedSetupReturn(value: string | null): boolean {
  return value === SETUP_RETURN_VALUE;
}

export interface SetupReturnBannerProps {
  readonly locale: Locale;
  readonly setup: DeploymentSetup;
  /** Whether the address that reached this screen carried the return parameter. */
  readonly requested: boolean;
}

/**
 * The banner that offers the way back, and only while there is a way back to
 * offer.
 *
 * Absent once the checklist is complete — not disabled, gone — because a
 * control that promised to resume a wizard with nothing left to resume is a
 * control that lies. The step it returns to is derived the same way the
 * wizard derives its own current step: from what the deployment says about
 * itself, never from what the browser remembers.
 */
export function SetupReturnBanner({
  locale,
  setup,
  requested,
}: SetupReturnBannerProps): ReactNode {
  if (!requested || outstanding(setup) === 0) return null;
  return (
    <div
      data-testid="setup-return-banner"
      className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-3 edge border-border-strong bg-sunken p-3"
    >
      <p className="text-small text-muted">{message(locale, 'firstRun.return.body')}</p>
      <Link href={hrefFor(currentStep(setup))} data-testid="setup-return-link">
        {message(locale, 'firstRun.return.cta')}
      </Link>
    </div>
  );
}
