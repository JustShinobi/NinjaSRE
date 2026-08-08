/**
 * Everything a screen is showing, in its address.
 *
 * The requirement reads "so a view can be sent to a colleague", and that is the
 * whole design constraint: a filter held in component state passes every test
 * anybody writes about filtering and fails the one that matters, which is
 * somebody pasting a link into a channel at three in the morning.
 *
 * Pure functions over a query string rather than a hook, because the reader of
 * this state is a *server* component — the page is rendered with the filters
 * already applied rather than fetched wholesale and filtered in a browser. The
 * hook in `use-view.ts` is the writing half and is the only part that needs a
 * browser at all.
 */

/** A filter's name, exactly as it appears in the address. */
export type FilterName = string;

/** The parameters that are the same on every screen. */
export const SORT_PARAM = 'sort';
export const PAGE_PARAM = 'page';
export const SELECTION_PARAM = 'selected';

/** What a screen is showing, in the form the address carries. */
export interface ViewState {
  /** The filters that are set. A filter nobody set is absent, never empty. */
  readonly filters: Readonly<Record<string, string>>;
  /** The column being sorted by. Empty means the screen's own default order. */
  readonly sort: string;
  readonly descending: boolean;
  /** One-based, because it is a thing a person reads rather than an index. */
  readonly page: number;
  /** The row the detail rail is showing, where the screen has one. */
  readonly selection: string | null;
}

/** No filters, the screen's own order, the first page, nothing selected. */
export const DEFAULT_VIEW_STATE: ViewState = {
  filters: {},
  sort: '',
  descending: false,
  page: 1,
  selection: null,
};

function parameters(search: string | URLSearchParams): URLSearchParams {
  return typeof search === 'string' ? new URLSearchParams(search) : search;
}

/**
 * The view `search` describes, keeping only the filters this screen declares.
 *
 * A parameter the screen does not know is dropped rather than carried. Carrying
 * it would let one screen's address quietly change another's behaviour, and
 * dropping it is what makes the round trip below a closed loop.
 */
export function readViewState(
  search: string | URLSearchParams,
  declared: readonly FilterName[],
): ViewState {
  const found = parameters(search);
  const filters: Record<string, string> = {};
  for (const name of declared) {
    const value = found.get(name);
    if (value !== null && value !== '') {
      filters[name] = value;
    }
  }

  const sort = found.get(SORT_PARAM) ?? '';
  const descending = sort.startsWith('-');

  const page = Number.parseInt(found.get(PAGE_PARAM) ?? '', 10);
  const selection = found.get(SELECTION_PARAM);

  return {
    filters,
    sort: descending ? sort.slice(1) : sort,
    descending,
    page: Number.isFinite(page) && page >= 1 ? page : 1,
    selection: selection === null || selection === '' ? null : selection,
  };
}

/**
 * `state` as a query string, in the order the screen declares its filters.
 *
 * Ordered rather than however a map iterates, so the same view produces the same
 * address twice — which is what makes two people comparing links a comparison
 * rather than a puzzle.
 */
export function writeViewState(
  state: ViewState,
  declared: readonly FilterName[],
): string {
  const written = new URLSearchParams();
  for (const name of declared) {
    const value = state.filters[name];
    if (value !== undefined && value !== '') {
      written.set(name, value);
    }
  }
  if (state.sort !== '') {
    written.set(SORT_PARAM, state.descending ? `-${state.sort}` : state.sort);
  }
  if (state.page > 1) {
    written.set(PAGE_PARAM, String(state.page));
  }
  if (state.selection !== null) {
    written.set(SELECTION_PARAM, state.selection);
  }
  return written.toString();
}

/** `path`, with `state` on it, and nothing after the path when there is none. */
export function hrefFor(
  path: string,
  state: ViewState,
  declared: readonly FilterName[],
): string {
  const query = writeViewState(state, declared);
  return query === '' ? path : `${path}?${query}`;
}

/**
 * `state` with `name` set to `value`, back at the first page.
 *
 * Back at the first page deliberately. Page six of a list that just became
 * eleven rows long is an empty screen, and a reader who concludes the filter
 * matched nothing.
 */
export function withFilter(state: ViewState, name: string, value: string): ViewState {
  // Rebuilt rather than deleted from: a filter set to nothing is a filter the
  // address does not carry, and an own property holding `undefined` is not the
  // same thing as an absent one when the result is compared.
  const filters = Object.fromEntries(
    Object.entries(state.filters).filter(([held]) => held !== name),
  );
  if (value !== '') {
    filters[name] = value;
  }
  return { ...state, filters, page: 1 };
}

/** `state` sorted by `column`, reversing it when it is already the sort. */
export function withSort(state: ViewState, column: string): ViewState {
  const same = state.sort === column;
  return {
    ...state,
    sort: column,
    descending: same ? !state.descending : false,
    page: 1,
  };
}

/** `state` at `page`, never below the first one. */
export function withPage(state: ViewState, page: number): ViewState {
  return { ...state, page: page < 1 ? 1 : page };
}

/** `state` with `selection` showing, at the page it was already on. */
export function withSelection(state: ViewState, selection: string | null): ViewState {
  return { ...state, selection };
}
