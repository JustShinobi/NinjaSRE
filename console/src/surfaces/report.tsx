import type { ReactNode } from 'react';

import { Link } from '@/components/action';

/**
 * The report an investigation wrote, drawn as a document instead of shown as
 * the text a model produced.
 *
 * No dependency parses this. The text a report carries came from a model that
 * read tool outputs, and a tool output can carry anything an alert, a log
 * line or an API response carries — so the property this module exists to
 * hold is structural rather than a list of things it happens to filter: it
 * never builds an HTML string and never hands one to the DOM, which means
 * there is no `dangerouslySetInnerHTML` call anywhere for hostile text to
 * reach. A block or an inline span this parser does not recognise is not
 * dropped and not guessed at — it is the text it already was, inside a
 * paragraph, the same way a literal `<script>` tag in the document is never
 * anything but the four-teen characters it is.
 *
 * The set of elements this can produce is closed and declared right here:
 * six heading levels, a paragraph, emphasis, strong, inline code, a fenced
 * code block, the two list kinds and their items, a block quote, a table and
 * its parts, a horizontal rule, and a link whose scheme this module checked
 * itself. An image never becomes an `<img>` — it becomes its own alt text,
 * which is what keeps "nothing this panel draws ever leaves the deployment"
 * true by construction rather than by a network rule elsewhere hoping to
 * catch what slipped through.
 */

// --- The inline tree ---------------------------------------------------------

type Inline =
  | { readonly kind: 'text'; readonly value: string }
  | { readonly kind: 'strong'; readonly children: readonly Inline[] }
  | { readonly kind: 'em'; readonly children: readonly Inline[] }
  | { readonly kind: 'code'; readonly value: string }
  | {
      readonly kind: 'link';
      readonly href: string;
      readonly children: readonly Inline[];
    }
  | { readonly kind: 'image'; readonly alt: string };

/** The only schemes a link in a report may navigate to. */
const ALLOWED_HREF_SCHEMES: readonly string[] = ['http:', 'https:', 'mailto:'];

/** Whether `href` is safe to make navigable. Anything else is rejected. */
function isAllowedHref(href: string): boolean {
  try {
    return ALLOWED_HREF_SCHEMES.includes(new URL(href).protocol);
  } catch {
    // Not a parseable absolute URL — including a bare path, since this panel
    // has nothing local for a report to link to.
    return false;
  }
}

/**
 * Parse one line's worth of text into an inline tree.
 *
 * A left-to-right scan, not a grammar: at every position it asks "does one of
 * the five inline forms start here", and falls back to plain text the moment
 * none of them do or a closing marker never arrives. An unterminated `**` is
 * therefore literal asterisks, not a guess at what the author meant.
 */
/**
 * The index of the `)` that closes the `(` at `openIndex`, honouring
 * parentheses nested inside — a href like `javascript:alert(1)` closes its
 * own paren before the link's does, and the first unmatched `indexOf(')')`
 * would stop there instead. `-1` when the source runs out first.
 */
