import { describe, expect, it } from 'vitest';

import { ROW_OVERSCAN, windowFor, type RowWindow } from '@/surfaces/window';

/**
 * The contract a long list is rendered under, and the reason it is a contract
 * rather than a component detail.
 *
 * Every row is the same height. That is a constraint on the *design* — a row
 * that grows to fit its content cannot be placed without measuring it, and a
 * list that measures ten thousand rows to place one has already lost. Given a
 * fixed height, the position of any row is arithmetic, and the number of rows in
 * the document stops depending on how many there are.
 */

const ROW = 44;
const VIEWPORT = 660;

function windowAt(total: number, scrollTop = 0): RowWindow {
  return windowFor({ total, rowHeight: ROW, viewport: VIEWPORT, scrollTop });
}

describe('the window over a long list', () => {
  it('renders a bounded number of rows however long the list is', () => {
    const hundred = windowAt(100);
    const tenThousand = windowAt(10_000);
    const million = windowAt(1_000_000);

    // This is the scaling assertion, and it is the whole point of the module:
    // the cost of a screen must not grow with the length of what it is showing.
    expect(tenThousand.count).toBe(hundred.count);
    expect(million.count).toBe(hundred.count);
    expect(tenThousand.count).toBeLessThanOrEqual(
      Math.ceil(VIEWPORT / ROW) + 2 * ROW_OVERSCAN + 1,
    );
  });

  it('reserves the exact height of everything it is not drawing', () => {
    const window = windowAt(10_000, 4400);

    expect(window.padTop + window.count * ROW + window.padBottom).toBe(10_000 * ROW);
  });

  it('keeps rows above the viewport so a fast scroll does not show a gap', () => {
    const window = windowAt(10_000, 44_000);

    expect(window.first).toBe(1000 - ROW_OVERSCAN);
  });

  it('does not run off either end of the list', () => {
    expect(windowAt(10_000, 0).first).toBe(0);
    expect(windowAt(10_000, 0).padTop).toBe(0);

    const bottom = windowAt(10_000, 10_000 * ROW);
    expect(bottom.first + bottom.count).toBeLessThanOrEqual(10_000);
    expect(bottom.padBottom).toBe(0);
  });

  it('shows a short list whole rather than windowing it', () => {
    const window = windowAt(3);

    expect(window).toEqual({ first: 0, count: 3, padTop: 0, padBottom: 0 });
  });

  it('shows nothing, and reserves nothing, for an empty list', () => {
    expect(windowAt(0)).toEqual({ first: 0, count: 0, padTop: 0, padBottom: 0 });
  });

  it('refuses a row height of nought rather than dividing by it', () => {
    expect(() =>
      windowFor({ total: 10, rowHeight: 0, viewport: VIEWPORT, scrollTop: 0 }),
    ).toThrow(/row height/i);
  });

  it('is unmoved by a negative scroll, which a rubber-banding browser reports', () => {
    expect(windowAt(10_000, -240).first).toBe(0);
  });
});
