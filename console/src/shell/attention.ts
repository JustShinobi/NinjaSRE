/**
 * What is waiting on a person, wherever it came from.
 *
 * The notification centre is not a list of approvals, or a list of questions, or
 * a list of failed runs. It is one list of *things needing a person*, because
 * that is the question an operator opening the console is actually asking, and
 * three separate counts in three places is three places to look before you know
 * the answer is none.
 *
 * The rule that makes it worth having: an item resolved anywhere else disappears
 * from here without a refresh. A notification centre that still shows an
 * approval somebody granted five minutes ago is one people learn to distrust,
 * and a distrusted alarm is worse than no alarm.
 */

import type { SemanticRole } from '@/design/tokens';

/** Where an attention item came from, which is also where following it goes. */
export const ATTENTION_KINDS = [
  'approval',
  'proposal',
  'question',
  'incident',
  'failure',
] as const;

export type AttentionKind = (typeof ATTENTION_KINDS)[number];

/** One thing waiting on a person. */
export interface AttentionItem {
  /** Stable across a refresh: it is the identifier of the thing itself. */
  readonly id: string;
  readonly kind: AttentionKind;
  readonly title: string;
  readonly detail: string;
  readonly href: string;
  /** When it started waiting, so the oldest can be named. */
  readonly since: string;
}

/** The role each kind is rendered in. Colour is never the only signal. */
export const ATTENTION_ROLE: Readonly<Record<AttentionKind, SemanticRole>> = {
  approval: 'warning',
  // Info rather than warning: a proposal is an improvement waiting, not a
  // production change waiting. Colouring it the same as a remediation approval
  // would teach people that the amber row is sometimes not urgent, which is how
  // the urgent one stops being read.
  proposal: 'info',
  question: 'info',
  incident: 'danger',
  failure: 'danger',
};

/**
 * The attention list, and what it is like to resolve one.
 *
 * Immutable: resolving returns a new list rather than mutating this one, so a
 * component holding the old value re-renders instead of silently disagreeing
 * with itself about the count.
 */
export function withoutItem(
  items: readonly AttentionItem[],
  id: string,
): readonly AttentionItem[] {
  return items.filter((item) => item.id !== id);
}

/**
 * How a surface says an item is no longer waiting.
 *
 * A browser event rather than a callback threaded through every screen: the
 * thing that resolves an approval is a page three components deep, and the
 * notification centre is in the shell. Passing a handler down to reach it would
 * mean every intervening component knowing about a list it does not render.
 *
 * The shell listens; anything may publish. That is the "resolved anywhere else"
 * half of the requirement, and it costs one line at the point of resolution.
 */
export const ATTENTION_RESOLVED_EVENT = 'ninjasre:attention-resolved';

/** Say that `id` no longer needs a person. Safe to call on the server, where it does nothing. */
export function publishResolved(id: string): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(ATTENTION_RESOLVED_EVENT, { detail: id }));
}

/** Hear about anything resolved anywhere. Returns the way to stop hearing about it. */
export function onResolved(listener: (id: string) => void): () => void {
  const handler = (event: Event): void => {
    const detail: unknown = (event as CustomEvent<unknown>).detail;
    if (typeof detail === 'string') listener(detail);
  };
  window.addEventListener(ATTENTION_RESOLVED_EVENT, handler);
  return () => {
    window.removeEventListener(ATTENTION_RESOLVED_EVENT, handler);
  };
}

/** How many are still waiting. */
export function unreadCount(items: readonly AttentionItem[]): number {
  return items.length;
}

/** The one that has been waiting longest, which is the one a header names. */
export function oldest(items: readonly AttentionItem[]): AttentionItem | undefined {
  let found: AttentionItem | undefined;
  let earliest = Number.POSITIVE_INFINITY;
  for (const item of items) {
    const at = new Date(item.since).getTime();
    if (Number.isNaN(at)) continue;
    if (at < earliest) {
      earliest = at;
      found = item;
    }
  }
  return found;
}
