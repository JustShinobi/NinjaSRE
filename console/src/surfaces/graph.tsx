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
/** How much vertical room one rank of a hierarchy takes. */
const RANK_HEIGHT = 110;

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

/** One box in a hierarchy, and whether it is currently doing anything. */
export interface HierarchyNode extends GraphNode {
  /** Off, in the deployment's configuration. Drawn faint rather than omitted. */
  readonly disabled?: boolean;
  /** Where a run starts. Exactly one node carries it. */
  readonly entryPoint?: boolean;
}

/** One rank of the hierarchy, drawn as a row. */
export interface HierarchyRank {
  readonly id: string;
  readonly label: string;
  readonly nodes: readonly HierarchyNode[];
  /**
   * Whether this rank's boxes run in order rather than side by side.
   *
   * The stages of an investigation do — resolve, intake, plan, gather,
   * diagnose, deliver — and drawn as a plain row fanning out of their parent,
   * nothing on the screen said which ran first. A reader was left to guess a
   * sequence from a picture that had deliberately not drawn one.
   */
  readonly sequence?: boolean;
}

export interface HierarchyGraphProps {
  readonly ranks: readonly HierarchyRank[];
  readonly labels: { readonly title: string };
}

/** How many boxes a rank draws before it stops drawing. */
export const RANK_BOUND = 8;

/** Minimum horizontal gap between two boxes drawn in the same rank. */
const NODE_GAP = 16;

/**
 * A hierarchy, top to bottom, in the same visual language as the neighbourhood.
 *
 * Extended here rather than written as a second component, for the reason a
 * second renderer is always the wrong answer: two pictures of "what is
 * connected to what", drawn with two sets of geometry, become two visual
 * languages an operator has to learn separately. The boxes, the rounding, the
 * stroke and the bound are the ones above; what changes is the axis.
 *
 * **State is on the node and never on colour alone.** A disabled specialist is
 * drawn faint *and* is marked in the list beside it, because a picture is not
 * the accessible copy of itself.
 */
export function HierarchyGraph({ ranks, labels }: HierarchyGraphProps): ReactNode {
  const drawn = ranks.map((rank) => ({
    ...rank,
    nodes: rank.nodes.slice(0, RANK_BOUND),
  }));
  // Sized to the ranks it has, with no floor. The floor was the neighbourhood
  // graph's own constant, and a two-rank hierarchy borrowing it reserved a
  // third more canvas than it drew on — which, because the element scales to
  // its container, became roughly three hundred pixels of void beneath the
  // boxes on a wide screen.
  const height = drawn.length * RANK_HEIGHT;
  // The widest rank decides how wide the picture is. A fixed canvas sized for
  // a handful of boxes per row draws a wider rank overlapping instead of
  // refusing to — which for an SVG box is one opaque rectangle sitting on
  // top of its neighbour's label, not a visible layout bug so much as a
  // vanished word.
  const widestRank = Math.max(1, ...drawn.map((rank) => rank.nodes.length));
  const width = Math.max(VIEW_WIDTH, widestRank * (NODE_WIDTH + NODE_GAP));
  const rowY = (index: number): number => index * RANK_HEIGHT + RANK_HEIGHT / 2;

  return (
    <svg
      role="img"
      aria-label={labels.title}
      viewBox={`0 0 ${String(width)} ${String(height)}`}
      data-testid="hierarchy"
      className="w-full h-auto"
      // Free to shrink on a narrow screen and never stretched beyond the size
      // it was drawn at. Stretched, a 720-wide drawing became a 2100-wide one
      // and carried its empty canvas up with it.
      style={{ maxInlineSize: `${String(width)}px` }}
    >
      <title>{labels.title}</title>
      <defs>
        <marker
          id="hierarchy-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M 0 1 L 9 5 L 0 9" className="fill-none stroke-border-strong" />
        </marker>
      </defs>
      <g className="stroke-border" strokeWidth={1} fill="none">
        {drawn
          .slice(1)
          .map((rank, index) =>
            rank.nodes.map((node) => (
              <line
                key={`edge-${node.id}`}
                x1={width / 2}
                y1={rowY(index) + NODE_HEIGHT / 2}
                x2={
                  acrossFor(rank.nodes.indexOf(node), rank.nodes.length, width) +
                  NODE_WIDTH / 2
                }
                y2={rowY(index + 1) - NODE_HEIGHT / 2}
              />
            )),
          )}
      </g>
      {/* The order, where a rank has one. Between the boxes rather than on
          them: the arrow is the claim that one follows another, and a glyph
          inside a box could only ever repeat the box's own name. */}
      <g className="stroke-border-strong" strokeWidth={1} fill="none">
        {drawn.flatMap((rank, index) =>
          rank.sequence !== true
            ? []
            : rank.nodes.slice(0, -1).map((node, position) => {
                const from =
                  acrossFor(position, rank.nodes.length, width) + NODE_WIDTH;
                const to = acrossFor(position + 1, rank.nodes.length, width);
                return (
                  <line
                    key={`sequence-${node.id}`}
                    data-testid="sequence-edge"
                    x1={from + 4}
                    y1={rowY(index)}
                    x2={to - 4}
                    y2={rowY(index)}
                    markerEnd="url(#hierarchy-arrow)"
                  />
                );
              }),
        )}
      </g>
      {drawn.map((rank, index) =>
        rank.nodes.map((node, position) => (
          <g
            key={node.id}
            data-testid="hierarchy-node"
            data-node={node.id}
            data-rank={rank.id}
            data-disabled={node.disabled === true ? 'true' : 'false'}
            data-entry={node.entryPoint === true ? 'true' : 'false'}
            className={node.disabled === true ? 'opacity-60' : undefined}
          >
            <Box
              node={node}
              x={acrossFor(position, rank.nodes.length, width)}
              y={rowY(index) - NODE_HEIGHT / 2}
            />
            {rank.sequence !== true ? null : (
              // Which one this is, so the order survives the picture being
              // read out of order — or read by something that cannot see the
              // arrows at all.
              <text
                data-testid={`sequence-ordinal-${node.id}`}
                x={acrossFor(position, rank.nodes.length, width) + NODE_WIDTH / 2}
                y={rowY(index) - NODE_HEIGHT / 2 - 6}
                textAnchor="middle"
                className="fill-muted text-micro"
              >
                {position + 1}
              </text>
            )}
          </g>
        )),
      )}
    </svg>
  );
}

/** Where the `index`th of `count` boxes sits across a picture `width` wide. */
function acrossFor(index: number, count: number, width: number): number {
  const step = width / (count + 1);
  return step * (index + 1) - NODE_WIDTH / 2;
}
