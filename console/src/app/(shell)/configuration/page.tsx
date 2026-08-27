'use client';

import { useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';

import { configurationRedirectTarget } from '@/shell/configuration-redirect';

/** Declared per route: a layout's dynamism can stop applying to a child segment without warning. */
export const dynamic = 'force-dynamic';

/**
 * The retired configuration editor's address, forwarding to whichever page now
 * owns the group a visitor was heading for.
 *
 * A client component, unlike every other retired route in this shell, and for
 * one reason: the group was carried in the URL's *fragment*, and a fragment is
 * never sent to a server. `/administration` and `/signals` could redirect in
 * `page.tsx` because `?tab=` arrives with the request; `#config-section-...`
 * does not, so the only place that can read it is the browser that already
 * holds it.
 *
 * `replace` rather than `push`, so the retired address does not sit in the
 * history for Back to land on and forward again.
 */
export default function Page(): ReactNode {
  const router = useRouter();

  useEffect(() => {
    router.replace(configurationRedirectTarget(window.location.hash));
  }, [router]);

  return null;
}
