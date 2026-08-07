import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CodeBlock, DataList, DiffView, Table, Timeline } from '@/components/data';

/**
 * The components that carry the data, and the three cases that break them.
 *
 * A table at 320 pixels with eight columns. A cell holding one unbroken
 * identifier longer than the column. A payload larger than anybody will read.
 * Each of those has a declared answer here rather than a scrollbar and a shrug.
 */

const COLUMNS = [
  { key: 'node', header: 'Node' },
  { key: 'status', header: 'Status' },
  { key: 'used', header: 'Used', numeric: true },
] as const;

const ROWS = [
  { id: '1', node: 'pve01', status: 'healthy', used: '41%' },
  { id: '2', node: 'pve02', status: 'degraded', used: '95%' },
];

describe('Table', () => {
  it('renders headers and rows, and names itself', () => {
    render(<Table caption="Storage" columns={COLUMNS} rows={ROWS} />);

    expect(screen.getByRole('table', { name: 'Storage' })).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader')).toHaveLength(3);
    expect(screen.getAllByRole('row')).toHaveLength(3);
  });

  it('labels every cell, which is what lets it stack below the breakpoint', () => {
    render(<Table caption="Storage" columns={COLUMNS} rows={ROWS} />);
    // Below 768 the table becomes stacked rows and each cell prints its own
    // header. The attribute is what the stylesheet reads; without it the
    // stacked form is a column of unlabelled values.
    expect(screen.getByText('pve01')).toHaveAttribute('data-label', 'Node');
  });

  it('lets a long single-token cell break rather than widening the table', () => {
    render(
      <Table
        caption="Storage"
        columns={COLUMNS}
        rows={[{ id: '1', node: 'a'.repeat(120), status: 'healthy', used: '1%' }]}
      />,
    );
    expect(screen.getByText('a'.repeat(120)).className).toContain('break-all');
  });

  it('sets numeric columns in tabular figures and aligns them right', () => {
    render(<Table caption="Storage" columns={COLUMNS} rows={ROWS} />);
    expect(screen.getByText('41%').className).toContain('tabular-nums');
    expect(screen.getByText('41%').className).toContain('text-right');
  });

  it('says what nothing means rather than showing an empty grid', () => {
    render(
      <Table
        caption="Storage"
        columns={COLUMNS}
        rows={[]}
        empty="No storage is watched."
      />,
    );
    expect(screen.getByText('No storage is watched.')).toBeInTheDocument();
  });
});

describe('DataList', () => {
  it('is a description list, so a name and its value stay associated', () => {
    render(
      <DataList
        items={[
          { term: 'Target', value: 'local-lvm on pve02' },
          { term: 'Rollback', value: 'Snapshot retained for 7 days' },
        ]}
      />,
    );

    expect(screen.getByText('Target').tagName).toBe('DT');
    expect(screen.getByText('local-lvm on pve02').tagName).toBe('DD');
  });

  it('sets an identifier in monospace, because identifiers are compared character by character', () => {
    render(
      <DataList items={[{ term: 'Volume', value: 'local-lvm', identifier: true }]} />,
    );
    expect(screen.getByText('local-lvm').className).toContain('font-mono');
  });

  it('declares an empty state', () => {
    render(<DataList items={[]} empty="Nothing was recorded." />);
    expect(screen.getByText('Nothing was recorded.')).toBeInTheDocument();
  });
});

describe('Timeline', () => {
  it('is a list, in the order the events happened', () => {
    render(
      <Timeline
        events={[
          {
            id: '1',
            kind: 'observed',
            actor: 'detector',
            at: '09:01',
            summary: 'Volume at 94%',
          },
          {
            id: '2',
            kind: 'decided',
            actor: 'model',
            at: '09:02',
            summary: 'Proposed a reclaim',
          },
        ]}
      />,
    );

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('Volume at 94%');
  });

  it('says a side effect happened rather than leaving it in the payload', () => {
    render(
      <Timeline
        events={[
          {
            id: '1',
            kind: 'acted',
            actor: 'runner',
            at: '09:03',
            summary: 'Removed 41 GiB',
            sideEffect: true,
          },
        ]}
      />,
    );
    expect(screen.getByText(/side effect/i)).toBeInTheDocument();
  });

  it('declares an empty state', () => {
    render(<Timeline events={[]} empty="Nothing has happened yet." />);
    expect(screen.getByText('Nothing has happened yet.')).toBeInTheDocument();
  });
});

describe('CodeBlock', () => {
  it('bounds a very large payload, and says what it bounded and by how much', () => {
    const payload = Array.from(
      { length: 4000 },
      (_, index) => `line ${String(index)}`,
    ).join('\n');
    render(<CodeBlock content={payload} label="Response" />);

    const bound = screen.getByTestId('bounded');
    expect(bound).toHaveTextContent(/4000 lines/);
    expect(bound).toHaveTextContent(/showing the first/i);
  });

  it('leaves a payload inside the bound alone', () => {
    render(<CodeBlock content={'one\ntwo'} label="Response" />);
    expect(screen.queryByTestId('bounded')).not.toBeInTheDocument();
  });

  it('is reachable by keyboard, because a scrollable region has to be', () => {
    render(<CodeBlock content={'one\ntwo'} label="Response" />);
    expect(screen.getByRole('region', { name: 'Response' })).toHaveAttribute(
      'tabindex',
      '0',
    );
  });
});

describe('DiffView', () => {
  it('marks each line as added, removed or unchanged in words as well as colour', () => {
    render(
      <DiffView
        before={'retention: 7\nquorum: 2'}
        after={'retention: 14\nquorum: 2'}
        label="Proposed configuration"
      />,
    );

    expect(screen.getByText('retention: 7').closest('tr')).toHaveAttribute(
      'data-change',
      'removed',
    );
    expect(screen.getByText('retention: 14').closest('tr')).toHaveAttribute(
      'data-change',
      'added',
    );
    expect(screen.getByText('quorum: 2').closest('tr')).toHaveAttribute(
      'data-change',
      'unchanged',
    );
  });

  it('says when two documents are the same rather than rendering nothing', () => {
    render(<DiffView before="same" after="same" label="Proposed configuration" />);
    expect(screen.getByText(/no difference/i)).toBeInTheDocument();
  });

  it('bounds a very large diff', () => {
    const before = Array.from({ length: 3000 }, (_, index) => `a${String(index)}`).join(
      '\n',
    );
    render(<DiffView before={before} after="b" label="Proposed configuration" />);
    expect(screen.getByTestId('bounded')).toHaveTextContent(/showing the first/i);
  });
});
