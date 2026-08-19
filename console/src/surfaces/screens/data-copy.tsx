'use client';

import { useState, type ReactNode } from 'react';

import { Button } from '@/components/action';

/**
 * One line of text, and the one control that puts it on the clipboard.
 *
 * Built for the webhook addresses on the Data screen: a value an operator has
 * to paste into a system this console does not configure, which is exactly the
 * kind of string a person otherwise selects by hand and gets wrong at the
 * edges. A click that cannot fail silently — the label changes to say it
 * worked, and stays changed rather than reverting on its own, so a person who
 * looked away for a second still finds the answer when they look back.
 */

export interface CopyValueLabels {
  readonly copy: string;
  readonly copied: string;
}

export interface CopyValueProps {
  readonly value: string;
  readonly labels: CopyValueLabels;
  /** Names this control for anything that looks for it. */
  readonly testId?: string;
}

/** A value, shown in full, with a button that copies it in one click. */
export function CopyValue({ value, labels, testId }: CopyValueProps): ReactNode {
  const [copied, setCopied] = useState(false);

  return (
    <span className="flex items-center gap-2 flex-wrap min-w-0" data-testid={testId}>
      <code className="text-meta break-all">{value}</code>
      <Button
        variant="quiet"
        data-testid={testId === undefined ? undefined : `${testId}-copy`}
        onClick={() => {
          void navigator.clipboard.writeText(value).then(
            () => {
              setCopied(true);
            },
            () => {
              // A refused clipboard is the browser's decision; the value is
              // still on the screen and still selectable by hand.
              setCopied(false);
            },
          );
        }}
      >
        {copied ? labels.copied : labels.copy}
      </Button>
    </span>
  );
}

export interface CopyActionProps {
  /** What actually reaches the clipboard. Never rendered on the screen. */
  readonly value: string;
  readonly label: string;
  readonly copiedLabel: string;
  /** Names this control for anything that looks for it. */
  readonly testId?: string;
}

/**
 * A button that copies `value` without ever displaying it.
 *
 * `CopyValue`'s sibling for a block too long to show inline — the
 * Alertmanager receiver YAML, not a URL a row already prints in full. The
 * value still never leaves the click handler's own closure: nothing renders
 * it, and nothing but the browser's clipboard API ever reads it.
 */
export function CopyAction({
  value,
  label,
  copiedLabel,
  testId,
}: CopyActionProps): ReactNode {
  const [copied, setCopied] = useState(false);

  return (
    <Button
      variant="quiet"
      data-testid={testId}
      onClick={() => {
        void navigator.clipboard.writeText(value).then(
          () => {
            setCopied(true);
          },
          () => {
            setCopied(false);
          },
        );
      }}
    >
      {copied ? copiedLabel : label}
    </Button>
  );
}
