import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ContentWidth, PageHeader, Section, SplitLayout } from '@/components/layout';
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