function matchingParen(source: string, openIndex: number): number {
  let depth = 0;
  for (let index = openIndex; index < source.length; index += 1) {
    if (source[index] === '(') depth += 1;
    else if (source[index] === ')') {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  return -1;
}

function parseInline(source: string): Inline[] {
  const nodes: Inline[] = [];
  let cursor = 0;
  let buffer = '';

  function flush(): void {
    if (buffer !== '') {
      nodes.push({ kind: 'text', value: buffer });
      buffer = '';
    }
  }

  while (cursor < source.length) {
    const ch = source[cursor];

    if (ch === '`') {
      const end = source.indexOf('`', cursor + 1);
      if (end !== -1) {
        flush();
        nodes.push({ kind: 'code', value: source.slice(cursor + 1, end) });
        cursor = end + 1;
        continue;
      }
    }

    if ((ch === '*' || ch === '_') && source[cursor + 1] === ch) {
      const marker = source.slice(cursor, cursor + 2);
      const end = source.indexOf(marker, cursor + 2);
      if (end !== -1 && end > cursor + 2) {
        flush();
        nodes.push({
          kind: 'strong',
          children: parseInline(source.slice(cursor + 2, end)),
        });
        cursor = end + 2;
        continue;
      }
    }

    if (ch === '*' || ch === '_') {
      const end = source.indexOf(ch, cursor + 1);
      if (end !== -1 && end > cursor + 1) {
        flush();
        nodes.push({
          kind: 'em',
          children: parseInline(source.slice(cursor + 1, end)),
        });
        cursor = end + 1;
        continue;
      }
    }

    if (ch === '!' && source[cursor + 1] === '[') {
      const closeBracket = source.indexOf(']', cursor + 2);
      if (closeBracket !== -1 && source[closeBracket + 1] === '(') {
        const closeParen = matchingParen(source, closeBracket + 1);
        if (closeParen !== -1) {
          flush();
          nodes.push({ kind: 'image', alt: source.slice(cursor + 2, closeBracket) });
          cursor = closeParen + 1;
          continue;
        }
      }
    }

    if (ch === '[') {
      const closeBracket = source.indexOf(']', cursor + 1);
      if (closeBracket !== -1 && source[closeBracket + 1] === '(') {
        const closeParen = matchingParen(source, closeBracket + 1);
        if (closeParen !== -1) {
          const label = source.slice(cursor + 1, closeBracket);
          const href = source.slice(closeBracket + 2, closeParen);
          flush();
          if (isAllowedHref(href)) {
            nodes.push({ kind: 'link', href, children: parseInline(label) });
          } else {
            // A rejected scheme is never navigable, and never disappears
            // either — the operator still needs to see there was a link
            // there. Only its label is kept; the address it refused to
            // carry is not worth repeating next to it.
            nodes.push(...parseInline(label));
          }
          cursor = closeParen + 1;
          continue;
        }
      }
    }

    buffer += ch ?? '';
    cursor += 1;
  }
  flush();
  return nodes;
}

// --- The block tree -----------------------------------------------------------

type Block =
  | {
      readonly kind: 'heading';
      readonly level: 1 | 2 | 3 | 4 | 5 | 6;
      readonly inline: Inline[];
    }
  | { readonly kind: 'paragraph'; readonly inline: Inline[] }
  | {
      readonly kind: 'list';
      readonly ordered: boolean;
      readonly items: readonly Inline[][];
    }
  | {
      readonly kind: 'table';
      readonly header: readonly Inline[][];
      readonly rows: readonly Inline[][][];
    }
  | { readonly kind: 'code'; readonly text: string }
  | { readonly kind: 'blockquote'; readonly inline: Inline[] }
  | { readonly kind: 'hr' };

const HEADING = /^(#{1,6})\s+(.*)$/;
const FENCE = /^(`{3,}|~{3,})/;
const RULE = /^ {0,3}([-*_])( *\1){2,} *$/;
const TABLE_SEPARATOR = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;
const LIST_ITEM = /^\s*([-*+]|\d+\.)\s+(.*)$/;
const BLOCKQUOTE = /^>\s?(.*)$/;

/** One table row, cell text split on `|` and each cell parsed inline. */
function splitTableRow(line: string): Inline[][] {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  return trimmed.split('|').map((cell) => parseInline(cell.trim()));
}

/**
 * Parse a whole report into a block tree.
 *
 * Line-oriented, in the order CommonMark's own block grammar checks them:
 * a fence before a heading before a rule before a table before a quote
 * before a list, and a paragraph is whatever is left over — which is also
 * what keeps a raw `<script>` tag from matching anything more specific than
 * "a line of paragraph text".
 */
function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? '';

    if (line.trim() === '') {
      index += 1;
      continue;
    }

    const fence = FENCE.exec(line.trim());
    if (fence?.[1] !== undefined) {
      const marker = fence[1];
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !(lines[index] ?? '').trim().startsWith(marker)) {
        codeLines.push(lines[index] ?? '');
        index += 1;
      }
      index += 1; // the closing fence itself
      blocks.push({ kind: 'code', text: codeLines.join('\n') });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading?.[1] !== undefined && heading[2] !== undefined) {
      const level = heading[1].length as 1 | 2 | 3 | 4 | 5 | 6;
      blocks.push({ kind: 'heading', level, inline: parseInline(heading[2].trim()) });
      index += 1;
      continue;
    }

    if (RULE.test(line)) {
      blocks.push({ kind: 'hr' });
      index += 1;
      continue;
    }

    const next = lines[index + 1] ?? '';
    if (line.includes('|') && TABLE_SEPARATOR.test(next) && next.trim() !== '') {
      const header = splitTableRow(line);
      index += 2;
      const rows: Inline[][][] = [];
      while (
        index < lines.length &&
        (lines[index] ?? '').includes('|') &&
        (lines[index] ?? '').trim() !== ''
      ) {
        rows.push(splitTableRow(lines[index] ?? ''));
        index += 1;
      }
      blocks.push({ kind: 'table', header, rows });
      continue;
    }

    if (BLOCKQUOTE.test(line)) {
      const quoteLines: string[] = [];
      while (index < lines.length && BLOCKQUOTE.test(lines[index] ?? '')) {
        const captured = BLOCKQUOTE.exec(lines[index] ?? '');
        quoteLines.push(captured?.[1] ?? '');
        index += 1;
      }
      blocks.push({
        kind: 'blockquote',
        inline: parseInline(quoteLines.join(' ').trim()),
      });
      continue;
    }

    const listItem = LIST_ITEM.exec(line);
    if (listItem?.[1] !== undefined) {
      const ordered = /^\d+\.$/.test(listItem[1]);
      const items: Inline[][] = [];
      while (index < lines.length) {
        const match = LIST_ITEM.exec(lines[index] ?? '');
        if (match?.[2] === undefined) break;
        items.push(parseInline(match[2]));
        index += 1;
      }
      blocks.push({ kind: 'list', ordered, items });
      continue;
    }

    const paragraphLines: string[] = [];
    while (
      index < lines.length &&
      (lines[index] ?? '').trim() !== '' &&
      !HEADING.test(lines[index] ?? '') &&
      !FENCE.test((lines[index] ?? '').trim()) &&
      !RULE.test(lines[index] ?? '') &&
      !LIST_ITEM.test(lines[index] ?? '') &&
      !BLOCKQUOTE.test(lines[index] ?? '')
    ) {
      paragraphLines.push(lines[index] ?? '');
      index += 1;
    }
    blocks.push({
      kind: 'paragraph',
      inline: parseInline(paragraphLines.join(' ').trim()),
    });
  }
  return blocks;
}

// --- Rendering ------------------------------------------------------------

const HEADING_CLASS: Readonly<Record<1 | 2 | 3 | 4 | 5 | 6, string>> = {
  1: 'text-strong mt-6 mb-2 first:mt-0',
  2: 'text-strong mt-6 mb-2 first:mt-0',
  3: 'text-strong mt-5 mb-2 first:mt-0',
  4: 'text-small font-semibold mt-5 mb-1 first:mt-0',
  5: 'text-small font-semibold mt-4 mb-1 first:mt-0',
  6: 'text-small font-semibold text-muted mt-4 mb-1 first:mt-0',
};

function renderInline(nodes: readonly Inline[], keyPrefix: string): ReactNode {
  return nodes.map((node, index) => {
    const key = `${keyPrefix}-${String(index)}`;
    switch (node.kind) {
      case 'text':
        return node.value === '' ? null : node.value;
      case 'strong':
        return (
          <strong key={key} className="text-strong">
            {renderInline(node.children, key)}
          </strong>
        );
      case 'em':
        return <em key={key}>{renderInline(node.children, key)}</em>;
      case 'code':
        return (
          <code
            key={key}
            className="rounded-1 bg-surface-sunken px-1 font-mono text-meta"
          >
            {node.value}
          </code>
        );
      case 'link':
        return (
          <Link key={key} href={node.href} external>
            {renderInline(node.children, key)}
          </Link>
        );
      case 'image':
        // Never an `<img>` — the alt text is the whole representation, so no
        // request for this asset ever leaves the deployment.
        return (
          <span key={key} className="text-muted italic">
            {node.alt}
          </span>
        );
      default:
        return null;
    }
  });
}

function renderBlock(block: Block, key: string): ReactNode {
  switch (block.kind) {
    case 'heading': {
      const Heading = `h${String(block.level)}` as
        'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';
      return (
        <Heading key={key} className={HEADING_CLASS[block.level]}>
          {renderInline(block.inline, key)}
        </Heading>
      );
    }
    case 'paragraph':
      return (
        <p key={key} className="text-small">
          {renderInline(block.inline, key)}
        </p>
      );
    case 'list': {
      const List = block.ordered ? 'ol' : 'ul';
      return (
        <List
          key={key}
          className={
            block.ordered ? 'list-decimal pl-5 text-small' : 'list-disc pl-5 text-small'
          }
        >
          {block.items.map((item, index) => (
            <li key={`${key}-${String(index)}`}>
              {renderInline(item, `${key}-${String(index)}`)}
            </li>
          ))}
        </List>
      );
    }
    case 'table':
      return (
        <div key={key} className="w-full overflow-x-auto">
          <table className="w-full text-meta">
            <thead>
              <tr>
                {block.header.map((cell, index) => (
                  <th
                    key={`${key}-h-${String(index)}`}
                    scope="col"
                    className="text-left text-micro uppercase text-muted pb-1 pr-3"
                  >
                    {renderInline(cell, `${key}-h-${String(index)}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rowIndex) => (
                <tr key={`${key}-r-${String(rowIndex)}`}>
                  {row.map((cell, cellIndex) => (
                    <td
                      key={`${key}-r-${String(rowIndex)}-${String(cellIndex)}`}
                      className="py-1 pr-3"
                    >
                      {renderInline(
                        cell,
                        `${key}-r-${String(rowIndex)}-${String(cellIndex)}`,
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case 'code':
      return (
        <div
          key={key}
          className="w-full overflow-x-auto rounded-2 bg-surface-sunken p-3"
        >
          <pre className="text-meta font-mono whitespace-pre">{block.text}</pre>
        </div>
      );
    case 'blockquote':
      return (
        <blockquote
          key={key}
          className="edge border-border border-y-0 border-r-0 pl-3 text-small text-muted"
        >
          {renderInline(block.inline, key)}
        </blockquote>
      );
    case 'hr':
      return <hr key={key} className="border-border" />;
    default:
      return null;
  }
}

export interface ReportProps {
  /** The document as the deployment recorded it. */
  readonly text: string;
}

/**
 * The report, rendered as a document.
 *
 * A server component: the parse runs once, on the server, over text the
 * request already carried — no client state, no effect, nothing shipped to
 * the browser beyond the elements themselves. `max-h-prose` and its own
 * scroll keep a long report from being what the page's scroll budget
 * measures instead of the page.
 */
export function Report({ text }: ReportProps): ReactNode {
  const blocks = parseBlocks(text);
  return (
    <div
      data-testid="report"
      className="flex max-h-prose flex-col gap-3 overflow-y-auto"
    >
      {blocks.map((block, index) => renderBlock(block, `block-${String(index)}`))}
    </div>
  );
}
