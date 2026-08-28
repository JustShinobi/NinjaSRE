import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  AccountStateChip,
  Badge,
  BridgedServerStateChip,
  CapabilityAvailabilityChip,
  CheckChip,
  DetectorStateChip,
  PrincipalKindChip,
  ResolvedChip,
  SideEffectChip,
  SpecialistStateChip,
  StatusDot,
  TokenGroupStateChip,
} from '@/components/status';
import {
  RESOURCE_STATUSES,
  RUN_STATUSES,
  SHAPES,
  type Shape,
  statusPresentation,
} from '@/design/status';
import { SEMANTIC_ROLES, type SemanticRole } from '@/design/tokens';

/**
 * Status, shown twice: once in colour and once in something else.
 *
 * These two components are where the "never colour alone" requirement is
 * actually kept, so the tests are about absence as much as presence — a badge
 * with no text and a dot with no shape both fail here, because both are a
 * status that some viewers do not have.
 */

const EVERY_STATUS = [...RUN_STATUSES, ...RESOURCE_STATUSES, 'invented-by-a-provider'];

describe('Badge', () => {
  it('always says the status in words', () => {
    for (const status of EVERY_STATUS) {
      const { unmount } = render(<Badge status={status} />);
      expect(screen.getByText(statusPresentation(status).label)).toBeInTheDocument();
      unmount();
    }
  });

  it('always carries a shape as well as a colour', () => {
    for (const status of EVERY_STATUS) {
      const { container, unmount } = render(<Badge status={status} />);
      const shape = container.querySelector('[data-shape]');
      expect(shape, status).not.toBeNull();
      expect(shape).toHaveAttribute('data-shape', statusPresentation(status).shape);
      unmount();
    }
  });

  it('gives a status nobody declared its raw text and the neutral role', () => {
    const { container } = render(<Badge status="quiesced" />);
    expect(screen.getByText('quiesced')).toBeInTheDocument();
    expect(container.querySelector('[data-role]')).toHaveAttribute(
      'data-role',
      'neutral',
    );
  });

  it('says nothing was reported rather than rendering an empty chip', () => {
    render(<Badge status="" />);
    expect(screen.getByText('unreported')).toBeInTheDocument();
  });
});

