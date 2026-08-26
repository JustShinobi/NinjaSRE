import type { ReactNode } from 'react';

import { Button, CONTROL_SHAPE, STATE_SKIN, VARIANT_SKIN } from '@/components/action';
import { cx } from '@/design/cx';
import { AlertCircleIcon, InboxIcon } from '@/design/icons';

/**
 * The two states a data-bearing region spends most of its first day in.
 *
 * The design document calls the empty state the highest-leverage requirement in
 * the console, and the reason is specific: a fresh deployment that looks broken
 * is indistinguishable from one that is. So all four parts are required — an
 * icon, a one-line heading, a sentence saying what would be here and how to get
 * it, and an action — and "required" means the component refuses to render
 * without them rather than a reviewer noticing.
 *
 * The error state is scoped to its own panel. It names the dependency, says the
 * rest of the page is unaffected, and offers a retry for that panel only. An
 * error that took the whole page down for one failed metric source is an error
 * that teaches operators to distrust the console.
 */

/**
 * What to do about the emptiness — a place to go, or something to run.
 *
 * A union rather than a handler that sometimes navigates, because the two are
 * different elements and rendering the wrong one is what put every empty
 * state's action into the accessibility tree twice. An action with an `href` is
 * a link and reads as a link; an action with an `onSelect` is a button. Nothing
 * can be both, so nothing needs a hidden twin to make up the difference.
 */
export type EmptyStateAction =
  | { readonly label: string; readonly href: string; readonly onSelect?: never }
  | { readonly label: string; readonly onSelect: () => void; readonly href?: never };

export interface EmptyStateProps {
  readonly heading: string;
  readonly body: string;
  readonly action: EmptyStateAction;
  readonly icon?: ReactNode;
}

/** Nothing here yet, what would be here, and how to get it. */
export function EmptyState({
  heading,
  body,
  action,
  icon,
}: EmptyStateProps): ReactNode {
  if (body.trim() === '') {
    throw new Error(
      `The empty state "${heading}" has no body. "Nothing here" is not advice; say what would be here and how to get it.`,
    );
  }
  // The type already makes a missing action impossible, and re-checking it
  // here would be code the type checker can prove unreachable. What a
  // well-typed caller *can* still do is supply an action with nothing written
  // on it, which is the same dead end wearing a label, so that is what is
  // guarded.
  if (action.label.trim() === '') {
    throw new Error(
      `The empty state "${heading}" has no action. An empty state with nothing to do is a dead end.`,
    );
  }
  return (
    <div className="flex flex-col items-center gap-3 px-5 py-7 text-center">
      <span className="flex items-center justify-center size-7 rounded-3 bg-neutral-bg text-muted">
        {icon ?? <InboxIcon size="empty" />}
      </span>
      <h4 className="text-strong">{heading}</h4>
      {/* The block stays centred; the sentence does not. Centring is fine for
          a line and costs a reader real effort at three, because every line
          starts at a different x and the eye has to find the beginning of each
          one. Knowledge's empty state is four lines long and explains the two
          ways a document can arrive — exactly the case where a ragged right
          edge and a fixed left one is the readable shape. */}
      <p className="text-muted text-small max-w-prose text-left">{body}</p>
      {action.href === undefined ? (
        <Button
          variant="primary"
          onClick={() => {
            action.onSelect();
          }}
        >
          {action.label}
        </Button>
      ) : (
        // One element, not a button beside a hidden link. The identifier stays
        // what every screen's test already looks for; what changes is that
        // there is now exactly one thing carrying it.
        <a
          href={action.href}
          data-testid="way-back"
          data-variant="primary"
          data-state="default"
          className={cx(CONTROL_SHAPE, VARIANT_SKIN.primary, STATE_SKIN.default)}
        >
          {action.label}
        </a>
      )}
    </div>
  );
}

export interface ErrorStateProps {
  /** What failed, in a sentence, from the catalogue. */
  readonly heading: string;
  /** What failed. Named, because "something went wrong" is not a fault report. */
  readonly dependency: string;
  readonly detail: string;
  /** What the retry control is called, in the viewer's language. */
  readonly retryLabel: string;
  readonly onRetry: () => void;
}

/** One panel failed; the page did not. */
export function ErrorState({
  heading,
  dependency,
  detail,
  retryLabel,
  onRetry,
}: ErrorStateProps): ReactNode {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 px-5 py-7 text-center"
    >
      <span className="flex items-center justify-center size-7 rounded-3 bg-danger-bg text-danger">
        <AlertCircleIcon size="empty" />
      </span>
      <h4 className="text-strong">{heading}</h4>
      <p className="text-muted text-small max-w-prose">
        <span className="font-mono">{dependency}</span> {detail}
      </p>
      <Button
        onClick={() => {
          onRetry();
        }}
      >
        {retryLabel}
      </Button>
    </div>
  );
}
