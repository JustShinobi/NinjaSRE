import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AutoRefresh } from '@/live/auto-refresh';
import { CHIP_SHAPE } from '@/components/status';
import { FRESHNESS_STATES } from '@/live/freshness';

/**
 * The one chip that is on every screen, held to the shape every other chip has.
 *
 * The freshness indicator sits in the utility bar, so it is beside a run's
 * status chip, a credential's chip and a side effect's chip on nearly every
 * page in the console. It was written with its own geometry — a control height
 * and horizontal padding, where a chip has padding on all four sides — and so
 * rendered eight pixels shorter in the box and with its label pressed against
 * the top and bottom edges. Individually trivial; sitting in a row with three
 * chips that were drawn correctly, it is the one that looks wrong, and it is
 * the one a reader sees most often.
 *
 * The assertion is against the shared constant rather than against a list of
 * classes written out here, because a list written out here is a third copy of
 * the geometry and would drift from both.
 */

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: () => undefined }),
}));

describe('the frame’s freshness chip', () => {
  it('is drawn with the same geometry as every other chip', () => {
    render(<AutoRefresh locale="en" />);

    const chip = screen.getByTestId('freshness');
    for (const utility of CHIP_SHAPE.split(' ')) {
      expect([...chip.classList], utility).toContain(utility);
    }
  });

  it('does not set its own height, which is what removed the padding', () => {
    render(<AutoRefresh locale="en" />);

    const classes = [...screen.getByTestId('freshness').classList];
    expect(classes).not.toContain('h-control');
  });

  it('draws its mark on the icon scale, like every other status shape', () => {
    render(<AutoRefresh locale="en" />);

    // `icon-inline` is the thirteen pixels every `ShapeMark` in the library
    // uses. This mark was eight — a spacing step borrowed for a glyph, which
    // is the exact swap `status.tsx` documents as the thing not to do, because
    // a glyph sized off the spacing scale drifts away from the letters beside
    // it the moment either scale moves.
    const mark = screen.getByTestId('freshness').querySelector('[aria-hidden]');
    expect(mark).not.toBeNull();
    const classes = [...(mark?.classList ?? [])];
    expect(classes).toContain('icon-inline');
    expect(classes).not.toContain('size-2');
  });

  it('declares a state the indicator is allowed to be in', () => {
    render(<AutoRefresh locale="en" />);

    const state = screen.getByTestId('freshness').getAttribute('data-state');
    expect(FRESHNESS_STATES as readonly string[]).toContain(state);
  });

  it('reschedules another timer after a successful refresh', async () => {
    vi.useFakeTimers();
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })));

    render(<AutoRefresh locale="en" />);

    // First timer fires and settles
    await vi.runOnlyPendingTimersAsync();
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // Let fetch promise and finally block settle so React schedules next timer
    await vi.advanceTimersByTimeAsync(0);

    // Second timer must be scheduled and fire
    await vi.runOnlyPendingTimersAsync();
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    fetchSpy.mockRestore();
    vi.useRealTimers();
  });
});
