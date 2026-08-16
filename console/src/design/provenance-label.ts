import { message, type Locale } from '@/i18n/messages';

/**
 * What a row of an effective-configuration table says about where its value
 * came from — in a vocabulary where "no override" and "an override, recorded
 * at a node" never share a word.
 *
 * A module with no client directive, deliberately: every page that shows an
 * effective value's origin is a server component that calls this as a plain
 * function, and `tests/unit/shell/rsc-boundary.test.ts` refuses a server
 * module that calls a function a `'use client'` module exports — the same
 * reasoning `settings/values.ts` already follows for `valueAt`, and why this
 * sits beside `resolution-preview.tsx` rather than inside it.
 *
 * A deployment's own root node can be named `default`, so a provenance string
 * built by printing the node name would read "Set at default" for an override
 * exactly there — indistinguishable, to an operator, from "this is the
 * default value", which is the opposite claim. The fix is not to rename the
 * node; it is to never let the two cases share a sentence. An unset value
 * says "Deployment default" and names no node at all; an overridden one
 * always says "Set at:" before the node, whatever that node is called.
 *
 * `name` may be a leaf path the API attributed directly, or a compound one a
 * table collapsed into a single row (a policy, an integration list). For a
 * compound row with no direct entry, every leaf beneath it is consulted: one
 * shared source is reported as that source, more than one is reported as
 * mixed rather than guessing which one to show.
 */
export function provenanceLabel(
  locale: Locale,
  name: string,
  provenance: ReadonlyMap<string, string>,
): string {
  const direct = provenance.get(name);
  if (direct !== undefined && direct !== '') {
    return message(locale, 'configuration.provenance.setAt', { node: direct });
  }
  const prefix = `${name}.`;
  const children = new Set(
    [...provenance.entries()]
      .filter(([path]) => path.startsWith(prefix))
      .map(([, node]) => node),
  );
  if (children.size === 1) {
    return message(locale, 'configuration.provenance.setAt', {
      node: [...children][0] ?? '',
    });
  }
  if (children.size > 1) {
    return message(locale, 'configuration.provenance.mixed');
  }
  return message(locale, 'configuration.provenance.default');
}
