/**
 * Class composition, and nothing else.
 *
 * A component builds its classes from conditions, and the alternative to a
 * helper is a template literal per component with its own opinion about
 * separators and about what `false` means. Twelve of those disagree; one of
 * these does not.
 */

/** Anything a caller might pass where a class list is expected. */
export type ClassValue = string | false | null | undefined;

/** Join `values`, dropping the ones a condition turned off. */
export function cx(...values: readonly ClassValue[]): string {
  return values
    .filter((value): value is string => typeof value === 'string' && value !== '')
    .join(' ');
}
