import type { ReactNode } from 'react';

import { AlertTriangleIcon } from '@/design/icons';
import { message, type Locale } from '@/i18n/messages';
import type { Viewer } from '@/session/viewer';

/**
 * "You are not who you think you are", said on every page and not dismissable.
 *
 * An administrator acting as somebody else has, for as long as it lasts, a
 * different set of permissions and a different view of the same data. Every
 * mistake that follows from forgetting is expensive and every one of them is
 * attributed to the person being impersonated.
 *
 * So there is no close button. A banner that can be dismissed is a banner that
 * is dismissed once and then absent for the rest of the session, which is the
 * whole of the time it was needed. It names both parties, because "acting as"
 * with only one name is ambiguous in exactly the direction that matters.
 *
 * It renders above the shell rather than inside a page, so it cannot be
 * scrolled away or replaced by a page that forgot about it.
 */

export interface ImpersonationBannerProps {
  readonly viewer: Viewer;
  readonly locale: Locale;
}

export function ImpersonationBanner({
  viewer,
  locale,
}: ImpersonationBannerProps): ReactNode {
  if (!viewer.impersonating) {
    return null;
  }
  return (
    <p
      data-testid="impersonation"
      role="status"
      aria-label={message(locale, 'session.impersonation.label')}
      className="flex items-center justify-center gap-2 bg-warning-bg px-4 py-1 text-small text-warning edge border-x-0 border-t-0 border-warning"
    >
      <AlertTriangleIcon />
      {message(locale, 'session.impersonation.banner', {
        actor: viewer.impersonatedBy ?? message(locale, 'avatar.unknown'),
        subject: viewer.displayName,
      })}
    </p>
  );
}
