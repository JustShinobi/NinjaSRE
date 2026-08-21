import type { ReactNode } from 'react';

/**
 * A service and its neighbourhood, as a picture and as a list.
 *
 * The layout is computed once from the data rather than simulated: three
 * columns, dependencies on the left, the subject in the middle, dependents on
 * the right, each column spread evenly down its own height. A force simulation
 * would look better and would cost a frame budget per data change to draw
 * something whose only job is to say what is connected to what.
 *
 * **The rendered neighbourhood is bounded and the list is not.** A node with two
 * hundred dependents drawn as two hundred boxes is a picture nobody can read and
 * a document nobody can scroll; the graph shows the first `bound` and says how
 * many there are, and the list below it has every one. That is the accessible
 * equivalent as well as the scalable one — the same facts, in a form a screen
 * reader can walk and a keyboard can tab through.
 */

/** How many neighbours a side of the graph draws before it stops drawing. */
export const NEIGHBOUR_BOUND = 12;

/** The picture's own geometry. Not spacing steps: this is a drawing, not a layout. */
const VIEW_WIDTH = 720;
const VIEW_HEIGHT = 360;
const NODE_WIDTH = 168;
const NODE_HEIGHT = 34;

export interface GraphNode {
  readonly id: string;
  readonly name: string;
  readonly kind: string;
  readonly href: string;
}

export interface DependencyGraphProps {
  readonly subject: GraphNode;
  readonly dependencies: readonly GraphNode[];
  readonly dependents: readonly GraphNode[];
  readonly labels: {
    readonly title: string;
    readonly dependencies: string;
    readonly dependents: string;
  };
}

/** Where the `index`th of `count` boxes sits down the picture. */
function offsetFor(index: number, count: number): number {
  const step = VIEW_HEIGHT / (count + 1);
  return step * (index + 1) - NODE_HEIGHT / 2;
}

function Box({
  node,
  x,
  y,
}: {
  readonly node: GraphNode;
  readonly x: number;
  readonly y: number;
}): ReactNode {
  return (
    <a href={node.href} data-testid="graph-node" data-node={node.id}>
      <rect
        x={x}
        y={y}
        width={NODE_WIDTH}
        height={NODE_HEIGHT}
        rx={6}
        className="fill-raised stroke-border-strong"
      />
      <text
        x={x + NODE_WIDTH / 2}
        y={y + NODE_HEIGHT / 2 + 4}
        textAnchor="middle"
        className="fill-text text-meta"
      >
        {node.name}
      </text>
    </a>
  );
}

/** The picture. The list beside it is the screen's job, not this component's. */
export function DependencyGraph({
  subject,
  dependencies,
  dependents,
  labels,
}: DependencyGraphProps): ReactNode {
  const left = dependencies.slice(0, NEIGHBOUR_BOUND);
  const right = dependents.slice(0, NEIGHBOUR_BOUND);
  const centreY = VIEW_HEIGHT / 2 - NODE_HEIGHT / 2;
  const centreX = VIEW_WIDTH / 2 - NODE_WIDTH / 2;
  const rightX = VIEW_WIDTH - NODE_WIDTH;

  return (
    <svg
      role="img"
      aria-label={labels.title}
      viewBox={`0 0 ${String(VIEW_WIDTH)} ${String(VIEW_HEIGHT)}`}
      data-testid="graph"
      className="w-full h-auto"
    >
      <title>{labels.title}</title>
      <g className="stroke-border" strokeWidth={1} fill="none">
        {left.map((node, index) => (
          <line
            key={`in-${node.id}`}
            x1={NODE_WIDTH}
            y1={offsetFor(index, left.length) + NODE_HEIGHT / 2}
            x2={centreX}
            y2={centreY + NODE_HEIGHT / 2}
          />
        ))}
        {right.map((node, index) => (
          <line
            key={`out-${node.id}`}
            x1={centreX + NODE_WIDTH}
            y1={centreY + NODE_HEIGHT / 2}
            x2={rightX}
            y2={offsetFor(index, right.length) + NODE_HEIGHT / 2}
          />
        ))}
      </g>
      {left.map((node, index) => (
        <Box key={node.id} node={node} x={0} y={offsetFor(index, left.length)} />
      ))}
      <g data-testid="graph-subject">
        <rect
          x={centreX}
          y={centreY}
          width={NODE_WIDTH}
          height={NODE_HEIGHT}
          rx={6}
          className="fill-accent-bg stroke-accent"
        />
        <text
          x={centreX + NODE_WIDTH / 2}
          y={centreY + NODE_HEIGHT / 2 + 4}
          textAnchor="middle"
          className="fill-accent text-meta"
        >
          {subject.name}
        </text>
      </g>
      {right.map((node, index) => (
        <Box key={node.id} node={node} x={rightX} y={offsetFor(index, right.length)} />
      ))}
    </svg>
  );
}
