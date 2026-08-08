/**
 * A 401 is a session event, not a request outcome.
 *
 * Three panels fetching at once against an expired session produce three 401s.
 * Handled as request outcomes they produce three prompts, or three redirects
 * racing each other, or — the version that actually ships — one prompt and two
 * error toasts behind it. So they are not handled as request outcomes. Every
 * refusal is published to one controller, and the controller ends the session
 * once.
 *
 * The collapse is a property of there being one controller, not of each caller
 * checking whether another already handled it. That distinction is the whole
 * design: a check-before-acting is a race with a small window, and a small
 * window is the kind that opens on the slow morning when it matters.
 */

/** What the console does when the session is over. */
export interface SessionEnding {
  /** The route the viewer was on, to come back to after signing in again. */
  readonly returnTo: string;
  /** Why it ended, which is what the sign-in page explains. */
  readonly reason: 'expired' | 'signed-out';
}

/** Somewhere for a session ending to be delivered. */
export type SessionListener = (ending: SessionEnding) => void;

/**
 * The one controller a refusal reaches.
 *
 * It ends once. Every call after the first is dropped on the floor, including
 * the ones already in flight when the first arrived — which is exactly the case
 * that produces the second prompt when this is done per request.
 */
export class SessionController {
  #ended = false;
  #listener: SessionListener | null = null;

  /** Where to deliver the ending. Set once, by whatever renders the prompt. */
  listen(listener: SessionListener): void {
    this.#listener = listener;
  }

  /** Whether this session has already ended. */
  get hasEnded(): boolean {
    return this.#ended;
  }

  /** The API refused a call. Ends the session, at most once. */
  unauthorized(returnTo: string): void {
    this.#end({ returnTo, reason: 'expired' });
  }

  /** The viewer asked to leave. Ends the session, at most once. */
  signOut(returnTo: string): void {
    this.#end({ returnTo, reason: 'signed-out' });
  }

  /** Forget that it ended, which only a test and a fresh page load ever want. */
  reset(): void {
    this.#ended = false;
  }

  #end(ending: SessionEnding): void {
    if (this.#ended) {
      return;
    }
    this.#ended = true;
    this.#listener?.(ending);
  }
}

/**
 * The process's controller.
 *
 * A module-level instance rather than a React context, because the API client
 * publishes into it and the API client is not a component. A context would mean
 * every caller had to be inside the tree, and a fetch in a server action is not.
 */
export const sessionController = new SessionController();

/**
 * Publish a refusal.
 *
 * Called by the one module that makes requests. `returnTo` is read here rather
 * than passed in, because the caller is a fetch wrapper and has no idea which
 * page it is on — and a route remembered by the thing that knows it is a route
 * that is right.
 */
export function reportUnauthorized(): void {
  const returnTo =
    typeof window === 'undefined'
      ? '/'
      : `${window.location.pathname}${window.location.search}`;
  sessionController.unauthorized(returnTo);
}
