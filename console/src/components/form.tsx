'use client';

import type { ChangeEvent, ReactNode } from 'react';
import { useId, useState } from 'react';

import { cx } from '@/design/cx';
import { ChevronDownIcon } from '@/design/icons';

/**
 * The form controls.
 *
 * Two rules run through all of them. Every control has a real label — not a
 * placeholder, which disappears the moment somebody types and takes the
 * question with it. And every error is announced on the control as well as
 * shown beside it, because a red border is a state some viewers do not have.
 *
 * The controls are uncontrolled by default and take a change handler when a
 * caller wants one. A design system that insisted on owning form state would be
 * a form library, and this is not one.
 */

/** The label, the description and the error, laid out the same way every time. */
function Field({
  id,
  label,
  description,
  error,
  children,
  inline = false,
}: {
  readonly id: string;
  readonly label: string;
  // `| undefined` spelled out because `exactOptionalPropertyTypes` is on: a
  // caller forwarding its own optional prop passes `undefined`, and without
  // this the only way to forward one would be to build the props object
  // conditionally at every call site.
  readonly description?: string | undefined;
  readonly error?: string | undefined;
  readonly children: ReactNode;
  readonly inline?: boolean;
}): ReactNode {
  return (
    <div
      className={cx(
        // `min-w-0` because a date input carries an intrinsic minimum width
        // larger than a narrow column, and a flex item that will not shrink
        // below its content takes the whole page sideways with it.
        'flex gap-1 min-w-0',
        inline ? 'flex-row items-center gap-2' : 'flex-col',
      )}
    >
      {inline ? children : null}
      <label htmlFor={id} className="text-meta text-muted">
        {label}
      </label>
      {inline ? null : children}
      {description === undefined ? null : (
        <p id={`${id}-description`} className="text-meta text-muted">
          {description}
        </p>
      )}
      {error === undefined ? null : (
        <p id={`${id}-error`} role="alert" className="text-meta text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/** What a control points `aria-describedby` at, given what it has. */
function describedBy(
  id: string,
  description?: string,
  error?: string,
): string | undefined {
  const parts = [
    description === undefined ? null : `${id}-description`,
    error === undefined ? null : `${id}-error`,
  ].filter((part): part is string => part !== null);
  return parts.length > 0 ? parts.join(' ') : undefined;
}

const CONTROL =
  'h-control px-3 rounded-2 edge border-border-strong bg-surface text-text text-body w-full motion-hover';

const INVALID = 'border-danger';

export interface FieldProps {
  readonly label: string;
  readonly name: string;
  readonly description?: string;
  readonly error?: string;
  readonly disabled?: boolean;
}

export interface InputProps extends FieldProps {
  /**
   * `password` is here for one reason: a credential typed in plain sight is a
   * credential the person at the next desk has read.
   */
  readonly type?: 'text' | 'search' | 'number' | 'date' | 'password';
  /**
   * What the browser may remember and offer back.
   *
   * Here for the same reason `password` is: an operations credential that the
   * browser's own memory offers back on a shared machine is a credential the
   * next person at that keyboard has. `off` is the only value a caller needs,
   * and spelling it as a prop rather than as a literal attribute is what makes
   * "every secret field turns it off" a thing a test can walk.
   */
  readonly autoComplete?: 'off' | undefined;
  readonly value?: string;
  readonly defaultValue?: string;
  readonly onValueChange?: (value: string) => void;
}

/** One line of text. */
export function Input({
  label,
  name,
  description,
  error,
  disabled = false,
  type = 'text',
  autoComplete,
  value,
  defaultValue,
  onValueChange,
}: InputProps): ReactNode {
  const id = useId();
  return (
    <Field id={id} label={label} description={description} error={error}>
      <input
        id={id}
        name={name}
        type={type}
        autoComplete={autoComplete}
        disabled={disabled}
        value={value}
        defaultValue={defaultValue}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={describedBy(id, description, error)}
        onChange={(event: ChangeEvent<HTMLInputElement>) => {
          onValueChange?.(event.target.value);
        }}
        className={cx(CONTROL, error === undefined ? '' : INVALID)}
      />
    </Field>
  );
}

export interface Option {
  readonly value: string;
  readonly label: string;
}

export interface SelectProps extends FieldProps {
  readonly options: readonly Option[];
  readonly value?: string;
  readonly onValueChange?: (value: string) => void;
}

/** A choice from a closed list, using the browser's own control. */
export function Select({
  label,
  name,
  options,
  description,
  error,
  disabled = false,
  value,
  onValueChange,
}: SelectProps): ReactNode {
  const id = useId();
  return (
    <Field id={id} label={label} description={description} error={error}>
      <div className="relative">
        <select
          id={id}
          name={name}
          disabled={disabled}
          value={value}
          aria-invalid={error === undefined ? undefined : true}
          aria-describedby={describedBy(id, description, error)}
          onChange={(event: ChangeEvent<HTMLSelectElement>) => {
            onValueChange?.(event.target.value);
          }}
          className={cx(
            CONTROL,
            'appearance-none pr-6',
            error === undefined ? '' : INVALID,
          )}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDownIcon className="absolute right-2 top-3 text-muted" />
      </div>
    </Field>
  );
}

export interface TextareaProps extends FieldProps {
  readonly rows?: number;
  readonly value?: string;
  readonly onValueChange?: (value: string) => void;
}

/** Several lines of text — a rejection reason, a note on an approval. */
export function Textarea({
  label,
  name,
  description,
  error,
  disabled = false,
  rows = 4,
  value,
  onValueChange,
}: TextareaProps): ReactNode {
  const id = useId();
  return (
    <Field id={id} label={label} description={description} error={error}>
      <textarea
        id={id}
        name={name}
        rows={rows}
        disabled={disabled}
        value={value}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={describedBy(id, description, error)}
        onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
          onValueChange?.(event.target.value);
        }}
        className={cx(
          'px-3 py-2 rounded-2 edge border-border-strong bg-surface text-text text-body w-full',
          error === undefined ? '' : INVALID,
        )}
      />
    </Field>
  );
}

export interface CheckboxProps extends FieldProps {
  readonly checked?: boolean;
  readonly onCheckedChange?: (checked: boolean) => void;
}

/** One independent yes or no. */
export function Checkbox({
  label,
  name,
  description,
  error,
  disabled = false,
  checked,
  onCheckedChange,
}: CheckboxProps): ReactNode {
  const id = useId();
  return (
    <Field id={id} label={label} description={description} error={error} inline>
      <input
        id={id}
        name={name}
        type="checkbox"
        disabled={disabled}
        checked={checked}
        aria-describedby={describedBy(id, description, error)}
        onChange={(event: ChangeEvent<HTMLInputElement>) => {
          onCheckedChange?.(event.target.checked);
        }}
        className="icon-nav rounded-1 edge border-border-strong accent-accent"
      />
    </Field>
  );
}

export interface RadioProps extends FieldProps {
  readonly value: string;
  readonly checked?: boolean;
  readonly onSelect?: (value: string) => void;
}

/** One choice out of several that share a name. */
export function Radio({
  label,
  name,
  value,
  description,
  error,
  disabled = false,
  checked,
  onSelect,
}: RadioProps): ReactNode {
  const id = useId();
  return (
    <Field id={id} label={label} description={description} error={error} inline>
      <input
        id={id}
        name={name}
        type="radio"
        value={value}
        disabled={disabled}
        checked={checked}
        aria-describedby={describedBy(id, description, error)}
        onChange={() => {
          onSelect?.(value);
        }}
        className="icon-nav rounded-full edge border-border-strong accent-accent"
      />
    </Field>
  );
}

export interface SwitchProps extends FieldProps {
  readonly checked?: boolean;
  readonly onCheckedChange?: (checked: boolean) => void;
}

/**
 * A setting that takes effect as soon as it is flipped.
 *
 * A real `role="switch"` rather than a styled checkbox, because the two are
 * announced differently and the difference is exactly the one that matters: a
 * switch is on, a checkbox is selected, and "autonomy is selected" is not a
 * sentence anybody wants to hear at three in the morning.
 */
export function Switch({
  label,
  name,
  description,
  error,
  disabled = false,
  checked = false,
  onCheckedChange,
}: SwitchProps): ReactNode {
  const id = useId();
  const [on, setOn] = useState(checked);
  return (
    <Field id={id} label={label} description={description} error={error} inline>
      <button
        id={id}
        type="button"
        role="switch"
        name={name}
        disabled={disabled}
        aria-checked={on}
        aria-describedby={describedBy(id, description, error)}
        onClick={() => {
          const next = !on;
          setOn(next);
          onCheckedChange?.(next);
        }}
        className={cx(
          'inline-flex items-center w-6 h-4 rounded-full edge motion-hover',
          on
            ? 'bg-accent border-accent justify-end'
            : 'bg-neutral-bg border-border-strong',
        )}
      >
        <span className="icon-nav rounded-full bg-surface" />
      </button>
    </Field>
  );
}

export interface ComboboxProps extends FieldProps {
  readonly options: readonly Option[];
  readonly onValueChange?: (value: string) => void;
}

/**
 * A text field over a list, for a set too long to scroll and too open to close.
 *
 * The roles are the ones the pattern requires rather than the ones that happen
 * to render: a `combobox` with `aria-expanded` and `aria-autocomplete`, and
 * options that are `option`s. Without them a screen reader announces a text
 * field and the list simply is not there.
 */
export function Combobox({
  label,
  name,
  options,
  description,
  error,
  disabled = false,
  onValueChange,
}: ComboboxProps): ReactNode {
  const id = useId();
  const listId = `${id}-list`;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  const matching = options.filter((option) =>
    option.label.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <Field id={id} label={label} description={description} error={error}>
      <input
        id={id}
        name={name}
        type="text"
        role="combobox"
        disabled={disabled}
        value={query}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={describedBy(id, description, error)}
        onChange={(event: ChangeEvent<HTMLInputElement>) => {
          setQuery(event.target.value);
          setOpen(true);
          onValueChange?.(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            event.preventDefault();
            setOpen(true);
          }
          if (event.key === 'Escape') {
            setOpen(false);
          }
        }}
        className={cx(CONTROL, error === undefined ? '' : INVALID)}
      />
      <ul
        id={listId}
        role="listbox"
        aria-label={label}
        hidden={!open}
        className="rounded-2 edge border-border bg-surface shadow-2"
      >
        {matching.map((option) => (
          <li
            key={option.value}
            role="option"
            aria-selected={false}
            className="px-3 py-2 text-small"
          >
            {option.label}
          </li>
        ))}
        {open && matching.length === 0 ? (
          <li className="px-3 py-2 text-small text-muted">No match for “{query}”.</li>
        ) : null}
      </ul>
    </Field>
  );
}

export interface DateRangeProps {
  readonly label: string;
  readonly name: string;
  readonly from?: string;
  readonly to?: string;
  readonly onRangeChange?: (range: { from: string; to: string }) => void;
}

/**
 * Two dates, which are two questions.
 *
 * One control labelled "window" would leave a screen reader saying "window,
 * window". A range that ends before it starts is reported rather than accepted,
 * because the alternative is an empty result set that looks like no data.
 */
export function DateRange({
  label,
  name,
  from = '',
  to = '',
  onRangeChange,
}: DateRangeProps): ReactNode {
  const [range, setRange] = useState({ from, to });
  const inverted = range.from !== '' && range.to !== '' && range.to < range.from;

  const update = (next: { from: string; to: string }): void => {
    setRange(next);
    onRangeChange?.(next);
  };

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-meta text-muted">{label}</legend>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Input
          label={`${label} from`}
          name={`${name}-from`}
          type="date"
          value={range.from}
          onValueChange={(value) => {
            update({ ...range, from: value });
          }}
        />
        <Input
          label={`${label} to`}
          name={`${name}-to`}
          type="date"
          value={range.to}
          onValueChange={(value) => {
            update({ ...range, to: value });
          }}
        />
      </div>
      {inverted ? (
        <p role="alert" className="text-meta text-danger">
          The range ends before it starts.
        </p>
      ) : null}
    </fieldset>
  );
}
