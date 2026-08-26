import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  ContentWidth,
  CountStrip,
  PageHeader,
  Section,
  SplitLayout,
} from '@/components/layout';
import { applyDensity, DENSITY_ATTRIBUTE, readDensity } from '@/design/density';
import { DENSITIES, DENSITY_METRICS } from '@/design/tokens';
import { ServerIcon } from '@/design/icons';

import { only } from '../support/dom';
import { geometryClasses } from '../support/geometry';

/**
 * Page structure as components, and density as an application-level switch.
 *
 * The page layout is here rather than in each screen's stylesheet for the
 * reason the whole feature exists: a gutter written per page is a gutter that
 * disagrees with the next page. And density is asserted for what it *does not*
 * change — a density that touched a colour would be a second theme wearing a
 * different name.
 */

describe('PageHeader', () => {
  it('is the one first-level heading on the page, with its context beneath', () => {
    render(
      <PageHeader
        icon={<ServerIcon size="head" />}
        title="Cluster HAL9000"
        context="2 nodes · 84 guests · last swept 41s ago"
      />,
    );

    expect(
      screen.getByRole('heading', { level: 1, name: 'Cluster HAL9000' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/last swept 41s ago/)).toBeInTheDocument();
  });

  it('puts its actions after its title in the reading order', () => {
    render(
      <PageHeader
        icon={<ServerIcon size="head" />}
        title="Cluster HAL9000"
        context="2 nodes"
        actions={<button type="button">Sweep now</button>}
      />,
    );

    const heading = screen.getByRole('heading', { level: 1 });
    const action = screen.getByRole('button', { name: 'Sweep now' });
    expect(
      heading.compareDocumentPosition(action) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});

describe('Section', () => {
  it('is a landmark named by its own heading', () => {
    render(
      <Section title="Attention">
        <p>Three things need a person.</p>
      </Section>,
    );
    expect(screen.getByRole('region', { name: 'Attention' })).toBeInTheDocument();
  });

  it('uses the section step of the type scale rather than whatever h2 does', () => {
    render(
      <Section title="Attention">
        <p>content</p>
      </Section>,
    );
    expect(screen.getByRole('heading', { name: 'Attention' }).className).toContain(
      'text-section',
    );
  });
});

describe('SplitLayout', () => {
  it('puts the primary surface first in the reading order, whatever the columns do', () => {
    render(
      <SplitLayout
        primary={<p>The investigation</p>}
        secondary={<p>The context rail</p>}
      />,
    );

    const primary = screen.getByText('The investigation');
    const secondary = screen.getByText('The context rail');
    expect(
      primary.compareDocumentPosition(secondary) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('collapses to one column below the breakpoint rather than scrolling sideways', () => {
    const { container } = render(
      <SplitLayout primary={<p>a</p>} secondary={<p>b</p>} />,
    );
    const classes = only(container, 'div').className;

    expect(classes).toContain('grid-cols-1');
    expect(classes).toContain('lg:grid-cols-3');
  });
});

describe('ContentWidth', () => {
  it('caps the measure so a line of prose does not run the width of a monitor', () => {
    const { container } = render(
      <ContentWidth>
        <p>content</p>
      </ContentWidth>,
    );
    expect(only(container, 'div').className).toContain('max-w-page');
  });
});

describe('density', () => {
  it('is applied once, at the top of the application', () => {
    applyDensity('compact');
    expect(document.documentElement).toHaveAttribute(DENSITY_ATTRIBUTE, 'compact');
    expect(readDensity()).toBe('compact');

    applyDensity('comfortable');
    expect(readDensity()).toBe('comfortable');
  });

  it('changes spacing and control height, and nothing else', () => {
    const [comfortable, compact] = DENSITIES.map((density) => DENSITY_METRICS[density]);

    expect(compact?.gap).toBeLessThan(comfortable?.gap ?? 0);
    expect(compact?.control).toBeLessThan(comfortable?.control ?? 0);
    // Three keys, and they are all lengths. A density that could carry a fourth
    // could carry a colour, and then it would be a theme.
    expect(Object.keys(comfortable ?? {})).toEqual(['gap', 'control', 'row']);
  });

  it('leaves the components own classes untouched, because it works through tokens', () => {
    applyDensity('comfortable');
    const { container: roomy, unmount } = render(
      <Section title="Attention">
        <p>content</p>
      </Section>,
    );
    const before = geometryClasses(only(roomy, 'section'));
    unmount();

    applyDensity('compact');
    const { container: dense } = render(
      <Section title="Attention">
        <p>content</p>
      </Section>,
    );
    expect(geometryClasses(only(dense, 'section'))).toEqual(before);
  });
});

/**
 * The count strip a page header carries, and the arithmetic it cannot get wrong.
 *
 * Resources said "97 watched · 76 healthy · 0 degraded · 13 unhealthy" for a
 * fortnight. Those three parts total 89: eight resources sat in a state the
 * sentence had no slot for, and the table two hundred pixels below showed them.
 * A reader who adds up is being told the page is lying to them, and they are
 * right.
 *
 * A fixed sentence with four holes cannot be fixed once and stay fixed — the
 * ninth state arrives and the sum breaks again. So the strip takes the parts and
 * proves against the total it was handed, and says so where it cannot.
 */
describe('the header count strip', () => {
  it('renders each part with its own value and label', () => {
    render(
      <CountStrip
        total={{ label: 'watched', value: 97 }}
        parts={[
          { label: 'healthy', value: 76, role: 'success' },
          { label: 'unhealthy', value: 13, role: 'danger' },
          { label: 'unknown', value: 8, role: 'neutral' },
        ]}
      />,
    );
    expect(screen.getByTestId('count-strip')).toBeInTheDocument();
    expect(screen.getByTestId('count-total')).toHaveTextContent('97');
    expect(screen.getAllByTestId('count-part')).toHaveLength(3);
  });

  it('marks itself unbalanced when the parts do not reach the total', () => {
    render(
      <CountStrip
        total={{ label: 'watched', value: 97 }}
        parts={[
          { label: 'healthy', value: 76, role: 'success' },
          { label: 'unhealthy', value: 13, role: 'danger' },
        ]}
      />,
    );
    // Not hidden and not silently corrected: a strip that does not add up is a
    // read that lost eight rows, and that is the interesting fact on the page.
    expect(screen.getByTestId('count-strip')).toHaveAttribute('data-balanced', 'false');
  });

  it('leaves a part with no role in the body colour', () => {
    render(
      <CountStrip
        total={{ label: 'watched', value: 3 }}
        parts={[{ label: 'kinds', value: 3 }]}
      />,
    );
    // Neither good nor bad: a count of kinds is a fact, and colouring it would
    // be this component deciding something the screen did not.
    const part = screen.getByTestId('count-part');
    expect(part.className).not.toContain('text-success');
    expect(part.className).not.toContain('text-danger');
  });

  it('says nothing about a shortfall it has no word for', () => {
    render(
      <CountStrip
        total={{ label: 'watched', value: 97 }}
        parts={[{ label: 'healthy', value: 76, role: 'success' }]}
      />,
    );
    // Still marked unbalanced — the fact is on the element for the suite and
    // for anything reading the DOM — but not rendered as a nameless number a
    // reader would have to guess the meaning of.
    expect(screen.getByTestId('count-strip')).toHaveAttribute('data-balanced', 'false');
    expect(screen.queryByTestId('count-shortfall')).toBeNull();
  });

  /**
   * Parts that overshoot the total are a different fault from parts that fall
   * short, and the strip must not dress one as the other.
   *
   * The staging estate does exactly this: 75 healthy + 5 absent + 8 unknown +
   * 13 unhealthy against a total of 96 — the breakdown counts five more than
   * the whole it belongs to. Rendered as a remainder that read "-5 unaccounted
   * for", which is worse than the sentence this replaced.
   */
  it('invents no cell for a remainder that is negative', () => {
    render(
      <CountStrip
        total={{ label: 'watched', value: 96 }}
        parts={[
          { label: 'healthy', value: 75, role: 'success' },
          { label: 'absent', value: 5, role: 'neutral' },
          { label: 'unknown', value: 8, role: 'neutral' },
          { label: 'unhealthy', value: 13, role: 'danger' },
        ]}
        shortfallLabel="unaccounted for"
      />,
    );

    expect(screen.queryByTestId('count-shortfall')).toBeNull();
    // Still reported: the two numbers disagree, and that is the interesting
    // fact rather than something to smooth over.
    expect(screen.getByTestId('count-strip')).toHaveAttribute('data-balanced', 'false');
    expect(screen.getByTestId('count-total')).toHaveAttribute('title', '101 / 96');
  });

  it('balances when they do', () => {
    render(
      <CountStrip
        total={{ label: 'watched', value: 97 }}
        parts={[
          { label: 'healthy', value: 76, role: 'success' },
          { label: 'unhealthy', value: 13, role: 'danger' },
          { label: 'unknown', value: 8, role: 'neutral' },
        ]}
      />,
    );
    expect(screen.getByTestId('count-strip')).toHaveAttribute('data-balanced', 'true');
  });
});
