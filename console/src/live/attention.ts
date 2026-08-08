import type { AttentionItem } from '@/shell/attention';
import type { LiveState } from './reducer';

/**
 * What is waiting on a person, derived from the same events the screens read.
 *
 * The notification centre's count and the notification centre's list are the
 * classic pair that drift: two sources, two update paths, and a badge that says
 * two above a list of one. They cannot drift here, because the count *is* the
 * length of this list and this list is derived from the run's own events. There
 * is no second read to get out of step.
 *
 * The labels are passed in rather than looked up. This module is reachable from
 * the server as well as the browser, and a sentence resolved against the wrong
 * viewer's locale is a sentence in a language they did not ask for.
 */

/** What an attention item is called, in the viewer's language. */
export interface AttentionLabels {
  readonly approval: string;
  readonly question: string;
  /** What follows "decided by": the surface, when the deployment named one. */
  readonly elsewhere: string;
}

/** The items `state` is waiting on, in the order they started waiting. */
export function attentionFrom(
  state: LiveState,
  labels: AttentionLabels,
): readonly AttentionItem[] {
  return state.waiting
    .filter((item) => item.open)
    .map((item) => ({
      id: item.id,
      kind: item.kind === 'approval' ? 'approval' : 'question',
      title: item.kind === 'approval' ? labels.approval : labels.question,
      detail: item.question,
      href: `/runs/${state.runId}`,
      since: item.since,
    }));
}

/**
 * How a decision made somewhere else reads.
 *
 * Never blank. A card that closed with nothing on it is a card the person
 * looking at it assumes they closed, and the next thing they do is look for
 * what they just approved.
 */
export function decidedElsewhere(
  decidedBy: string,
  surface: string,
  labels: AttentionLabels,
): string {
  if (decidedBy === '' && surface === '') return labels.elsewhere;
  if (surface === '') return decidedBy;
  if (decidedBy === '') return surface;
  return `${decidedBy} · ${surface}`;
}
