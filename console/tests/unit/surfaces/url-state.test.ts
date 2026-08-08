import { describe, expect, it } from 'vitest';

import {
  DEFAULT_VIEW_STATE,
  PAGE_PARAM,
  SELECTION_PARAM,
  SORT_PARAM,
  hrefFor,
  readViewState,
  withFilter,
  withPage,
  withSelection,
  withSort,
  writeViewState,
  type FilterName,
  type ViewState,
} from '@/surfaces/url-state';

/**
 * A view somebody can send to a colleague.
 *
 * The property is a round trip, not a getter: whatever a screen is showing has
 * to survive being written into an address, pasted into a chat channel, and read
 * back on a machine that has never had this console open. A filter held in
 * component state passes every test anybody writes about filtering and fails
 * that one.
 */

const FILTERS: readonly FilterName[] = ['status', 'trigger', 'team'];

describe('the state a screen puts in its address', () => {
  it('round-trips every filter, the sort, the page and the selection', () => {
    const state: ViewState = {
      filters: { status: 'failed', trigger: 'alert', team: 'org-northwind' },
      sort: 'started',
      descending: true,
      page: 4,
      selection: 'run-0004',
    };

    const written = writeViewState(state, FILTERS);
    expect(readViewState(written, FILTERS)).toEqual(state);
  });

  it('writes nothing for a filter nobody set, so a fresh address is clean', () => {
    expect(writeViewState(DEFAULT_VIEW_STATE, FILTERS)).toBe('');
  });

  it('reads an address that carries none of it as the default view', () => {
    expect(readViewState('', FILTERS)).toEqual(DEFAULT_VIEW_STATE);
  });

  it('ignores a parameter that is not one of this screen’s filters', () => {
    const read = readViewState('status=failed&colour=green', FILTERS);

    expect(read.filters).toEqual({ status: 'failed' });
  });

  it('accepts a URLSearchParams as readily as a string', () => {
    const read = readViewState(new URLSearchParams('status=running'), FILTERS);

    expect(read.filters.status).toBe('running');
  });

  it('treats a page that is not a number as the first page', () => {
    expect(readViewState(`${PAGE_PARAM}=nought`, FILTERS).page).toBe(1);
    expect(readViewState(`${PAGE_PARAM}=-3`, FILTERS).page).toBe(1);
  });

  it('carries the sort direction as a sign rather than a second parameter', () => {
    const written = writeViewState(
      { ...DEFAULT_VIEW_STATE, sort: 'cost', descending: true },
      FILTERS,
    );

    expect(written).toBe(`${SORT_PARAM}=-cost`);
    expect(readViewState(written, FILTERS)).toMatchObject({
      sort: 'cost',
      descending: true,
    });
  });
});

describe('changing one part of the view', () => {
  const state: ViewState = {
    filters: { status: 'failed' },
    sort: 'started',
    descending: false,
    page: 7,
    selection: 'run-0001',
  };

  it('returns to the first page when a filter changes', () => {
    // Page six of a list that just became eleven rows long is an empty screen
    // and a reader who thinks the filter matched nothing.
    expect(withFilter(state, 'status', 'running').page).toBe(1);
  });

  it('clears a filter set to nothing rather than writing an empty value', () => {
    const cleared = withFilter(state, 'status', '');

    expect(cleared.filters.status).toBeUndefined();
    expect(writeViewState(cleared, FILTERS)).not.toContain('status');
  });

  it('reverses an already-selected sort rather than re-sorting by it', () => {
    expect(withSort(state, 'started').descending).toBe(true);
    expect(withSort(withSort(state, 'started'), 'started').descending).toBe(false);
    expect(withSort(state, 'cost')).toMatchObject({ sort: 'cost', descending: false });
  });

  it('keeps the page when only the selection changes', () => {
    expect(withSelection(state, 'run-0002')).toMatchObject({
      page: 7,
      selection: 'run-0002',
    });
    expect(withSelection(state, null).selection).toBeNull();
  });

  it('refuses a page below the first', () => {
    expect(withPage(state, 0).page).toBe(1);
  });
});

describe('the address itself', () => {
  it('is the path alone when the view is the default one', () => {
    expect(hrefFor('/runs', DEFAULT_VIEW_STATE, FILTERS)).toBe('/runs');
  });

  it('carries the query when there is one', () => {
    const href = hrefFor(
      '/runs',
      { ...DEFAULT_VIEW_STATE, selection: 'run-0003' },
      FILTERS,
    );

    expect(href).toBe(`/runs?${SELECTION_PARAM}=run-0003`);
  });
});
