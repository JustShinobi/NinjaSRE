/**
 * Which rows of a long list are actually in the document.
 *
 * Two requirements meet here. One list may not be silently truncated, and one
 * screen may not cost more because there is more of it. Both are satisfied by
 * the same arithmetic: every row is the same height, so the position of row *n*
 * is `n × height` without measuring anything, and the number of rows in the
 * document is a function of the viewport rather than of the collection.
 *
 * The fixed height is a constraint on the design rather than an implementation
 * detail, and it is worth saying plainly: a row that grows to fit its content
 * cannot be placed without measuring it, and a list that measures ten thousand
 * rows to place one has already spent the budget this module exists to protect.
 * A cell with more to say than fits gets a bound and a way to open it, which is
 * what `payload.tsx` is for.
 */

/**
 * How many rows are kept beyond each edge of the viewport.
 *
 * A scroll is not a sequence of small steps; a wheel flick or a dragged
 * scrollbar moves several viewports between two frames. Without a margin the
 * reader sees the reserved space before the rows land in it, which reads as the
 * list having lost its content.
 */
export const ROW_OVERSCAN = 6;

/** One row height, in pixels, for every windowed list in the console. */
export const ROW_HEIGHT = 44;

export interface WindowRequest {
  readonly total: number;
  readonly rowHeight: number;
  /** The height of the scrolling region, in pixels. */
  readonly viewport: number;
  readonly scrollTop: number;
}

/** The rows to draw, and the space to leave where the others would have been. */
export interface RowWindow {
  /** The index of the first row drawn. */
  readonly first: number;
  readonly count: number;
  /** Pixels reserved above, so the scrollbar means what it says. */
  readonly padTop: number;
  readonly padBottom: number;
}

/**
 * The window over `total` rows at `scrollTop`.
 *
 * A list short enough to fit within the overscan is returned whole. Windowing it
 * would add two padding elements and a scroll listener to a list of three rows,
 * which is cost for nothing.
 */
export function windowFor({
  total,
  rowHeight,
  viewport,
  scrollTop,
}: WindowRequest): RowWindow {
  if (rowHeight <= 0) {
    throw new Error('a windowed list needs a row height greater than nought');
  }
  if (total <= 0) {
    return { first: 0, count: 0, padTop: 0, padBottom: 0 };
  }

  const visible = Math.ceil(viewport / rowHeight) + 1;
  const drawn = visible + 2 * ROW_OVERSCAN;
  if (total <= drawn) {
    return { first: 0, count: total, padTop: 0, padBottom: 0 };
  }

  const offset = scrollTop > 0 ? scrollTop : 0;
  const wanted = Math.floor(offset / rowHeight) - ROW_OVERSCAN;
  const first = Math.min(Math.max(wanted, 0), total - drawn);
  const count = Math.min(drawn, total - first);

  return {
    first,
    count,
    padTop: first * rowHeight,
    padBottom: (total - first - count) * rowHeight,
  };
}
