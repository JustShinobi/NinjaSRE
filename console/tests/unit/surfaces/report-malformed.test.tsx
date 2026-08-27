import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Report } from '@/surfaces/report';

/**
 * What the renderer does with markdown nobody finished writing.
 *
 * The happy paths are covered by this file's sibling. These are the ones that
 * matter more: a report is a document a model wrote under time pressure and a
 * person never proof-read, so unclosed markers and half-typed links are the
 * normal case rather than the exotic one. Every case here asserts the same
 * shape of answer — the text survives, visible and inert, and nothing is
 * fabricated around it.
 *
 * A renderer that threw on any of these would take the whole run detail screen
 * down with it, which is a worse outcome than showing an asterisk.
 */

/** The rendered text of the report region, with whitespace normalised. */
function textOf(): string {
  return (screen.getByTestId('report').textContent || '').replace(/\s+/g, ' ').trim();
}

describe('Report, given markdown nobody finished', () => {
  it('keeps an unclosed code span as the characters that were typed', () => {
    render(<Report text={'the command is `systemctl restart'} />);
    expect(textOf()).toContain('`systemctl restart');
    expect(screen.queryByRole('code')).toBeNull();
  });

  it('keeps an unclosed strong marker literal', () => {
    render(<Report text={'the node is **down'} />);
    expect(textOf()).toContain('**down');
  });

  it('keeps an unclosed emphasis marker literal', () => {
    render(<Report text={'it looked *odd'} />);
    expect(textOf()).toContain('*odd');
  });

  it('keeps an empty emphasis pair literal rather than drawing an empty element', () => {
    render(<Report text={'nothing between these **** markers'} />);
    expect(textOf()).toContain('****');
  });

  it('keeps a link whose bracket never closes as text', () => {
    render(<Report text={'see [the runbook for this'} />);
    expect(textOf()).toContain('[the runbook for this');
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('keeps a label with no address after it as text', () => {
    render(<Report text={'see [the runbook] and nothing else'} />);
    expect(textOf()).toContain('[the runbook]');
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('keeps a link whose parenthesis never closes as text', () => {
    render(<Report text={'see [the runbook](https://example.test'} />);
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('follows nested parentheses to the address that closes them', () => {
    const address = ['https:', '', 'example.test', 'wiki', 'Failover_(database)'].join(
      '/',
    );
    render(<Report text={`see [the page](${address})`} />);
    expect(screen.getByRole('link', { name: /the page/ })).toHaveAttribute(
      'href',
      address,
    );
  });

  it('refuses a bare path, because this panel has nothing local to link to', () => {
    render(<Report text={'see [the settings](/settings/agent)'} />);
    expect(screen.queryByRole('link')).toBeNull();
    expect(textOf()).toContain('the settings');
  });

  it('refuses an address that is not a URL at all', () => {
    render(<Report text={'see [the thing](not a url)'} />);
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('keeps an exclamation mark that begins no image as text', () => {
    render(<Report text={'the disk filled up! it happened at noon'} />);
    expect(textOf()).toContain('filled up!');
  });

  it('keeps an unclosed image as text and still produces no image element', () => {
    render(<Report text={'![a graph of the memory'} />);
    expect(textOf()).toContain('![a graph of the memory');
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('renders an unclosed fence as a code block rather than losing the lines', () => {
    render(<Report text={'```\nsystemctl status\njournalctl -xe'} />);
    expect(textOf()).toContain('systemctl status');
    expect(textOf()).toContain('journalctl -xe');
  });

  it('treats a row of pipes with no separator beneath it as ordinary text', () => {
    render(<Report text={'vm | state | since\nnothing separates these'} />);
    expect(screen.queryByRole('table')).toBeNull();
    expect(textOf()).toContain('vm | state | since');
  });

  it('keeps a hash with no text after it as text, fabricating no empty heading', () => {
    render(<Report text={'#'} />);
    expect(screen.queryByRole('heading')).toBeNull();
  });

  it('draws nothing at all for an empty report', () => {
    render(<Report text={''} />);
    expect(textOf()).toBe('');
  });

  it('draws nothing at all for a report that is only blank lines', () => {
    render(<Report text={'\n\n   \n\n'} />);
    expect(textOf()).toBe('');
  });
});
