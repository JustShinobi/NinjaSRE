import { notFound } from 'next/navigation';

/** Declared per route: a layout's dynamism can stop applying to a child segment without warning. */
export const dynamic = 'force-dynamic';

/**
 * Everything that is not an area, routed into the shell so it can say so there.
 *
 * Without this, an unmatched address falls through to the router's own
 * not-found, which is rendered outside every layout — so the reader loses the
 * navigation at exactly the moment they need it, and a mistyped URL reads as a
 * console that has fallen over.
 *
 * This catch-all sits inside the shell's segment, so `not-found.tsx` beside it
 * renders with the sidebar, the utility bar and the palette all still there.
 */
export default function Unmatched(): never {
  notFound();
}
