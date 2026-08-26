'use client';

import type { ReactNode } from 'react';
import { cloneElement, isValidElement, useId, useState } from 'react';

import { IconButton } from '@/components/action';
import { cx } from '@/design/cx';
import { CloseIcon } from '@/design/icons';
import type { SemanticRole } from '@/design/tokens';

/**
 * "Wait", "here is how far", and "that happened".
 *
 * Every animation here is a named class rather than a duration written into the
 * component, which is what lets the global reduced-motion rule remove all of
 * them at once. A component carrying its own inline duration would escape that
 * rule silently, and the viewer who asked for no motion would get motion from
 * exactly the components most likely to move.
 */

export interface SpinnerProps {
  /** What is being waited for. A spinner with no answer to that is a shrug. */
  readonly label: string;
}

/** Something is happening, and this is what. */
export function Spinner({ label }: SpinnerProps): ReactNode {
  return (
    <span role="status" aria-label={label} className="inline-flex items-center gap-2">
      <span
        data-animated="spin"
        aria-hidden="true"
        className="icon-nav rounded-full edge-ring border-border-strong border-t-transparent animate-spin"
      />
      <span className="text-meta text-muted">{label}</span>
    </span>
  );
}

/** The shapes a skeleton reserves, matched to what will land in them. */
const SKELETON_WIDTH = {
  title: 'h-5 w-6',
  line: 'h-3 w-7',
  figure: 'h-6 w-4',
  // The three above reserve a word inside a panel that is otherwise drawn.
  // These two reserve a whole row, for the case where nothing around them has
  // arrived either — a route being fetched, where the alternative is a region
  // that is simply blank and indistinguishable from one that failed.
  'row-title': 'h-5 w-full',
  row: 'h-3 w-full',
} as const;

/**
 * What the placeholder is sitting on, which is what decides its tint.
 *
 * `neutral-bg` is the same value as the page ground in the light theme, so a
 * placeholder drawn on the page itself is invisible — which is not a subtle
 * failure: the region reserved for a heading reads as blank space, and blank
 * space is what a region that failed to load also reads as. Inside a panel,
 * over `raised`, the same tint is exactly right.
 */
const SKELETON_GROUND = {
  panel: 'bg-neutral-bg',
  page: 'bg-hover',
} as const;

export interface SkeletonProps {
  readonly width: keyof typeof SKELETON_WIDTH;
  /** Whether the real content has arrived. The box does not change either way. */
  readonly loaded?: boolean;
  /** Which ground it is drawn on. Panels are the common case and the default. */
  readonly ground?: keyof typeof SKELETON_GROUND;
}

/**
 * A reserved box.
 *
 * The geometry classes are identical loaded and unloaded, which is the whole
 * requirement: a skeleton whose box differs from the content's box is the
 * layout shift it was put there to prevent.
 */
export function Skeleton({
  width,
  loaded = false,
  ground = 'panel',
}: SkeletonProps): ReactNode {
  return (
    <span
      aria-hidden="true"
      data-loaded={loaded}
      className={cx(
        'block rounded-2',
        SKELETON_WIDTH[width],
        loaded ? 'bg-transparent' : cx(SKELETON_GROUND[ground], 'animate-pulse'),
      )}
    />
  );
}

/** Where a reading stops being fine and starts being a problem. */
const THRESHOLDS = { warning: 80, danger: 90 } as const;

export interface ProgressBarProps {
  readonly label: string;
  /** Per cent, 0 to 100. */
  readonly value: number;
}

/**
 * A bar and its number.
 *
 * The number is not optional: a bar alone is a shape a reader has to estimate,
 * and "about ninety per cent" is not a figure anybody acts on. The bar is
 * bordered so that nought per cent is still visibly a bar rather than a gap.
 */
