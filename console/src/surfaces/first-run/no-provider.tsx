import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { message, type Locale } from '@/i18n/messages';
import type { DeploymentSetup } from './plan';

/**
 * The one thing a deployment with no provider has to be told, where it is.
 *
 * A line inside the page rather than a door in front of it. It is actionable —
 * it links to the step that fixes it — and it is exact: "no provider" is a
 * different sentence from "nothing has been verified", and the second is not a
 * reason to stop anybody.
 *
 * This file used to also hold a checklist panel and a quick-actions list for the
 * dashboard's right-hand column. Both were replaced by the hero and the named
 * destinations that now carry the same job in the centre of that page, and were
 * deleted rather than left behind: a component nothing renders is a component
 * nothing tests, and the next reader cannot tell which of the two versions is
 * the one that ships.
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
