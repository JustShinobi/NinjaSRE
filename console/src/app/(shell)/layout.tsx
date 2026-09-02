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
  loadStopped,
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
 *
 * What is read here is read on every full-page render of every screen, so
 * only what the frame itself draws belongs in the list: the viewer, what is
 * waiting on them, the recent runs the palette offers, the guardian line,
 * the setup state and the kill switch. The investigate drawer's briefing is
 * not among them — three reads to fill a drawer most page views never open
 * are fetched by the drawer, from `/api/launcher`, when it opens.
 */
export const dynamic = 'force-dynamic';

export default async function ShellLayout({
  children,
}: Readonly<{ children: ReactNode }>): Promise<ReactNode> {
  const credential = await requestCredential();
  // Only the two redirects below use this, and both run on a real request
  // before anything renders — which is the one moment the header *is* the
  // path. The frame reads its own, from the router, because a layout is not
  // re-rendered by a segment navigation and this value would go stale the
  // first time somebody used the navigation.
  const current = (await headers()).get('x-current-path') ?? '/';
  if (credential === null) {
    redirect(signInHref(current));
  }

  const locale = await requestLocale();
  const viewer = await loadViewer(credential).catch(() => null);
  if (viewer === null) {
    redirect(signInHref(current, 'expired'));
  }

  const [attention, recentRuns, guardian, setup, stopped, expiresAt] =
    await Promise.all([
      loadAttention(credential),
      loadRecentRuns(credential),
      loadGuardian(credential),
      loadSetup(credential),
      loadStopped(credential),
      requestExpiry(),
    ]);

  return (
    <Shell
      viewer={viewer}
      locale={locale}
      deployment={deployment()}
      guardian={guardian}
      attention={attention}
      recentRuns={recentRuns}
      counts={countsFrom(attention)}
      setup={setup}
      stopped={stopped}
      expiresAt={expiresAt}
    >
      {children}
    </Shell>
  );
}
