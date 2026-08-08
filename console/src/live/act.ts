/**
 * Asking the console's own process to do something, and what comes back.
 *
 * One shape for every write this feature makes, because every one of them is
 * optimistic and every optimistic write needs the same two facts on refusal:
 * that it was refused, and why. A caller that had to pick the reason out of a
 * different field per endpoint would be a caller that stops bothering.
 */

/** What a write did. */
export interface Applied {
  readonly ok: boolean;
  /** The deployment's own words. Empty when it agreed, or would not say. */
  readonly reason: string;
  /** Whether the deployment answered at all. */
  readonly reachable: boolean;
  /** The run a start produced, when the write was one. */
  readonly runId: string;
}

function field(record: unknown, name: string): unknown {
  return Reflect.get(Object(record), name);
}

/** `POST` `address` with `body`, and read the answer the handlers agree on. */
export async function act(address: string, body: unknown): Promise<Applied> {
  try {
    const response = await fetch(address, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    const answer: unknown = await response.json().catch(() => ({}));
    const reason = field(answer, 'reason');
    return {
      ok: response.ok,
      reason: typeof reason === 'string' ? reason : '',
      reachable: field(answer, 'reachable') !== false,
      runId:
        typeof field(answer, 'runId') === 'string'
          ? String(field(answer, 'runId'))
          : '',
    };
  } catch {
    // The console's own process, not the deployment's. If this fails the page
    // has lost its own server, and saying "the deployment refused" would send
    // somebody to look at the wrong machine.
    return { ok: false, reason: '', reachable: false, runId: '' };
  }
}

/** Where a run is steered, and where a question is answered. */
export const RUN_ENDPOINT = '/api/run';
export const ANSWER_ENDPOINT = '/api/answer';
