'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button } from '@/components/action';

/**
 * The report's own Markdown, one control away instead of printed twice.
 *
 * This replaces a disclosure that held the *source of the document rendered
 * directly above it* — the same sentences, once as prose and once as `###`
 * headings, on every run page in the console. Nobody reads a document twice,
 * and the second copy cost the panel its height.
 *
 * The reason the raw text was kept at all is real and survives here: somebody
 * pastes a report into a ticket or a channel, and what they want in their
 * clipboard is the Markdown, not the rendered text with its list markers lost.
 * A button does that in one gesture and takes one line of the screen.
 *
 * The failure path matters more than it looks. A refused clipboard is the
 * browser's decision — an insecure origin, a permission the viewer declined —
 * and the honest response is to say the copy did not happen, not to flash
 * "copied" over a clipboard that still holds whatever it held before.
 */

export interface CopyReportLabels {
  readonly copy: string;
  readonly copied: string;
  readonly refused: string;
}

export interface CopyReportProps {
  readonly text: string;
  readonly labels: CopyReportLabels;
}

/** What the button is saying right now. */
type Said = 'idle' | 'copied' | 'refused';

/** A control that puts the report's Markdown on the clipboard. */
export function CopyReport({ text, labels }: CopyReportProps): ReactNode {
  const [said, setSaid] = useState<Said>('idle');

  return (
    <Button
      variant="quiet"
      data-testid="copy-report"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(
          () => {
            setSaid('copied');
          },
          () => {
            setSaid('refused');
          },
        );
      }}
    >
      {said === 'copied' ? labels.copied : said === 'refused' ? labels.refused : labels.copy}
    </Button>
  );
}
