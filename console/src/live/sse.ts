/**
 * Reading server-sent events out of a byte stream, as a pure function.
 *
 * The browser has an `EventSource`, and it is not usable here for two reasons
 * that are both about honesty rather than convenience. It cannot present a
 * cursor on the first connection — only on its own reconnections — so a page
 * reopened after a sleep would either start the transcript again or skip the
 * gap. And it reports every failure as one opaque `error`, so a session that
 * expired mid-stream would be indistinguishable from a network that dropped,
 * and the console would sit reconnecting into a session that is over.
 *
 * So the frames are read from a `fetch` body, and the parsing is here: a pure
 * function over text, tested without a network, a browser or a timer.
 */

/** One frame off the wire. */
export interface Frame {
  /** The cursor to resume from after this frame, when it carries one. */
  readonly id: string;
  readonly event: string;
  readonly data: string;
  /** A keep-alive. Carries nothing and means only that the socket is alive. */
  readonly comment: boolean;
}

/** What one chunk of the body contained, and what is not a frame yet. */
export interface Framed {
  readonly frames: readonly Frame[];
  /** The incomplete tail, to be prepended to the next chunk. */
  readonly rest: string;
}

/** The frame separator: a blank line, whichever way the sender ends lines. */
const SEPARATOR = '\n\n';

/**
 * The complete frames in `text`, and the incomplete tail after them.
 *
 * The tail matters more than it looks: a chunk boundary lands in the middle of
 * a frame routinely, and a parser that dropped the remainder would lose one
 * event per chunk — silently, and more often the busier the run is.
 */
export function framesIn(text: string): Framed {
  const normalised = text.replace(/\r\n/g, '\n');
  const blocks = normalised.split(SEPARATOR);
  const rest = blocks.pop() ?? '';
  const frames: Frame[] = [];

  for (const block of blocks) {
    if (block === '') continue;
    let id = '';
    let event = '';
    const data: string[] = [];
    let comment = false;

    for (const line of block.split('\n')) {
      if (line.startsWith(':')) {
        comment = true;
        continue;
      }
      const at = line.indexOf(':');
      const name = at < 0 ? line : line.slice(0, at);
      // One optional space after the colon is part of the framing rather than
      // part of the value.
      const value = at < 0 ? '' : line.slice(at + 1).replace(/^ /, '');
      if (name === 'id') id = value;
      else if (name === 'event') event = value;
      else if (name === 'data') data.push(value);
    }

    frames.push({
      id,
      event,
      data: data.join('\n'),
      comment: comment && data.length === 0,
    });
  }

  return { frames, rest };
}