describe('StatusDot', () => {
  it('is never announced on its own, because it is never on its own', () => {
    render(<StatusDot status="healthy" />);
    // Decorative: the label beside it is what a screen reader says. A dot that
    // announced itself would say "healthy" twice on every row.
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('carries an accessible name when a caller says it stands alone', () => {
    render(<StatusDot status="degraded" standalone />);
    expect(screen.getByRole('img', { name: /degraded/ })).toBeInTheDocument();
  });

  it('draws a different shape for each of the two neutral states', () => {
    const { container: unknown, unmount } = render(<StatusDot status="unknown" />);
    const first = unknown.firstElementChild?.getAttribute('data-shape');
    unmount();
    const { container: stale } = render(<StatusDot status="stale" />);
    expect(stale.firstElementChild?.getAttribute('data-shape')).not.toBe(first);
  });
});

describe('CheckChip', () => {
  // Every state the preflight actually reports, each with its own role and
  // shape — never the five-word credential vocabulary, which is a different
  // claim about a different kind of thing.
  const CASES: readonly {
    readonly status: 'passed' | 'degraded' | 'failed' | 'skipped';
    readonly role: string;
    readonly shape: string;
  }[] = [
    { status: 'passed', role: 'success', shape: 'filled-circle' },
    { status: 'degraded', role: 'warning', shape: 'triangle' },
    { status: 'failed', role: 'danger', shape: 'square' },
    { status: 'skipped', role: 'neutral', shape: 'dash' },
  ];

  it.each(CASES)(
    'draws $status with the $role role and the $shape shape',
    ({ status, role, shape }) => {
      const { container } = render(<CheckChip name="Tool calling" status={status} />);
      const chip = container.firstElementChild;
      expect(chip).toHaveAttribute('data-role', role);
      expect(chip).toHaveAttribute('data-check-status', status);
      expect(chip?.querySelector('[data-shape]')).toHaveAttribute('data-shape', shape);
    },
  );

  it('names the check, never a canonical credential word', () => {
    render(<CheckChip name="Structured output" status="failed" />);
    expect(screen.getByText('Structured output')).toBeInTheDocument();
  });
});

describe('PrincipalKindChip', () => {
  it('names a service account by what it is, never the transport word', () => {
    render(<PrincipalKindChip locale="en" kind="service_account" />);
    expect(screen.getByText('Service account')).toBeInTheDocument();
    expect(screen.queryByText('SERVICE_ACCOUNT')).toBeNull();
    expect(screen.queryByText('service_account')).toBeNull();
  });

  it('names a person by what they are, never the raw record kind', () => {
    render(<PrincipalKindChip locale="en" kind="user" />);
    expect(screen.getByText('Person')).toBeInTheDocument();
    expect(screen.queryByText('user')).toBeNull();
  });

  it('shows a kind this catalogue has never heard of rather than hiding it', () => {
    render(<PrincipalKindChip locale="en" kind="robot" />);
    expect(screen.getByText('robot')).toBeInTheDocument();
  });
});

describe('AccountStateChip', () => {
  it('says a live account is active, never the health word healthy', () => {
    render(<AccountStateChip locale="en" active />);
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.queryByText('healthy')).toBeNull();
    expect(screen.queryByText(/HEALTHY/i)).toBeNull();
  });

  it('says a disabled account is suspended, never disabled', () => {
    render(<AccountStateChip locale="en" active={false} />);
    expect(screen.getByText('Suspended')).toBeInTheDocument();
    expect(screen.queryByText('disabled')).toBeNull();
  });
});

describe('TokenGroupStateChip', () => {
  it('says a group with a recorded last use is in use, never healthy', () => {
    render(<TokenGroupStateChip locale="en" everUsed />);
    expect(screen.getByText('In use')).toBeInTheDocument();
    expect(screen.queryByText(/HEALTHY/i)).toBeNull();
  });

  it('says a group with no recorded use was never used', () => {
    render(<TokenGroupStateChip locale="en" everUsed={false} />);
    expect(screen.getByText('Never used')).toBeInTheDocument();
  });
});

describe('DetectorStateChip', () => {
  it('says a detector that evaluates is enabled, never the health word healthy', () => {
    render(<DetectorStateChip locale="en" enabled />);
    expect(screen.getByText('Enabled')).toBeInTheDocument();
    expect(screen.queryByText('healthy')).toBeNull();
    expect(screen.queryByText(/HEALTHY/i)).toBeNull();
  });

  // No fixture scenario carries a switched-off detector — every detector this
  // deployment ships is enabled — so this branch has no natural red to catch
  // it and is proved here instead.
  it('says a detector an operator turned off is disabled', () => {
    render(<DetectorStateChip locale="en" enabled={false} />);
    expect(screen.getByText('Disabled')).toBeInTheDocument();
  });
});

describe('SpecialistStateChip', () => {
  it('says a specialist the configuration still dispatches is enabled, never healthy', () => {
    render(<SpecialistStateChip locale="en" enabled />);
    expect(screen.getByText('Enabled')).toBeInTheDocument();
    expect(screen.queryByText(/HEALTHY/i)).toBeNull();
  });

  it('says a specialist the configuration switched off is disabled, never paused', () => {
    render(<SpecialistStateChip locale="en" enabled={false} />);
    expect(screen.getByText('Disabled')).toBeInTheDocument();
    expect(screen.queryByText('paused')).toBeNull();
  });
});

describe('BridgedServerStateChip', () => {
  it('says a server the configuration still registers is enabled, never healthy', () => {
    render(<BridgedServerStateChip locale="en" enabled />);
    expect(screen.getByText('Enabled')).toBeInTheDocument();
    expect(screen.queryByText(/HEALTHY/i)).toBeNull();
  });

  // No fixture scenario carries a bridged server switched off — the one
  // fixture server is enabled — so this branch has no natural red to catch
  // it and is proved here instead.
  it('says a server an operator turned off is disabled, never paused', () => {
    render(<BridgedServerStateChip locale="en" enabled={false} />);
    expect(screen.getByText('Disabled')).toBeInTheDocument();
    expect(screen.queryByText('paused')).toBeNull();
  });
});

describe('CapabilityAvailabilityChip', () => {
  it('says an available tool is enabled, never the health word healthy', () => {
    render(<CapabilityAvailabilityChip locale="en" available />);
    expect(screen.getByText('Enabled')).toBeInTheDocument();
    expect(screen.queryByText('healthy')).toBeNull();
    expect(screen.queryByText(/HEALTHY/i)).toBeNull();
  });

  // The capability table never renders this with `available={false}` — a
  // blocked tool shows the reason it is blocked instead of this chip (see
  // `capability-browser.tsx`) — so this branch has no render path to catch
  // it and is proved here instead.
  it('says an unavailable tool is disabled', () => {
    render(<CapabilityAvailabilityChip locale="en" available={false} />);
    expect(screen.getByText('Disabled')).toBeInTheDocument();
  });
});

/**
 * A side-effect level the catalogue invented still says its own word.
 *
 * The five levels are a closed set this console carries sentences for, which is
 * why they get a translated chip rather than the raw-status badge. A capability
 * declaring a sixth is a deployment one version ahead, not a fault — so it
 * falls through to the badge, which is exactly the case that badge exists for.
 */
describe('a side-effect level outside the closed set', () => {
  it('falls through to the badge rather than rendering blank', () => {
    render(<SideEffectChip locale="en" level="cataclysmic" />);

    expect(screen.getByText(/cataclysmic/i)).toBeInTheDocument();
  });

  it('carries the sentence as its explanation for a level it knows', () => {
    render(<SideEffectChip locale="en" level="write_reversible" />);

    const chip = screen.getByTestId('capability-side-effect');
    expect(chip).toHaveTextContent('Writes, reversible');
    expect(chip.getAttribute('title')).toMatch(/can be undone/i);
  });
});

describe('the shape, as the stylesheet resolves it rather than as it was meant', () => {
  /**
   * A hollow shape has to survive the cascade, not only the class list.
   *
   * It used to be drawn by putting `bg-transparent` in the shape's classes and
   * leaving the role's `bg-{role}` beside it, trusting the first to win. The
   * cascade does not read the order of the class attribute; it reads the order
   * of the stylesheet, which Tailwind writes alphabetically. So `bg-transparent`
   * beat `bg-danger`, `bg-info`, `bg-neutral` and `bg-success` — and lost to
   * `bg-warning`. Every warning hollow circle rendered solid, which drew
   * `pending` and `propose` as the same solid thirteen-pixel disc as
   * `completed`, separated from it by hue alone. That is precisely the failure
   * the second carrier exists to prevent, and it shipped while a test
   * asserting `bg-transparent` was present passed on every run.
   *
   * So what is asserted here is the absence of a contest: one background
   * utility on the mark, never two. An invariant over the composition cannot be
   * won or lost by an ordering, which is why it holds where the intention did
   * not — and why it will still hold for a role named after `transparent`.
   */
  const backgrounds = (mark: Element): readonly string[] =>
    [...mark.classList].filter((name) => name.startsWith('bg-'));

  function markOf(role: SemanticRole, shape: Shape): Element {
    const { container } = render(
      <ResolvedChip role={role} shape={shape} label="a word" testId="probe" />,
    );
    const mark = container.querySelector('[data-shape]');
    if (mark === null) throw new Error(`${shape} drew no mark`);
    return mark;
  }

  it.each(SHAPES)('puts one background utility on a %s, never two', (shape) => {
    for (const role of SEMANTIC_ROLES) {
      expect(backgrounds(markOf(role, shape)), `${shape} / ${role}`).toHaveLength(1);
    }
  });

  it('leaves a hollow circle without the fill it is meant to be missing', () => {
    for (const role of SEMANTIC_ROLES) {
      const classes = [...markOf(role, 'hollow-circle').classList];
      expect(classes, role).not.toContain(`bg-${role}`);
      expect(classes, role).toContain('bg-transparent');
    }
  });

  it('keeps a filled circle filled, in every role', () => {
    for (const role of SEMANTIC_ROLES) {
      expect([...markOf(role, 'filled-circle').classList], role).toContain(
        `bg-${role}`,
      );
    }
  });

  /**
   * A pinned, independent copy of the shape mark's own class tables, as they
   * stood before this feature's chip-outline change — not read from
   * `status.tsx`, which is what makes this a characterization rather than a
   * tautology that would pass however the source changed. The chip outline
   * this feature adds lives in `ROLE_SKIN`, which only ever reaches the
   * *outer* chip; none of the three tables below is any part of that change,
   * and this block is the proof that holds for both before and after it.
   */
  const PINNED_SHAPE_CLASS: Readonly<Record<Shape, string>> = {
    'filled-circle': 'icon-inline rounded-full',
    'hollow-circle': 'icon-inline rounded-full edge-ring',
    'dimmed-circle': 'icon-inline rounded-full opacity-50',
    square: 'icon-inline',
    'rotated-square': 'icon-inline rotate-45',
    triangle: 'icon-inline clip-triangle',
    dash: 'icon-inline h-0 edge-ring rounded-full',
  };
  const PINNED_ROLE_FILL: Readonly<Record<SemanticRole, string>> = {
    success: 'bg-success border-success',
    warning: 'bg-warning border-warning',
    danger: 'bg-danger border-danger',
    info: 'bg-info border-info',
    neutral: 'bg-neutral border-neutral',
  };
  const PINNED_ROLE_RING: Readonly<Record<SemanticRole, string>> = {
    success: 'bg-transparent border-success',
    warning: 'bg-transparent border-warning',
    danger: 'bg-transparent border-danger',
    info: 'bg-transparent border-info',
    neutral: 'bg-transparent border-neutral',
  };
  const PINNED_HOLLOW_SHAPES: readonly Shape[] = ['hollow-circle'];

  it.each(SHAPES)(
    'the %s mark carries exactly its pinned classes, for every role — before and after the chip outline',
    (shape) => {
      for (const role of SEMANTIC_ROLES) {
        const expected = [
          ...PINNED_SHAPE_CLASS[shape].split(' '),
          ...(PINNED_HOLLOW_SHAPES.includes(shape)
            ? PINNED_ROLE_RING[role]
            : PINNED_ROLE_FILL[role]
          ).split(' '),
          'edge',
          'inline-block',
          'shrink-0',
        ].sort();
        expect([...markOf(role, shape).classList].sort(), `${shape}/${role}`).toEqual(
          expected,
        );
      }
    },
  );
});

describe('every status chip carries a role-coloured 1px border on its tint', () => {
  /**
   * FR-017's claim, confirmed red before `ROLE_SKIN` gains the border: today
   * only `neutral` carries any boundary at all (`border-border`, a generic
   * token rather than its own role's), and the other four roles carry none.
   * After the change all five carry `edge` plus `border-{role}` — their own
   * role's colour, `neutral` included, which is why this checks `neutral`
   * exactly like the other four rather than exempting it.
   */
  it.each(SEMANTIC_ROLES)(
    'the %s chip carries `edge` and its own border colour',
    (role) => {
      const { container } = render(
        <ResolvedChip
          role={role}
          shape="filled-circle"
          label="a word"
          testId="probe-skin"
        />,
      );
      const chip = container.querySelector('[data-testid="probe-skin"]');
      if (chip === null) throw new Error(`${role} chip did not render`);
      const classes = [...chip.classList];
      expect(classes, `${role} chip classes: ${classes.join(' ')}`).toContain('edge');
      expect(classes, `${role} chip classes: ${classes.join(' ')}`).toContain(
        `border-${role}`,
      );
    },
  );
});
