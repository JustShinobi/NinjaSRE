import type { MessageKey } from '@/i18n/en';

/**
 * What to head the first-run checklist with, given how much of it is done.
 *
 * The panel was headed "What is left" unconditionally, over a line reading
 * "7 of 7 done" — two claims about the same list, disagreeing, on the one
 * screen somebody meets when nothing works yet.
 *
 * A plan with no steps in it keeps the question rather than the congratulation:
 * a deployment that declared nothing has not finished anything.
 */
export function checklistTitle(done: number, total: number): MessageKey {
  if (total <= 0) return 'firstRun.steps.title';
  return done >= total ? 'firstRun.steps.done' : 'firstRun.steps.title';
}
