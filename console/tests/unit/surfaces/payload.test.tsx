import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { BoundedPayload, boundOf, PAYLOAD_LINE_BOUND } from '@/surfaces/payload';

/**
 * A capability result of several megabytes, rendered without stalling the page.
 *
 * The property is not "it is short". It is that the reader is told what was
 * bounded and by how much, can ask for the rest, and can take the raw text away
 * — because the moment a result matters is the moment somebody is pasting it
 * into a ticket.
 */

const LABELS = {
  bounded: '1,918 lines in the payload; showing the first 24.',
  expand: 'Show the full payload',
  collapse: 'Bound it again',
  copy: 'Copy the raw payload',
  copied: 'Copied',
} as const;

function payload(lines: number): string {
  return Array.from({ length: lines }, (_, index) => `line ${String(index)}`).join(
    '\n',
  );
}

describe('what the bound is', () => {
  it('counts what there is and what is shown', () => {
    expect(boundOf(payload(1918))).toEqual({ total: 1918, shown: PAYLOAD_LINE_BOUND });
  });

  it('shows a short payload whole', () => {
    expect(boundOf(payload(3))).toEqual({ total: 3, shown: 3 });
  });

  it('counts nothing as nothing rather than as one empty line', () => {
    expect(boundOf('')).toEqual({ total: 0, shown: 0 });
  });
});

describe('a payload larger than anybody will read', () => {
  it('draws the bound rather than the whole of it', () => {
    render(
      <BoundedPayload
        label="storage pressure"
        content={payload(1918)}
        labels={LABELS}
      />,
    );

    const shown = screen.getByTestId('payload').textContent;
    expect(shown.split('\n')).toHaveLength(PAYLOAD_LINE_BOUND);
  });

  it('says what it bounded and by how much', () => {
    render(
      <BoundedPayload
        label="storage pressure"
        content={payload(1918)}
        labels={LABELS}
      />,
    );

    expect(screen.getByTestId('bounded')).toHaveTextContent(LABELS.bounded);
  });

  it('opens to the whole payload and closes again', async () => {
    render(
      <BoundedPayload label="storage pressure" content={payload(50)} labels={LABELS} />,
    );

    await userEvent.click(screen.getByRole('button', { name: LABELS.expand }));
    expect(screen.getByTestId('payload').textContent.split('\n')).toHaveLength(50);

    await userEvent.click(screen.getByRole('button', { name: LABELS.collapse }));
    expect(screen.getByTestId('payload').textContent.split('\n')).toHaveLength(
      PAYLOAD_LINE_BOUND,
    );
  });

  it('hands over the raw text rather than the drawn one', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    render(
      <BoundedPayload label="storage pressure" content={payload(50)} labels={LABELS} />,
    );
    await userEvent.click(screen.getByRole('button', { name: LABELS.copy }));

    expect(writeText).toHaveBeenCalledWith(payload(50));
    expect(
      await screen.findByRole('button', { name: LABELS.copied }),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});

describe('a payload that fits', () => {
  it('says nothing about a bound it did not apply', () => {
    render(<BoundedPayload label="quorum" content={payload(3)} labels={LABELS} />);

    expect(screen.queryByTestId('bounded')).toBeNull();
    expect(screen.queryByRole('button', { name: LABELS.expand })).toBeNull();
  });

  it('is still a region a keyboard can reach and read', () => {
    render(<BoundedPayload label="quorum" content={payload(3)} labels={LABELS} />);

    expect(screen.getByRole('region', { name: 'quorum' })).toHaveAttribute(
      'tabindex',
      '0',
    );
  });
});
