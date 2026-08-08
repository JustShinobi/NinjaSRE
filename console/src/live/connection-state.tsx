'use client';

import type { ReactNode } from 'react';

import { Button } from '@/components/action';
import { StatusDot } from '@/components/status';
import { message, type Locale } from '@/i18n/messages';
import type { ConnectionState } from './connection';

/**
 * Whether what is on screen is arriving, on the header of the thing it is
 * arriving into.
 *
 * The single most important claim this feature makes is the negative one: a
 * disconnected stream must never present itself as live. A transcript that
 * stopped updating looks exactly like a run that stopped producing events, and
 * an operator who cannot tell them apart will conclude the investigation is
 * stuck and go and do its work by hand.
 *
 * So the state is always rendered — including "connected", which costs a word
 * and buys the reader the knowledge that the absence of a word would have meant
 * something. And when the reconnection bound is reached it says so in a
 * sentence and offers the one thing left: doing it again, deliberately.
 */

const STATE_MESSAGE = {
  connecting: 'live.connection.connecting',
  connected: 'live.connection.connected',
  reconnecting: 'live.connection.reconnecting',
  idle: 'live.connection.idle',
  disconnected: 'live.connection.disconnected',
} as const;

export interface ConnectionBadgeProps {
  readonly locale: Locale;
  readonly state: ConnectionState;
  /** Whether the reconnection bound was reached, which is when a reload is offered. */
  readonly exhausted: boolean;
  readonly onReload: () => void;
}

export function ConnectionBadge({
  locale,
  state,
  exhausted,
  onReload,
}: ConnectionBadgeProps): ReactNode {
  return (
    <span
      data-testid="connection"
      data-connection={state}
      // Read by the suite as well as by a person: "is this live" has to be one
      // attribute rather than an inference from a colour.
      data-live={state === 'connected' ? 'true' : 'false'}
      className="flex items-center gap-2 text-meta text-muted"
    >
      {/* The shape carries the state and the word beside it says which. A
          standalone dot would name itself in the deployment's vocabulary rather
          than in the viewer's language, and say it twice. */}
      <StatusDot status={state} />
      <span>{message(locale, STATE_MESSAGE[state])}</span>
      {exhausted ? (
        <Button variant="quiet" data-testid="reconnect" onClick={onReload}>
          {message(locale, 'live.reload')}
        </Button>
      ) : null}
    </span>
  );
}

/** The sentence a stream that gave up leaves behind, where the events would be. */
export function StaleNotice({
  locale,
  shown,
}: {
  readonly locale: Locale;
  readonly shown: boolean;
}): ReactNode {
  if (!shown) return null;
  return (
    <p data-testid="stale" role="status" className="text-small text-danger">
      {message(locale, 'live.stale')}
    </p>
  );
}
