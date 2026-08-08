import type { ReactNode } from 'react';

import { cx } from '@/design/cx';
import {
  ActivityIcon,
  AlertCircleIcon,
  CheckIcon,
  ClockIcon,
  RefreshIcon,
  ShieldIcon,
  type IconProps,
} from '@/design/icons';

/**
 * What the system has been doing while nobody watched.
 *
 * The feed mixes every source into one stream deliberately: a reader coming back
 * on Monday wants the narrative, not five panels each holding a third of it.
 * Each entry has an icon well coloured by outcome, a relative time, and the
 * absolute instant on hover and on focus — on focus as well, because a tooltip a
 * pointer alone can reach is a tooltip half the operators cannot.
 */

export const ACTIVITY_KINDS = [
  'run',
  'incident',
  'verification',
  'sweep',
  'guardian',
  'recurrence',
] as const;

export type ActivityKind = (typeof ACTIVITY_KINDS)[number];

const KIND_ICON: Readonly<Record<ActivityKind, (props: IconProps) => ReactNode>> = {
  run: ActivityIcon,
  incident: AlertCircleIcon,
  verification: CheckIcon,
  sweep: RefreshIcon,
  guardian: ShieldIcon,
  recurrence: ClockIcon,
};

const OUTCOME_WELL: Readonly<Record<string, string>> = {
  success: 'bg-success-bg text-success border-success',
  warning: 'bg-warning-bg text-warning border-warning',
  danger: 'bg-danger-bg text-danger border-danger',
  info: 'bg-info-bg text-info border-info',
  neutral: 'bg-neutral-bg text-neutral border-border-strong',
};

/** One thing that happened. */
export interface ActivityEntry {
  readonly id: string;
  readonly kind: ActivityKind;
  /** The word for the kind, in the viewer's language. */
  readonly kindLabel: string;
  /** The semantic weight the outcome earns. */
  readonly outcome: keyof typeof OUTCOME_WELL;
  readonly title: string;
  readonly detail: string;
  readonly href: string;
  readonly relative: string;
  readonly absolute: string;
  readonly iso: string;
}

export interface ActivityFeedProps {
  readonly entries: readonly ActivityEntry[];
}

/** Recent events, newest first, each reaching its subject. */
export function ActivityFeed({ entries }: ActivityFeedProps): ReactNode {
  return (
    <ol className="flex flex-col">
      {entries.map((entry) => {
        const Icon = KIND_ICON[entry.kind];
        return (
          <li
            key={entry.id}
            data-testid="activity-entry"
            data-kind={entry.kind}
            className="edge border-border border-x-0 border-t-0 last:border-b-0"
          >
            <a
              href={entry.href}
              className="flex items-start gap-3 py-3 motion-hover hover:opacity-90"
            >
              <span
                aria-hidden="true"
                className={cx(
                  'flex items-center justify-center size-5 shrink-0 rounded-2 edge',
                  OUTCOME_WELL[entry.outcome] ?? OUTCOME_WELL.neutral,
                )}
              >
                <Icon />
              </span>
              <span className="min-w-0 flex flex-col gap-1">
                <span className="text-small">{entry.title}</span>
                <span className="text-meta text-muted flex items-center gap-2 flex-wrap">
                  {/* The kind, in words. The icon well is the second carrier and
                      never the only one. */}
                  <span data-testid="activity-kind">{entry.kindLabel}</span>
                  {entry.detail === '' ? null : <span>· {entry.detail}</span>}
                  <time dateTime={entry.iso} title={entry.absolute}>
                    {entry.relative}
                  </time>
                </span>
              </span>
            </a>
          </li>
        );
      })}
    </ol>
  );
}
