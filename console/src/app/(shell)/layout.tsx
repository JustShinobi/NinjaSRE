import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';

import { requestCredential, requestExpiry, requestLocale } from '@/shell/request';
import { signInHref } from '@/session/cookies';
import { deployment } from '@/shell/deployment';
import {
  countsFrom,
  loadAttention,
  loadGuardian,
  loadRecentRuns,
  loadSetup,
  loadViewer,
} from '@/shell/load';
import { Shell } from '@/shell/shell';

/**
 * The layout every area sits inside, and the one place the viewer is resolved.
 *
 * The middleware has already refused an unauthenticated request before routing
 * reached here; what this adds is the *resolution* — who the viewer is and what
 * they hold — done once per request rather than once per control. The redirect
 * below is therefore not a second guard but the answer to a narrower question:
 * a cookie that is present and no longer accepted by the API.
 *
 * The page arrives as `children`, rendered on the server independently of this.
 * A slow API delays the page and never the frame.
 */
export const dynamic = 'force-dynamic';

export default async function ShellLayout({
  children,
}: Readonly<{ children: ReactNode }>): Promise<ReactNode> {
  const credential = await requestCredential();
  const current = (await headers()).get('x-current-path') ?? '/';
  if (credential === null) {
    redirect(signInHref(current));
  }

  const locale = await requestLocale();
  const viewer = await loadViewer(credential).catch(() => null);
  if (viewer === null) {
    redirect(signInHref(current, 'expired'));
  }

  const [attention, recentRuns, guardian, setup, expiresAt] = await Promise.all([
    loadAttention(credential),
    loadRecentRuns(credential),
    loadGuardian(credential),
    loadSetup(credential),
    requestExpiry(),
  ]);

  return (
    <Shell
      viewer={viewer}
      locale={locale}
      deployment={deployment()}
      current={current}
      guardian={guardian}
      attention={attention}
      recentRuns={recentRuns}
      counts={countsFrom(attention)}
      setup={setup}
      expiresAt={expiresAt}
    >
      {children}
    </Shell>
  );
}
