import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { HierarchyGraph, type HierarchyRank } from '@/surfaces/graph';

/**
 * The picture is sized to what it draws, and says which way a rank runs.
 *
 * Two faults, one canvas. The height was floored at a constant sized for the
 * neighbourhood graph, so a hierarchy of two ranks reserved a third more room
 * than it used — and because the element scales to its container, that floor
 * became roughly three hundred pixels of void under the boxes on a wide screen.
 *
 * The second is about meaning rather than space. A rank whose boxes run in
 * order — the stages of an investigation do — was drawn as an unordered row
 * fanning out of its parent, so nothing on the screen said which ran first.
 */

function ranksOf(stageCount: number, sequence: boolean): readonly HierarchyRank[] {
  return [
    {
      id: 'orchestrator',
      label: 'Orchestrator',
      nodes: [
        {
          id: 'orchestrator',
          name: 'Orchestrator',
          kind: 'orchestrator',
          href: '#x',
          entryPoint: true,
        },
      ],
    },
    {
      id: 'stages',
      label: 'Stages',
      sequence,
      nodes: Array.from({ length: stageCount }, (_, index) => ({
        id: `stage-${String(index)}`,
        name: `stage ${String(index)}`,
        kind: 'stage',
        href: '#x',
      })),
    },
  ];
}

const LABELS = { title: 'The stages an investigation runs' };

describe('a hierarchy is sized to its own ranks', () => {
  it('reserves no room for a rank it does not draw', () => {
    render(<HierarchyGraph ranks={ranksOf(6, false)} labels={LABELS} />);

    const box = screen.getByTestId('hierarchy').getAttribute('viewBox') ?? '';
    const height = Number(box.split(' ')[3]);
    // Two ranks at one rank's height each, and not the neighbourhood graph's
    // constant — which is what left a third of the canvas empty.
    expect(height).toBe(220);
  });

  it('never scales itself up past the size it was drawn at', () => {
    render(<HierarchyGraph ranks={ranksOf(6, false)} labels={LABELS} />);

    // Free to shrink on a narrow screen; never stretched across a wide one,
    // where a 720-wide drawing became a 2100-wide one and took its empty
    // canvas with it.
    expect(screen.getByTestId('hierarchy').getAttribute('style')).toContain(
      'max-inline-size',
    );
  });
});

describe('a rank that runs in order says so', () => {
  it('draws an arrow between each pair of boxes and numbers them', () => {
    render(<HierarchyGraph ranks={ranksOf(6, true)} labels={LABELS} />);

    // Five arrows for six stages: the connections between them, not one each.
    expect(screen.getAllByTestId('sequence-edge')).toHaveLength(5);
    const first = screen.getByTestId('sequence-ordinal-stage-0');
    expect(first).toHaveTextContent('1');
  });

  it('draws neither for a rank that does not run in order', () => {
    render(<HierarchyGraph ranks={ranksOf(6, false)} labels={LABELS} />);

    expect(screen.queryAllByTestId('sequence-edge')).toHaveLength(0);
    expect(screen.queryByTestId('sequence-ordinal-stage-0')).toBeNull();
  });
});