export function ProgressBar({ label, value }: ProgressBarProps): ReactNode {
  const clamped = Math.min(100, Math.max(0, value));
  const role: Extract<SemanticRole, 'warning' | 'danger'> | 'accent' =
    clamped >= THRESHOLDS.danger
      ? 'danger'
      : clamped >= THRESHOLDS.warning
        ? 'warning'
        : 'accent';
  const fill = { accent: 'bg-accent', warning: 'bg-warning', danger: 'bg-danger' }[
    role
  ];

  return (
    <span className="flex items-center gap-2">
      <span
        role="progressbar"
        aria-label={label}
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        data-testid="meter"
        data-role={role}
        className="block h-2 w-7 rounded-full edge border-border bg-neutral-bg overflow-hidden"
      >
        <span
          className={cx('block h-full', fill)}
          style={{ inlineSize: `${String(clamped)}%` }}
        />
      </span>
      <span className="text-meta tabular-nums text-muted">{clamped}%</span>
    </span>
  );
}

export interface ToastProps {
  readonly role: SemanticRole;
  readonly message: string;
  /** Where the outcome is also recorded. A toast is never the only record. */
  readonly recordedAt?: { readonly href: string; readonly label: string };
  /** What the dismiss control is called, in the viewer's language. */
  readonly dismissLabel: string;
  readonly onDismiss: () => void;
}

const TOAST_SKIN: Readonly<Record<SemanticRole, string>> = {
  success: 'bg-success-bg text-success border-success',
  warning: 'bg-warning-bg text-warning border-warning',
  danger: 'bg-danger-bg text-danger border-danger',
  info: 'bg-info-bg text-info border-info',
  neutral: 'bg-neutral-bg text-neutral border-border-strong',
};

/**
 * An outcome, announced.
 *
 * Politely, unless it is a failure — a failure announced politely waits for the
 * screen reader to finish whatever it was saying, which for a failed reclaim is
 * too late. And never as the only record: every toast that reports something
 * consequential names where the same thing is written down.
 */
export function Toast({
  role,
  message,
  recordedAt,
  dismissLabel,
  onDismiss,
}: ToastProps): ReactNode {
  const assertive = role === 'danger';
  return (
    <div
      role={assertive ? 'alert' : 'status'}
      aria-live={assertive ? 'assertive' : 'polite'}
      className={cx(
        'flex items-center gap-3 px-4 py-3 rounded-3 edge shadow-2 motion-toast',
        TOAST_SKIN[role],
      )}
    >
      <span className="text-small">{message}</span>
      {recordedAt === undefined ? null : (
        <a href={recordedAt.href} className="text-small underline underline-offset-2">
          {recordedAt.label}
        </a>
      )}
      <IconButton label={dismissLabel} icon={<CloseIcon />} onClick={onDismiss} />
    </div>
  );
}

export interface TooltipProps {
  readonly text: string;
  readonly children: ReactNode;
}

/**
 * A description, on hover and on focus.
 *
 * `aria-describedby` rather than `aria-label`: a tooltip adds to a control's
 * name, it does not replace it, and a tooltip that replaced it would leave the
 * control called whatever the tooltip happened to say.
 */
export function Tooltip({ text, children }: TooltipProps): ReactNode {
  const id = useId();
  const [shown, setShown] = useState(false);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => {
        setShown(true);
      }}
      onMouseLeave={() => {
        setShown(false);
      }}
      onFocusCapture={() => {
        setShown(true);
      }}
      onBlurCapture={() => {
        setShown(false);
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') setShown(false);
      }}
    >
      {/*
       * The description goes on the control, not on a wrapper around it.
       * `aria-describedby` on a `span` describes the span, and a screen reader
       * reading the button inside it hears nothing — which is the failure this
       * component exists to avoid.
       */}
      {shown && isValidElement<{ 'aria-describedby'?: string }>(children)
        ? // Only while the tooltip is in the tree. A reference to an element
          // that is not there is a description a screen reader silently drops,
          // and the audit finds it because it is indistinguishable from a typo.
          cloneElement(children, { 'aria-describedby': id })
        : children}
      {shown ? (
        <span
          id={id}
          role="tooltip"
          className="absolute top-6 left-0 px-2 py-1 rounded-1 edge border-border bg-raised text-meta shadow-2 motion-hover"
        >
          {text}
        </span>
      ) : null}
    </span>
  );
}
