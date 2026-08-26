'use client';

import type { ReactNode } from 'react';
import { useRouter } from 'next/navigation';

import { Select } from '@/components/form';
import { hrefFor, withFilter, type FilterName, type ViewState } from './url-state';

/**
 * A screen's filters, bound to its address.
 *
 * Changing one is a navigation rather than a state change, and that is the whole
 * design: the filtered view has an address, so it can be reloaded, bookmarked,
 * and pasted to a colleague who sees exactly what the sender was looking at. A
 * filter held in component state passes every test anybody writes about
 * filtering and fails that one.
 */

export interface FilterChoice {
  readonly name: FilterName;
  readonly label: string;
  /** The values, in the order the screen wants them offered. */
  readonly options: readonly { readonly value: string; readonly label: string }[];
  /**
   * What "unset" is called for this control, when "Any" is the wrong word.
   *
   * A filter unset means every value, and `anyLabel` says so. A control that
   * shapes the listing rather than narrowing it has a real default instead —
   * unset is not "any view", it is the grouped one — and saying "Any" there
   * would be a control that cannot describe its own resting state.
   */
  readonly unsetLabel?: string;
}

export interface FilterBarProps {
  readonly path: string;
  readonly state: ViewState;
  readonly filters: readonly FilterName[];
  readonly choices: readonly FilterChoice[];
  /** What the "no particular value" option is called, in the viewer's language. */
  readonly anyLabel: string;
}

/** One row of choices, each of which navigates. */
export function FilterBar({
  path,
  state,
  filters,
  choices,
  anyLabel,
}: FilterBarProps): ReactNode {
  const router = useRouter();

  return (
    <div data-testid="filters" className="flex flex-wrap items-end gap-3 mb-4">
      {choices.map((choice) => (
        <div
          key={choice.name}
          className="min-w-0"
          data-testid="filter"
          data-filter={choice.name}
        >
          <Select
            label={choice.label}
            name={choice.name}
            value={state.filters[choice.name] ?? ''}
            options={[
              { value: '', label: choice.unsetLabel ?? anyLabel },
              ...choice.options,
            ]}
            onValueChange={(value) => {
              router.push(
                hrefFor(path, withFilter(state, choice.name, value), filters),
              );
            }}
          />
        </div>
      ))}
    </div>
  );
}
