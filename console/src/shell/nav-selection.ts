/**
 * Which navigation entry looks active, and when.
 *
 * Every area in this console is a dynamic Server Component that reads live,
 * authenticated data on render, and prefetch is off for the reason the sidebar
 * gives — so a navigation genuinely waits on the gateway. The question is what
 * the frame does meanwhile, and it used to do nothing at all: the entry the
 * operator pressed stayed unlit for the whole round trip while the one they
 * were leaving stayed lit, so the only feedback a click produced was that
 * nothing had happened yet.
 *
 * That is the archaic part. Not the absence of an animation — the absence of
 * an answer. Which page you are going to is a thing the browser knows the
 * instant you press the link, and the server is not needed to confirm it.
 *
 * So while a navigation is in flight the destination is the entry that looks
 * active, and the one being left goes quiet. `arriving` is distinguished from
 * `selected` rather than folded into it, because the two are different facts
 * and the entry says so: one carries the pending mark, the other does not.
 */

/** How a navigation entry is drawn right now. */
export type NavState = 'selected' | 'arriving' | 'idle';

/**
 * The state `area` is in.
 *
 * `pending` is the area a navigation is currently heading to, or the empty
 * string when none is. It wins over `current` deliberately: during the trip,
 * where the operator is going is more useful than where they have been, and
 * two lit entries at once would be the frame disagreeing with itself.
 */
export function navSelection(area: string, current: string, pending: string): NavState {
  if (pending !== '') {
    return area === pending ? 'arriving' : 'idle';
  }
  return area === current ? 'selected' : 'idle';
}

/** Whether an entry in `state` is drawn as the one the frame is showing. */
export function isActive(state: NavState): boolean {
  return state !== 'idle';
}
