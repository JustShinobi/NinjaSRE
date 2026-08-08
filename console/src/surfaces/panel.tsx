'use client';

import type { ReactNode } from 'react';
import { Component, useCallback, useId, useState } from 'react';
import { useRouter } from 'next/navigation';

import { EmptyState, ErrorState } from '@/components/state';
import { Skeleton } from '@/components/feedback';
import { cx } from '@/design/cx';

/**
 * One region that fetches, with its own boundary, its own three states and its
 * own retry.
 *
 * A dashboard is six independent questions. One unanswerable question must not
 * blank the other five, and the only way to hold that is a boundary per region
 * rather than one per page — a page-level boundary is a page that goes dark
 * because a metrics source timed out.
 *
 * There are two ways a region fails and this handles both. A read that rejects
 * is caught where it is made and arrives here as `state="error"`; that is the
 * easy half. The half that takes a page down is a component that throws while
 * React is drawing it, and what contains that is the class boundary below.
 *
 * **The empty declaration is required.** Not "recommended": the type has no way
 * to spell a panel without one, so a region that can show nothing has to have
 * said what nothing means before it ships. The first live run of the previous
 * console showed eight empty tables behind a sign-in nobody could pass, and a
 * fresh deployment that looks broken is indistinguishable from one that is.
 */

export const PANEL_STATES = ['ready', 'loading', 'empty', 'error'] as const;

export type PanelState = (typeof PANEL_STATES)[number];

/** What would be here, and the one action that produces it. */
export interface PanelEmpty {
  readonly heading: string;
  readonly body: string;
  readonly actionLabel: string;
  /** Where the action goes. A navigation rather than a handler, so it is a link. */
  readonly href: string;
}

/** Every sentence the panel renders on its own behalf, from the catalogue. */
export interface PanelLabels {
  readonly loading: string;
  readonly errorHeading: string;
  /** What follows the dependency's name: what failed, and what still works. */
  readonly errorDetail: string;
  readonly retry: string;
}

interface BoundaryProps {
  readonly onError: () => void;
  readonly children: ReactNode;
}

interface BoundaryState {
  readonly failed: boolean;
}

/**
 * The one class component in the console.
 *
 * React offers no hook for this, and that is not an oversight: catching a render
 * error needs a lifecycle that runs *instead of* the render that threw, which is
 * not something a hook can express.
 */
class PanelBoundary extends Component<BoundaryProps, BoundaryState> {
  constructor(props: BoundaryProps) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  // The error itself is deliberately not rendered anywhere, and is not even
  // taken as a parameter here. A stack trace on an operations console is a paste
  // into a chat channel, and what it pastes is whatever the exception happened to
  // be holding — a URL with a query string in it, more often than not.
  override componentDidCatch(): void {
    this.props.onError();
  }

  override render(): ReactNode {
    return this.state.failed ? null : this.props.children;
  }
}

export interface PanelProps {
  /** Names the region, so a panel that fails can say which panel failed. */
  readonly title: string;
  readonly state: PanelState;
  readonly empty: PanelEmpty;
  readonly labels: PanelLabels;
  /** What this panel reads. Named, because "something went wrong" is not a report. */
  readonly dependency?: string;
  /** The icon in the empty well. Four parts, and this is the first of them. */
  readonly icon?: ReactNode;
  readonly action?: ReactNode;
  /** Whether the panel's body is the whole of it, with no chrome around it. */
  readonly bare?: boolean;
  readonly children?: ReactNode;
}

/** A titled region with a boundary, three declared states and a scoped retry. */
export function Panel({
  title,
  state,
  empty,
  labels,
  dependency = '',
  icon,
  action,
  bare = false,
  children,
}: PanelProps): ReactNode {
  const headingId = useId();
  const router = useRouter();
  const [threw, setThrew] = useState(false);
  const onError = useCallback(() => {
    setThrew(true);
  }, []);

  const retry = useCallback(() => {
    // The segment is refetched rather than the document reloaded. A panel that
    // retries by reloading the page throws away every other panel's answer to
    // recover one of them.
    setThrew(false);
    router.refresh();
  }, [router]);

  const resolved: PanelState = threw ? 'error' : state;

  return (
    <section
      data-testid="panel"
      data-state={resolved}
      aria-labelledby={headingId}
      className={cx(
        'flex flex-col min-w-0',
        bare ? '' : 'bg-raised edge border-border rounded-3 shadow-1',
      )}
    >
      <header
        className={cx(
          'flex items-center gap-2',
          bare ? 'pb-3' : 'px-4 py-3 edge border-border border-t-0 border-x-0',
        )}
      >
        <h3 id={headingId} className="text-strong">
          {title}
        </h3>
        {action === undefined ? null : <div className="ml-auto">{action}</div>}
      </header>
      <div className={cx('min-w-0', bare ? '' : 'p-4')}>
        {resolved === 'loading' ? (
          <div
            role="status"
            aria-label={labels.loading}
            className="flex flex-col gap-2"
          >
            {/* The skeleton reserves the box the content will land in, so the
                arrival of data moves nothing. */}
            <Skeleton width="title" />
            <Skeleton width="line" />
            <Skeleton width="line" />
          </div>
        ) : null}
        {resolved === 'empty' ? (
          <>
            <EmptyState
              heading={empty.heading}
              body={empty.body}
              {...(icon === undefined ? {} : { icon })}
              action={{
                label: empty.actionLabel,
                onSelect: () => {
                  window.location.assign(empty.href);
                },
              }}
            />
            {/* The same destination as a real link, for anything that reads
                edges rather than presses buttons. */}
            <a href={empty.href} className="sr-only" data-testid="way-back">
              {empty.actionLabel}
            </a>
          </>
        ) : null}
        {resolved === 'error' ? (
          <ErrorState
            heading={labels.errorHeading}
            dependency={dependency}
            detail={labels.errorDetail}
            retryLabel={labels.retry}
            onRetry={retry}
          />
        ) : null}
        {resolved === 'ready' ? (
          <PanelBoundary onError={onError}>{children}</PanelBoundary>
        ) : null}
      </div>
    </section>
  );
}
