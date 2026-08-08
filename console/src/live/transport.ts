import type { StreamHandle, StreamHandlers, StreamSource } from './connection';
import { framesIn } from './sse';

/**
 * The stream, as the browser actually reads it.
 *
 * A `fetch` with a reader rather than an `EventSource`, for the two reasons
 * `sse.ts` gives: the cursor has to be presented on the *first* connection, and
 * a refusal has to be distinguishable from a network that dropped. Both are
 * properties an `EventSource` cannot express, and both decide whether an
 * operator is looking at a live transcript or at a stale one that says live.
 *
 * The request goes to the console's own origin. The credential is in an
 * HTTP-only cookie, so a browser cannot present it to the deployment — the
 * route handler behind that address is what does, and it is a courier.
 */
export const fetchStreamSource: StreamSource = {
  open(address: string, handlers: StreamHandlers): StreamHandle {
    const controller = new AbortController();
    let closed = false;

    const read = async (): Promise<void> => {
      const response = await fetch(address, {
        signal: controller.signal,
        headers: { accept: 'text/event-stream' },
        cache: 'no-store',
      });
      if (!response.ok || response.body === null) {
        handlers.onError(response.status);
        return;
      }
      handlers.onOpen();

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let carry = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        const framed = framesIn(carry + decoder.decode(value, { stream: true }));
        carry = framed.rest;
        for (const frame of framed.frames) {
          if (!frame.comment) handlers.onFrame(frame.data);
        }
      }
      // A stream that ends is a stream that has to be reopened. The deployment
      // closes one when a subscriber falls behind its buffer, and the answer to
      // that is to reconnect with the cursor rather than to declare the run over.
      if (!closed) handlers.onError(0);
    };

    void read().catch(() => {
      if (!closed) handlers.onError(0);
    });

    return {
      close(): void {
        closed = true;
        controller.abort();
      },
    };
  },
};
