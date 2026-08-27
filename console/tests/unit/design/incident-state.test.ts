import { describe, expect, it } from 'vitest';

import {
  AGENT_INCIDENT_STATES,
  ATTENTION_STATUSES,
  HUMAN_INCIDENT_STATES,
  isTerminalIncident,
  LIVE_INCIDENT_STATES,
  statusPresentation,
} from '@/design/status';

/**
 * Which incident states mean "finished", and why the console may not decide it
 * by comparing against a word.
 *
 * The overview asked `state === 'closed'`. The store's enumeration has seven
 * members and `closed` is not one of them, so the comparison never once
 * matched: every incident the agent had already finished was counted as one
 * waiting on a person, and in the activity feed the same test made the success
 * branch unreachable — a self-resolved incident was painted the same red as a
 * live outage.
 *
 * `tests/contract/console/test_console_incident_state_vocabulary.py` holds the
 * vocabulary itself against the enumeration, which is a thing only Python can
 * do here. This suite holds the *behaviour*: which of those words end an
 * incident, and that none of them lands on the unknown-status path.
 */

/** The three states the store's own `is_closed` property returns true for. */
const TERMINAL = ['resolved', 'suppressed', 'closed_without_action'] as const;

/** The four that mean the incident is still somebody's problem. */
const LIVE = ['open', 'investigating', 'awaiting_human', 'remediating'] as const;

describe('isTerminalIncident', () => {
  it.each(TERMINAL)('%s has finished', (state) => {
    expect(isTerminalIncident(state)).toBe(true);
  });

  it.each(LIVE)('%s has not finished', (state) => {
    expect(isTerminalIncident(state)).toBe(false);
  });

  it('does not answer true for a word the store cannot write', () => {
    // The specific regression: `closed` reads like an ending and is not one.
    // Answering true here would trade a filter that never fires for a filter
    // that fires on nothing real, which is the same defect wearing a fix.
    expect(isTerminalIncident('closed')).toBe(false);
    expect(isTerminalIncident('')).toBe(false);
    expect(isTerminalIncident('finished')).toBe(false);
  });
});

describe('the vocabulary', () => {
  it.each([...TERMINAL, ...LIVE])('draws %s deliberately', (state) => {
    const presented = statusPresentation(state);
    expect(presented.known).toBe(true);
    expect(ATTENTION_STATUSES as readonly string[]).toContain(state);
  });

  it('tells the agent reading apart from the agent writing', () => {
    // `investigating` and `remediating` are the two states an operator most
    // needs to separate — one is the agent looking, the other is the estate
    // being changed — so they may not share a shape.
    expect(statusPresentation('remediating').shape).not.toBe(
      statusPresentation('investigating').shape,
    );
  });

  it('does not draw an incident closed without a fix as a success', () => {
    // An incident a person shut with nothing done is not one that was solved.
    expect(statusPresentation('closed_without_action').role).not.toBe('success');
    expect(statusPresentation('resolved').role).toBe('success');
  });
});

/**
 * Which live states are a person's problem, and which are the agent's.
 *
 * This is the distinction the overview never drew. Every incident that was not
 * terminal went into "N items need you", including the ones the agent had
 * picked up and was actively working — so a product whose whole claim is that
 * it investigates without you was using its first screen to announce how much
 * it had left undone.
 */
describe('who a live incident is waiting on', () => {
  it('is a person when nothing has picked it up, or when it asked one', () => {
    expect([...HUMAN_INCIDENT_STATES].sort()).toEqual(['awaiting_human', 'open']);
  });

  it('is the agent while it is reading or writing', () => {
    expect([...AGENT_INCIDENT_STATES].sort()).toEqual(['investigating', 'remediating']);
  });

  it('accounts for every live state exactly once', () => {
    // A partition, not two lists that happen to look right. A state in neither
    // is an incident nothing on the overview counts; a state in both is one
    // counted twice, in two places that then disagree.
    const both = [...HUMAN_INCIDENT_STATES, ...AGENT_INCIDENT_STATES].sort();
    expect(both).toEqual([...LIVE_INCIDENT_STATES].sort());
    expect(new Set(both).size).toBe(both.length);
  });
});
