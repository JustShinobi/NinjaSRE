import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EN } from '@/i18n/en';
import { RunsScreen } from '@/surfaces/screens/runs';

import { contextFor, datasetViewer, serveScenario } from '../support/dataset';

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: () => ({ value: 'a-token' }),
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
  serveScenario('populated');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the runs list language', () => {
  it('uses investigations in visible copy and translates trigger slugs', async () => {
    render(await RunsScreen(contextFor(datasetViewer())));

    expect(
      screen.getByText('Every investigation this deployment has recorded'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Every run this deployment has recorded')).toBeNull();

    const triggers = screen.getAllByTestId('row').map((row) => {
      const cells = within(row).getAllByRole('cell');
      return cells[2]?.textContent ?? '';
    });

    expect(triggers).toEqual(expect.arrayContaining(['Alert', 'Scheduled', 'Manual']));
    expect(triggers).not.toContain('alert');
    expect(triggers).not.toContain('schedule');
    expect(triggers).not.toContain('manual');
  });

  it('keeps the raw trigger in the address value while showing its label', async () => {
    render(await RunsScreen(contextFor(datasetViewer())));

    const trigger = screen.getByRole('combobox', { name: EN['runs.filter.trigger'] });
    expect(within(trigger).getByRole('option', { name: 'Alert' })).toHaveValue('alert');
    expect(within(trigger).getByRole('option', { name: 'Scheduled' })).toHaveValue(
      'schedule',
    );
  });

  it('gives the subject cell a tooltip containing the complete subject', async () => {
    render(await RunsScreen(contextFor(datasetViewer())));

    const firstRow = screen.getAllByTestId('row')[0];
    if (firstRow === undefined) throw new Error('the populated fixture has no runs');
    const subject = within(firstRow).getAllByRole('cell')[0];
    if (subject === undefined) throw new Error('the run has no subject cell');

    const tooltip = subject.querySelector('[title]');
    if (tooltip === null) throw new Error('the subject has no tooltip');
    const visibleSubject = subject.querySelector('span.truncate');
    if (visibleSubject === null) throw new Error('the subject has no visible text');
    expect(tooltip.getAttribute('title')).toBe(visibleSubject.textContent.trim());
  });
});
