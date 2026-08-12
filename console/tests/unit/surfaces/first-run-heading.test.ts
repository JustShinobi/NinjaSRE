import { describe, expect, it } from 'vitest';

import { checklistTitle } from '@/surfaces/screens/first-run-heading';

/**
 * The first-run panel is headed "What is left" and its first line reads
 * "7 of 7 done". Both are drawn from the same list, and on the one screen a
 * stranger meets on the day nothing works yet they contradict each other.
 *
 * A heading is a claim about the state below it. When nothing is left, the
 * honest claim is that nothing is left — not a standing label that happens to
 * be true most of the time.
 */

describe('the checklist heading is a claim about what is under it', () => {
  it('asks what is left while something is', () => {
    expect(checklistTitle(3, 7)).toBe('firstRun.steps.title');
  });

  it('stops saying anything is left once nothing is', () => {
    expect(checklistTitle(7, 7)).toBe('firstRun.steps.done');
  });

  it('treats a deployment that declared no steps as having none left, not all done', () => {
    // An empty plan is a deployment that said nothing about setup. Reporting it
    // as finished would claim somebody had done seven things nobody listed.
    expect(checklistTitle(0, 0)).toBe('firstRun.steps.title');
  });

  it('does not congratulate a deployment that has overshot its own list', () => {
    // More done than declared means the plan and the progress disagree; the
    // screen should not resolve that disagreement in the flattering direction.
    expect(checklistTitle(8, 7)).toBe('firstRun.steps.done');
  });
});
