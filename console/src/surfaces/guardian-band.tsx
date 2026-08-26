import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { cx } from '@/design/cx';
import { formatNumber } from '@/i18n/format';
import { message, type Locale } from '@/i18n/messages';

/**
 * Whether the product is doing its job, as the first thing on the page.
 *
 * This screen used to open with a count of what it had left undone, and put
 * the guardian's own state in a small card in the right column, below the
 * fold. For an agent whose whole claim is that it investigates without you,
 * that is the wrong first sentence: an operator opening the console is asking
 * "is it working" before they are asking "does it need me", and the second
 * question is only frightening when the first has no answer.
 *
 * So: the state, what it is watching with, what it is holding right now, and
 * the runs in flight named rather than counted. Nothing here is a figure with
 * no list behind it — every number on the band is either a state or a count of
 * rows the reader can go and see.
 *
 * There is deliberately no progress bar on a run. Nothing the listing serves
 * says how far through a run is, and a bar drawn from an elapsed time is a
 * number this console would be inventing.
 */

/** One run the agent is working right now. */
export interface FlightRow {
  readonly id: string;
  /** The sentence naming the run. */
  readonly headline: string;
  readonly status: string;
  /** How long it has been running, already phrased. */
  readonly since: string;
  readonly href: string;
}

export interface GuardianBandProps {
  readonly locale: Locale;
  /** Whether the deployment reports itself ready to watch anything. */
  readonly ready: boolean;
  /** What it may do on its own, in the viewer's language. */
  readonly posture: string;
  readonly detectorsLive: number;
  readonly detectorsTotal: number;
  readonly watched: number;
  /** How many things are blocked on a person. */
  readonly blocked: number;
  /**
   * Incidents the agent has picked up.
   *
   * Not the same number as the runs in flight, and worth both: an incident is
   * held from the moment the agent takes it, which can be before a run starts
   * against it and stays true between runs.
   */
  readonly held: number;
  readonly flights: readonly FlightRow[];
}

interface TallyProps {
  readonly label: string;
  readonly value: string;
  readonly tone: string;
  readonly testId: string;
}

/** One count, and the word for what it counts. */
function Tally({ label, value, tone, testId }: TallyProps): ReactNode {
  return (
    <div className="flex flex-col items-end gap-1">
      <span
        data-testid={testId}
        className={cx('text-section tabular-nums leading-none', tone)}
      >
        {value}
      </span>
      <span className="text-micro text-muted">{label}</span>
    </div>
  );
}

/** The state of the agent, above everything the agent is watching. */
export function GuardianBand({
  locale,
  ready,
  posture,
  detectorsLive,
  detectorsTotal,
  watched,
  blocked,
  held,
  flights,
}: GuardianBandProps): ReactNode {
  return (
    <section
      data-testid="guardian-band"
      data-ready={ready ? 'true' : 'false'}
      aria-label={message(
        locale,
        ready ? 'dashboard.band.active' : 'dashboard.band.silent',
      )}
      className={cx(
        'bg-raised rounded-3 shadow-1 mb-5 overflow-hidden edge',
        // A guardian that has stopped looks exactly like a cluster with no
        // problems, so the one state that has to be unmissable is the quiet
        // one — and it is the border that says so, not a colour on the words.
        ready ? 'border-border' : 'border-danger',
      )}
    >
      <header className="flex items-center gap-3 flex-wrap px-4 py-3">
        <span className="flex items-center gap-2 text-strong">
          <span
            aria-hidden="true"
            className={cx(
              'pulse-live inline-block size-2 rounded-full',
              ready ? 'bg-accent' : 'bg-danger',
            )}
          >
            {ready ? <span className="pulse-live-ring" /> : null}
          </span>
          {message(locale, ready ? 'dashboard.band.active' : 'dashboard.band.silent')}
        </span>
        <span data-testid="guardian-band-meta" className="text-small text-muted">
          {message(locale, 'dashboard.band.meta', {
            posture,
            live: formatNumber(locale, detectorsLive),
            total: formatNumber(locale, detectorsTotal),
            watched: formatNumber(locale, watched),
          })}
        </span>
        <div className="ml-auto flex items-center gap-6">
          <Tally
            testId="tally-flight"
            label={message(locale, 'dashboard.band.flight')}
            value={formatNumber(locale, flights.length)}
            tone={flights.length > 0 ? 'text-info' : 'text-muted'}
          />
          <Tally
            testId="tally-held"
            label={message(locale, 'dashboard.band.held')}
            value={formatNumber(locale, held)}
            tone={held > 0 ? 'text-info' : 'text-muted'}
          />
          <Tally
            testId="tally-blocked"
            label={message(locale, 'dashboard.band.blocked')}
            value={formatNumber(locale, blocked)}
            tone={blocked > 0 ? 'text-warning' : 'text-muted'}
          />
        </div>
      </header>

      {ready ? null : (
        <p
          data-testid="guardian-band-silent"
          className="px-4 pb-3 text-small text-danger max-w-prose"
        >
          {message(locale, 'dashboard.band.silent.body')}
        </p>
      )}

      <div className="edge border-border border-x-0 border-b-0">
        {flights.length === 0 ? (
          <p
            data-testid="guardian-band-idle"
            className="px-4 py-3 text-small text-muted"
          >
            {message(locale, 'dashboard.band.idle')}
          </p>
        ) : (
          <ul className="flex flex-col">
            {flights.map((flight) => (
              <li
                key={flight.id}
                data-testid="guardian-flight"
                className="edge border-border border-x-0 border-b-0 first:border-t-0"
              >
                <a
                  href={flight.href}
                  className="flex items-center gap-3 px-4 py-3 motion-hover hover:bg-hover"
                >
                  <Badge status={flight.status} className="shrink-0" />
                  <span className="min-w-0 truncate text-small">{flight.headline}</span>
                  <span className="ml-auto shrink-0 text-meta text-muted tabular-nums">
                    {message(locale, 'dashboard.band.started', { since: flight.since })}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
