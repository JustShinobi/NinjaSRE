'use client';

import type { ReactNode } from 'react';
import { useId, useState } from 'react';

import { Button } from '@/components/action';

/**
 * A capability result that is larger than anybody will read.
 *
 * Bounded rather than truncated, and the difference is the whole component: a
 * truncation is silent, and a bound says what it bounded and by how much, so a
 * reader knows there is more *and* knows how much more. The mockup's line reads
 * "result bounded to 3 of 19 volumes, ranked by size" — the bound, the total,
 * and what decided which three, which is three facts a scrollbar does not carry.
 *
 * The full payload is one control away and the raw text is one more, because the
 * moment a result matters is the moment somebody wants to paste it into a
 * ticket. A page that stalls for four seconds rendering six megabytes of JSON is
 * a page nobody opens twice, so the expansion is a decision the reader makes.
 */

/** How many lines are shown before a payload is bounded. */
export const PAYLOAD_LINE_BOUND = 24;

/** What was bounded, for the sentence that says so. */
export interface Bound {
  readonly total: number;
  readonly shown: number;
}

/** How much of `content` is shown at the bound, and how much there is. */
export function boundOf(content: string, bound: number = PAYLOAD_LINE_BOUND): Bound {
  const total = content === '' ? 0 : content.split('\n').length;
  return { total, shown: Math.min(total, bound) };
}

/** The first `bound` lines of `content`. */
function bounded(content: string, bound: number): string {
  return content.split('\n').slice(0, bound).join('\n');
}

export interface PayloadLabels {
  /** "1,918 lines in the payload; showing the first 24." Interpolated by the caller. */
  readonly bounded: string;
  readonly expand: string;
  readonly collapse: string;
  readonly copy: string;
  readonly copied: string;
}

export interface BoundedPayloadProps {
  /** What this payload is of. Names the region for anything that lists them. */
  readonly label: string;
  readonly content: string;
  readonly labels: PayloadLabels;
  readonly bound?: number;
}

/** A payload, bounded, expandable, with the raw text retrievable. */
export function BoundedPayload({
  label,
  content,
  labels,
  bound = PAYLOAD_LINE_BOUND,
}: BoundedPayloadProps): ReactNode {
  const id = useId();
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const { total, shown } = boundOf(content, bound);
  const over = total > shown;

  return (
    <div className="flex flex-col gap-1 min-w-0">
      <span id={id} className="sr-only">
        {label}
      </span>
      <pre
        role="region"
        aria-labelledby={id}
        tabIndex={0}
        data-testid="payload"
        data-expanded={expanded}
        className="p-3 rounded-2 edge border-border bg-sunken font-mono text-meta whitespace-pre-wrap break-all overflow-auto"
      >
        {expanded || !over ? content : bounded(content, bound)}
      </pre>
      <div className="flex items-center gap-3 flex-wrap">
        {over ? (
          <>
            <p data-testid="bounded" className="text-meta text-muted">
              {labels.bounded}
            </p>
            <Button
              variant="quiet"
              data-testid="expand"
              aria-expanded={expanded}
              onClick={() => {
                setExpanded(!expanded);
              }}
            >
              {expanded ? labels.collapse : labels.expand}
            </Button>
          </>
        ) : null}
        <Button
          variant="quiet"
          data-testid="copy"
          onClick={() => {
            void navigator.clipboard.writeText(content).then(
              () => {
                setCopied(true);
              },
              () => {
                // A refused clipboard is the browser's decision, not a fault of
                // the console's, and the payload is still on the screen.
                setCopied(false);
              },
            );
          }}
        >
          {copied ? labels.copied : labels.copy}
        </Button>
      </div>
    </div>
  );
}
