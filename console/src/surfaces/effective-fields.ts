import { message, type Locale } from '@/i18n/messages';
import type { EffectiveFieldRow } from '@/design/resolution-preview';
import type { EditableField } from './preview';

/**
 * A configuration table's row, derived from the one place that already knows
 * both halves of it — the deployment's own field catalogue
 * (`GET /v1/config/{node_id}/fields`) — instead of a value read from the
 * effective-configuration document and an origin read from its separate
 * provenance map.
 *
 * The catalogue's `value` is `null` for a field nothing has ever set, so the
 * override is read from it only when `provenance` says something set it;
 * otherwise the row shows the schema's own `default`, which the catalogue
 * carries for exactly this reason. A row a page asks for and the catalogue
 * does not declare is a defect in the page, not a blank cell — see
 * `effectiveRows`'s own doc.
 */

/** One row this module is asked to draw: a path, its display label, and — for
 * the handful of fields whose unit a bare number does not say — how to say it. */
export interface EffectiveFieldSpec {
  readonly path: string;
  readonly label: string;
  /**
   * Overrides the type-driven formatting below for a field whose schema type
   * ('integer') does not carry its own unit — an expiry counted in hours, a
   * cooldown counted in seconds. Absent for every field the schema's own type
   * already says enough about.
   */
  readonly format?: ((value: unknown, locale: Locale) => string) | undefined;
}

/** `value`, read for a human: a boolean as the design system's own words for
 * on and off, everything else as its own literal — never the payload verbatim
 * for a boolean, which is what `true`/`false` printed as text would be. */
function formatByType(value: unknown, type: string, locale: Locale): string {
  if (type === 'boolean') {
    return message(
      locale,
      value === true ? 'configuration.value.on' : 'configuration.value.off',
    );
  }
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return JSON.stringify(value);
}

/**
 * `specs`, resolved against `fields` into rows a configuration table can
 * draw: the effective value (the override when one is recorded, the schema
 * default otherwise), formatted for reading, and the origin — the node that
 * set it, or the deployment-default phrase when none did.
 *
 * A spec naming a path the catalogue does not declare is the caller's own
 * mistake — the page asked for a field the schema does not carry — and is
 * surfaced as the same "not set" marker a genuinely blank field gets, rather
 * than thrown: a schema this deployment has not upgraded to yet must not
 * take the whole page down for one field it does not recognise.
 */
export function effectiveRows(
  specs: readonly EffectiveFieldSpec[],
  fields: readonly EditableField[],
  locale: Locale,
): readonly EffectiveFieldRow[] {
  const byPath = new Map(fields.map((field) => [field.path, field]));
  return specs.map((spec) => {
    const field = byPath.get(spec.path);
    if (field === undefined) {
      return {
        path: spec.path,
        label: spec.label,
        value: message(locale, 'configuration.value.notSet'),
        origin: message(locale, 'configuration.provenance.default'),
      };
    }
    const overridden = field.provenance !== '';
    const raw = overridden ? field.value : field.default;
    const formatted =
      spec.format !== undefined
        ? spec.format(raw, locale)
        : formatByType(raw, field.type, locale);
    return {
      path: spec.path,
      label: spec.label,
      // A field can be declared with no value and no default at all — a
      // required field nobody has filled in yet. The cell still owes an
      // explicit marker rather than nothing, which is indistinguishable from
      // a render defect.
      value:
        formatted === '' ? message(locale, 'configuration.value.notSet') : formatted,
      origin: overridden
        ? field.provenance
        : message(locale, 'configuration.provenance.default'),
    };
  });
}

/** `hours`, said as a duration — "2 hours", never the bare number. */
export function formatHours(value: unknown, locale: Locale): string {
  const count = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(count)) return '';
  return message(
    locale,
    count === 1 ? 'configuration.value.hours.one' : 'configuration.value.hours',
    {
      count: String(count),
    },
  );
}

/** `seconds`, said as a duration — "300 seconds", never the bare number. */
export function formatSeconds(value: unknown, locale: Locale): string {
  const count = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(count)) return '';
  return message(
    locale,
    count === 1 ? 'configuration.value.seconds.one' : 'configuration.value.seconds',
    { count: String(count) },
  );
}
