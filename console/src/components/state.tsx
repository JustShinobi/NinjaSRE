import type { ReactNode } from 'react';

import { Button } from '@/components/action';
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

export interface EmptyStateAction {
  readonly label: string;
  readonly onSelect: () => void;
}

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
      <p className="text-muted text-small max-w-prose">{body}</p>
      <Button
        variant="primary"
        onClick={() => {
          action.onSelect();
        }}
      >
        {action.label}
      </Button>
    </div>
  );
}

export interface ErrorStateProps {
  /** What failed. Named, because "something went wrong" is not a fault report. */
  readonly dependency: string;
  readonly detail: string;
  readonly onRetry: () => void;
}

/** One panel failed; the page did not. */
export function ErrorState({
  dependency,
  detail,
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
      <h4 className="text-strong">Could not reach this source</h4>
      <p className="text-muted text-small max-w-prose">
        <span className="font-mono">{dependency}</span> {detail}. The rest of this page
        is unaffected.
      </p>
      <Button
        onClick={() => {
          onRetry();
        }}
      >
        Retry this panel
      </Button>
    </div>
  );
}
