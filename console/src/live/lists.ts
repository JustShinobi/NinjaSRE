/**
 * A list that changes while somebody is reading it.
 *
 * Two requirements pull against each other here. A list of runs, approvals or
 * incidents has to stay current without a refetch — and it must not reorder
 * under the operator's pointer, because a row that moves between the decision
 * to click and the click is how the wrong change gets approved.
 *
 * So the two cases are separated. A row that is *already there* is updated in
 * place, at the index it already holds, whatever the sort order now says: the
 * content changes and nothing moves. A row that is *new* while the pointer is
 * over the list is held back and counted, and the operator places it themselves
 * by moving away or by pressing the control that says how many arrived.
 *
 * Pure, so both halves are provable without a pointer.
 */

/** A list, and what has arrived that is not in it yet. */
export interface ListState<T> {
  readonly items: readonly T[];
  /** Arrived while the pointer was over the list. Counted, not placed. */
  readonly pending: readonly T[];
}

/** How to tell one row from another, and what order they go in. */
export interface ListRules<T> {
  readonly identify: (item: T) => string;
  readonly order: (first: T, second: T) => number;
}

/** A list as it arrives from the server. */
export function listOf<T>(items: readonly T[], rules: ListRules<T>): ListState<T> {
  return { items: [...items].sort(rules.order), pending: [] };
}

/**
 * `state` with `item` received.
 *
 * `held` is whether the operator's pointer is over the list. It is a parameter
 * rather than something this module works out, because "the pointer is here" is
 * a fact only the component knows and a rule this module can then apply.
 */
export function receive<T>(
  state: ListState<T>,
  item: T,
  rules: ListRules<T>,
  held: boolean,
): ListState<T> {
  const id = rules.identify(item);
  const at = state.items.findIndex((held_) => rules.identify(held_) === id);

  if (at >= 0) {
    // Updated where it stands. Re-sorting a row that changed is a row that
    // jumps under the pointer for a reason the reader cannot see.
    const items = [...state.items];
    items[at] = item;
    return {
      items: held ? items : [...items].sort(rules.order),
      pending: state.pending,
    };
  }

  if (!held) {
    return { items: [...state.items, item].sort(rules.order), pending: state.pending };
  }

  const pending = state.pending.filter((waiting) => rules.identify(waiting) !== id);
  return { items: state.items, pending: [...pending, item] };
}

/** `state` with everything that arrived placed and the whole list back in order. */
export function settle<T>(state: ListState<T>, rules: ListRules<T>): ListState<T> {
  if (state.pending.length === 0) {
    return state.items.length === 0
      ? state
      : { items: [...state.items].sort(rules.order), pending: [] };
  }
  return { items: [...state.items, ...state.pending].sort(rules.order), pending: [] };
}

/** How many arrived and are not on screen. What the "new" control says. */
export function arrivedCount<T>(state: ListState<T>): number {
  return state.pending.length;
}
