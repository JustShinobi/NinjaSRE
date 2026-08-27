import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { GuardianBand, type FlightRow } from '@/surfaces/guardian-band';

/**
 * The band that answers "is it working" before the page asks "does it need
 * you".
 *
 * The screen it replaces opened with a count of what the deployment had left
 * undone and put the guardian's own state in a card below the fold. For an
 * agent whose claim is that it investigates on its own, that is the wrong
 * first sentence — and the state that most needs saying is the quiet one,
 * because a guardian that has stopped looks exactly like a cluster with no
 * problems.
 */

function flight(over: Partial<FlightRow> = {}): FlightRow {
  return {
    id: 'run-1',
    headline: 'Redis container lxc/122 stopped on pve02',
    status: 'running',
    since: '41 seconds ago',
    href: '/runs/run-1',
    ...over,
  };
}

function band(over: Partial<Parameters<typeof GuardianBand>[0]> = {}): void {
  render(
    <GuardianBand
      locale="en"
      ready
      posture="propose-only"
      detectorsLive={24}
      detectorsTotal={26}
      watched={132}
      blocked={2}
      held={3}
      flights={[flight()]}
      {...over}
    />,
  );
}

describe('the guardian band', () => {
  it('says what it is watching with, not only that it is up', () => {
    band();

    expect(screen.getByTestId('guardian-band-meta')).toHaveTextContent(
      'propose-only · 24 of 26 detectors live · 132 resources watched',
    );
  });

  it('names the runs in flight rather than only counting them', () => {
    band({
      flights: [
        flight(),
        flight({ id: 'run-2', headline: 'DNS resolver failing probes' }),
      ],
    });

    const rows = screen.getAllByTestId('guardian-flight');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Redis container lxc/122 stopped on pve02');
    expect(screen.getByTestId('tally-flight')).toHaveTextContent('2');
  });

  it('says so plainly when nothing is being investigated', () => {
    // Not an empty list and not a zero with no sentence: "nothing is running"
    // and "the guardian has stopped" look identical to a reader, and only one
    // of them is fine.
    band({ flights: [] });

    expect(screen.getByTestId('guardian-band-idle')).toBeInTheDocument();
    expect(screen.queryAllByTestId('guardian-flight')).toHaveLength(0);
  });

  it('makes a guardian that is not ready unmissable', () => {
    band({ ready: false });

    const region = screen.getByTestId('guardian-band');
    expect(region.getAttribute('data-ready')).toBe('false');
    expect(region.className).toContain('border-danger');
    expect(screen.getByTestId('guardian-band-silent')).toHaveTextContent(
      'nothing is being watched',
    );
  });

  it('does not draw the live mark when nothing is live', () => {
    // The mark says the page is describing something happening now. On a
    // deployment that has stopped, an animation saying otherwise is the single
    // most misleading thing this band could do.
    const { container } = render(
      <GuardianBand
        locale="en"
        ready={false}
        posture="propose-only"
        detectorsLive={0}
        detectorsTotal={26}
        watched={132}
        blocked={0}
        held={0}
        flights={[]}
      />,
    );

    expect(container.querySelector('.pulse-live-ring')).toBeNull();
  });

  it('draws the live mark while it is running', () => {
    const { container } = render(
      <GuardianBand
        locale="en"
        ready
        posture="propose-only"
        detectorsLive={24}
        detectorsTotal={26}
        watched={132}
        blocked={0}
        held={0}
        flights={[]}
      />,
    );

    expect(container.querySelector('.pulse-live-ring')).not.toBeNull();
  });

  it('counts what the agent has picked up apart from what it is executing', () => {
    // Two facts, not one: an incident is held from the moment the agent takes
    // it, which can be before a run starts against it and stays true between
    // runs. Folding them into one number would make a page that is working
    // look idle in the gap.
    band({ held: 3, flights: [flight()] });

    expect(screen.getByTestId('tally-held')).toHaveTextContent('3');
    expect(screen.getByTestId('tally-flight')).toHaveTextContent('1');
  });

  it('says what it is watching with in words rather than as a third tally', () => {
    // The detector count is a sentence on the meta line an inch to the left.
    // Repeating it as a tally would be the same fact twice, competing.
    band();

    expect(screen.queryByTestId('tally-detectors')).toBeNull();
    expect(screen.getByTestId('guardian-band-meta')).toHaveTextContent('24 of 26');
  });

  it('leaves a count of zero quiet rather than colouring it', () => {
    // Colour is what says "act". A nought that needs nobody wearing the same
    // amber as a queue of four is how an operator learns to stop reading the
    // amber.
    band({ blocked: 0, held: 0, flights: [] });

    expect(screen.getByTestId('tally-blocked').className).toContain('text-muted');
    expect(screen.getByTestId('tally-blocked').className).not.toContain('text-warning');
  });

  it('colours what is waiting on a person once there is any', () => {
    band({ blocked: 3 });

    expect(screen.getByTestId('tally-blocked')).toHaveTextContent('3');
    expect(screen.getByTestId('tally-blocked').className).toContain('text-warning');
  });

  it('reaches each run in one click', () => {
    band();

    const row = within(screen.getByTestId('guardian-flight')).getByRole('link');
    expect(row.getAttribute('href')).toBe('/runs/run-1');
  });
});
