import { render, screen } from '@testing-library/react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { ResourcesScreen } from '@/surfaces/screens/resources';

import { serveScenario, serveScenarioExcept } from '../support/dataset';

/**
 * Selecting a resource must change what the operator is looking at.
 *
 * The failure these tests exist for: the detail panels were appended after a
 * table of a hundred-odd rows, below the fold, so a click that worked looked
 * exactly like a click that did nothing. The detail therefore renders *above*
 * the table — named, with the way back to the list beside it — and these
 * assert the document order rather than trusting the layout to imply it.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/** The container the committed dataset carries a detail for. */
const SELECTED = 'ct-100';

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function resources(query: Record<string, string> = {}): Promise<void> {
  render(await ResourcesScreen(await surfaceContext(query)));
}

/** Whether `first` comes before `second` in document order. */
function precedes(first: HTMLElement, second: HTMLElement): boolean {
  const position = first.compareDocumentPosition(second);
  return (position & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

describe('where the selected resource’s detail sits', () => {
  it('draws no detail heading until a row is selected', async () => {
    serveScenario('populated');
    await resources();

    expect(screen.queryByTestId('resource-detail-header')).toBeNull();
  });

  it('places the detail above the table, where the click lands the eye', async () => {
    serveScenario('populated');
    await resources({ selected: SELECTED });

    const header = screen.getByTestId('resource-detail-header');
    const signals = screen.getByTestId('resource-signals');
    const [firstRow] = screen.getAllByTestId('resource-card');
    if (firstRow === undefined) throw new Error('no rows rendered');

    expect(precedes(header, firstRow)).toBe(true);
    expect(precedes(signals, firstRow)).toBe(true);
  });

  it('names the selected resource and offers the way back to the list', async () => {
    serveScenario('populated');
    await resources({ selected: SELECTED });

    const header = screen.getByTestId('resource-detail-header');
    // The committed dataset's own name for ct-100.
    expect(header).toHaveTextContent('plateau');

    const back = screen.getByTestId('resource-detail-back');
    expect(back).toHaveAttribute('href', '/resources');
  });

  it('keeps the rest of the view in the address the way back travels', async () => {
    serveScenario('populated');
    await resources({ selected: SELECTED, zone: 'apps' });

    const back = screen.getByTestId('resource-detail-back');
    expect(back).toHaveAttribute('href', '/resources?zone=apps');
  });

  it('still answers the click when the detail read is refused', async () => {
    // A deployment on an older build serves no detail route. The selection must
    // still visibly change the screen — the identifier stands in for the name —
    // or the operator is back to concluding the click is broken.
    serveScenarioExcept('populated', ['/v1/estate/resources/']);
    await resources({ selected: SELECTED });

    const header = screen.getByTestId('resource-detail-header');
    expect(header).toHaveTextContent(SELECTED);
    expect(screen.getByTestId('resource-detail-back')).toHaveAttribute(
      'href',
      '/resources',
    );
  });
});
