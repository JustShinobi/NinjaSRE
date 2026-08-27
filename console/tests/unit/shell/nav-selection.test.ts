import { describe, expect, it } from 'vitest';

import { isActive, navSelection } from '@/shell/nav-selection';

/**
 * What the frame says while it is waiting for the server.
 *
 * It used to say nothing. Every area is a dynamic Server Component reading
 * authenticated data, and prefetch is off on purpose, so a navigation really
 * does wait on the gateway — and for the whole of that wait the entry the
 * operator pressed stayed unlit while the one they were leaving stayed lit.
 * The only feedback a click produced was the absence of one.
 *
 * Which page you are going to is known the instant the link is pressed. The
 * server is not needed to confirm it.
 */
describe('navSelection', () => {
  it('lights the current area when nothing is in flight', () => {
    expect(navSelection('incidents', 'incidents', '')).toBe('selected');
    expect(navSelection('runs', 'incidents', '')).toBe('idle');
  });

  it('lights the destination the moment a navigation starts', () => {
    expect(navSelection('runs', 'incidents', 'runs')).toBe('arriving');
  });

  it('takes the light off the area being left', () => {
    // Two lit entries at once is the frame disagreeing with itself about where
    // the operator is.
    expect(navSelection('incidents', 'incidents', 'runs')).toBe('idle');
  });

  it('distinguishes arriving from selected rather than folding them together', () => {
    // They are different facts, and the entry draws them differently: one
    // carries the pending mark and the other does not. Folding them would make
    // a page that has arrived indistinguishable from one still loading.
    expect(navSelection('runs', 'runs', 'runs')).toBe('arriving');
    expect(navSelection('runs', 'runs', '')).toBe('selected');
  });

  it('counts both as the entry the frame is showing', () => {
    expect(isActive('selected')).toBe(true);
    expect(isActive('arriving')).toBe(true);
    expect(isActive('idle')).toBe(false);
  });

  it('lights nothing at all when the destination is not an area', () => {
    // A navigation to something outside the manifest — a run's own page, say —
    // leaves every entry quiet rather than guessing which group it belongs to.
    expect(navSelection('incidents', 'incidents', 'nowhere')).toBe('idle');
    expect(navSelection('runs', 'incidents', 'nowhere')).toBe('idle');
  });
});
