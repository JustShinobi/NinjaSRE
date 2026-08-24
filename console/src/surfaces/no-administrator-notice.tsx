import type { ReactNode } from 'react';

/** The two strings this block shows, already resolved from the catalogue. */
export interface NoAdministratorNoticeLabels {
  readonly title: string;
  readonly body: string;
}

/**
 * The block shown on the sign-in form and the first-run screen, in the one
 * state neither owns yet: no local administrator, and no identity provider
 * to be the way in instead.
 *
 * `command` is the CLI invitation, or the empty string when the block
 * should not render at all — absent from the document, never merely
 * hidden. That single prop is what lets both screens share this component
 * without a second `if` of their own: whatever
 * `localAdministratorAvailability()` returned is handed straight through.
 *
 * The command itself is never translated (FR-079) — it is a shell
 * invocation, not prose — while `labels` carries everything that is.
 */
export function NoAdministratorNotice({
  command,
  labels,
}: {
  readonly command: string;
  readonly labels: NoAdministratorNoticeLabels;
}): ReactNode {
  if (!command) return null;
  return (
    <div
      data-testid="no-administrator-notice"
      role="status"
      className="flex flex-col gap-2 rounded-2 edge border-border bg-sunken p-4"
    >
      <p className="text-small font-semibold text-text">{labels.title}</p>
      <p className="text-small text-muted">{labels.body}</p>
      <pre
        data-testid="no-administrator-command"
        className="select-all overflow-x-auto rounded-2 border-border bg-surface px-3 py-2 text-small text-text"
      >
        {command}
      </pre>
    </div>
  );
}
