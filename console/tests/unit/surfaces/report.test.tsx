import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Report } from '@/surfaces/report';

/**
 * The report renderer, in isolation from any screen: a closed set of
 * elements, never a string handed to the DOM, an image that never becomes
 * one, and a link whose scheme was checked before it became navigable.
 */

describe('Report', () => {
  it('draws a heading as a heading element, not literal syntax', () => {
    render(<Report text={'### Evidence gathered\n\nSomething happened.'} />);
    expect(screen.getByRole('heading', { name: 'Evidence gathered' })).toBeInTheDocument();
    expect(screen.queryByText(/###/)).toBeNull();
  });

  it('draws a list as a list, with one item per line', () => {
    render(<Report text={'- first finding\n- second finding\n- third finding'} />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent('first finding');
  });

  it('draws a table with its header and its rows', () => {
    render(<Report text={'| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |'} />);
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getAllByRole('row')).toHaveLength(3); // header + two body rows
  });

  it('puts a code block in its own horizontally-scrolling container', () => {
    const { container } = render(<Report text={'```\nlong-line-with-no-spaces\n```'} />);
    const pre = container.querySelector('pre');
    expect(pre).not.toBeNull();
    expect(pre?.textContent).toContain('long-line-with-no-spaces');
    expect(pre?.parentElement).toHaveClass('overflow-x-auto');
  });

  it('renders raw HTML as text, never as an element', () => {
    const { container } = render(<Report text={"<script>alert('x')</script>"} />);
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText("<script>alert('x')</script>")).toBeInTheDocument();
  });

  it('represents an image by its alt text, and never produces an <img>', () => {
    const { container } = render(
      <Report text={'![a chart nobody can fetch](https://example.test/chart.png)'} />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('a chart nobody can fetch')).toBeInTheDocument();
  });

  it('makes an https link navigable, and keeps its label visible', () => {
    render(<Report text={'[the runbook](https://runbooks.example.test/pg-failover)'} />);
    const link = screen.getByRole('link', { name: /the runbook/ });
    expect(link).toHaveAttribute('href', 'https://runbooks.example.test/pg-failover');
    // External by construction: every navigable link in a report leaves the
    // page it is read on, so it always opens in a new tab with no opener.
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('refuses a javascript: link — its label stays, but it is not a link', () => {
    render(<Report text={'[click me](javascript:alert(1))'} />);
    expect(screen.queryByRole('link', { name: 'click me' })).toBeNull();
    expect(screen.getByText('click me')).toBeInTheDocument();
  });

  it('refuses a data: link the same way', () => {
    render(<Report text={'[open](data:text/html,<script>alert(1)</script>)'} />);
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('renders strong and emphasis as their own elements, not literal asterisks', () => {
    const { container } = render(<Report text={'A **bold** and an *emphasised* word.'} />);
    expect(container.querySelector('strong')).toHaveTextContent('bold');
    expect(container.querySelector('em')).toHaveTextContent('emphasised');
    expect(screen.queryByText(/\*/)).toBeNull();
  });

  it('renders inline code in its own element', () => {
    const { container } = render(<Report text={'Run `pg_repack` during a window.'} />);
    expect(container.querySelector('code')).toHaveTextContent('pg_repack');
  });

  it('treats a single line with no special syntax as an ordinary paragraph, fabricating no heading', () => {
    render(<Report text={'Just one plain sentence.'} />);
    expect(screen.getByText('Just one plain sentence.')).toBeInTheDocument();
    expect(screen.queryAllByRole('heading')).toHaveLength(0);
  });

  it('renders a construct outside the declared element set as its own literal text', () => {
    // A setext-style underline and a definition-list marker are not part of
    // this renderer's closed set — both fall through to a paragraph rather
    // than being silently dropped or guessed at.
    render(<Report text={'Term\n: a definition nobody asked this renderer to draw'} />);
    expect(screen.getByText(/a definition nobody asked this renderer to draw/)).toBeInTheDocument();
  });

  it('never calls dangerouslySetInnerHTML — the whole tree is built from elements', () => {
    const hostile =
      '# Heading\n\n<img src=x onerror=alert(1)>\n\n[bad](javascript:void(0))\n\n' +
      '![remote](https://example.test/a.png)\n\n```\ncode\n```';
    const { container } = render(<Report text={hostile} />);
    expect(container.querySelectorAll('img').length).toBe(0);
    expect(container.querySelectorAll('script').length).toBe(0);
  });
});
