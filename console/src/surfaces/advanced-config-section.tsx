import type { ReactNode } from 'react';

import { message, type Locale } from '@/i18n/messages';
import { EffectiveFieldsTable } from '@/design/resolution-preview';
import { editableFields } from './editable';
import { effectiveRows } from './effective-fields';
import { ConfigEditor, type EditorLabels } from './preview';

/**
 * A technical group of a domain's own configuration, folded into that
 * domain's page rather than exiled to the generic editor.
 *
 * The spec that retires the raw configuration editor allows a group to live
 * "in an advanced section collapsed on the human page — never in a
 * resurrected generic editor". This is that section, built once: a `prefix`
 * scopes the deployment's own field catalogue to the group a page owns, the
 * effective value and its origin are shown for every field in it whether or
 * not the viewer may write, and the write path is the same `ConfigEditor`
 * the (former) generic editor used — never a client-side merge, never a
 * second opinion about what the deployment resolves a change to. Collapsed
 * by default, natively: a `<details>` with no `open` attribute costs no
 * client script and keeps every page that mounts this within the product's
 * scroll budget.
 *
 * A page using this still does its own fetch of `/v1/config`,
 * `/v1/config/{node_id}/fields` (regardless of `writable` — the effective
 * value and its origin are shown to every viewer of the page, not only one
 * who may change them), exactly as every page in this group already does for
 * its own primary content; this component starts from what that fetch
 * already produced rather than issuing a second, competing read.
 */

/** One field this section shows: its full schema path, and its already-localised label. */
export interface AdvancedConfigSectionField {
  readonly path: string;
  readonly label: string;
  /** Overrides the type-driven formatting below for a field the schema's own
   * type ('integer') does not say is a duration. */
  readonly format?: ((value: unknown, locale: Locale) => string) | undefined;
}

export interface AdvancedConfigSectionProps {
  /** The section heading, shown on the `<summary>` — already localised. */
  readonly title: string;
  /**
   * The dotted path prefix this section owns, e.g. `'policies.observation.'`.
   *
   * More than one may be given, for a page whose group is not a single clean
   * prefix: Schedules & destinations owns three named `surfaces.*` fields but
   * not the bare `surfaces.` prefix, which would also reach the notification
   * policy Notifications owns and a machine field with no form by decision.
   * Naming them individually is how a page scopes itself to what it owns
   * without offering a second, competing control for what it does not.
   */
  readonly prefix: string | readonly string[];
  /**
   * The `data-testid` for this section, where the one derived from the prefix
   * would not describe it. A section scoped to several paths is named for the
   * subject it covers, not for whichever path happens to sort first — the
   * derived name would change the moment somebody adds a path above it.
   */
  readonly testId?: string;
  readonly nodeId: string;
  readonly locale: Locale;
  readonly writable: boolean;
  /** Every field this section shows in the effective-value table, in display order. */
  readonly fields: readonly AdvancedConfigSectionField[];
  /**
   * The `/v1/config/{node_id}/fields` answer's own data, already unwrapped
   * from its envelope the way every page in this group already unwraps it
   * with `dataOf`. This is the one source both the effective-value table and
   * the editor below it read — the value, the schema default and the
   * per-field origin all come from here, so the two can never disagree about
   * what a field currently resolves to.
   */
  readonly rawFields: unknown;
}

/** Every prefix this section scopes to, whether one was given or several. */
function prefixesOf(prefix: string | readonly string[]): readonly string[] {
  return typeof prefix === 'string' ? [prefix] : prefix;
}

/**
 * A stable id for this section's `<details>`, derived from the prefix it
 * scopes — from the first one, where several are given, so that adding a
 * second path to a section does not silently rename the element its own
 * tests and the browser suite already address.
 *
 * Exported because it is also how a page links to its own advanced section —
 * an empty state whose field is already on this same page names this id
 * rather than a generic route, and it is what the id attribute below carries
 * so that link actually lands somewhere.
 */
export function advancedConfigSectionId(prefix: string | readonly string[]): string {
  return `advanced-config-${(prefixesOf(prefix)[0] ?? '')
    .replace(/[^a-z0-9]+/gi, '-')
    .toLowerCase()
    .replace(/^-+|-+$/g, '')}`;
}

/**
 * The `ConfigEditor` labels, built once for every advanced section instead of
 * copied into each one.
 *
 * The catalogue keys are the generic editor's own (`configuration.editor.*`,
 * `configuration.column.*`, `configuration.preview.*`): the control being
 * scoped to a prefix does not change what a save button, a locked field or a
 * "Set at:" note says, so there is nothing section-specific to parametrise.
 */
export function configEditorLabels(locale: Locale): EditorLabels {
  return {
    setting: message(locale, 'configuration.column.setting'),
    value: message(locale, 'configuration.column.value'),
    submit: message(locale, 'configuration.editor.submit'),
    save: message(locale, 'configuration.editor.save'),
    saving: message(locale, 'configuration.editor.saving'),
    saved: message(locale, 'configuration.editor.saved'),
    failed: message(locale, 'configuration.editor.failed'),
    unreachable: message(locale, 'configuration.editor.unreachable'),
    before: message(locale, 'configuration.preview.before'),
    after: message(locale, 'configuration.preview.after'),
    locked: message(locale, 'configuration.locked'),
    lockedDetail: message(locale, 'configuration.locked.detail'),
    gated: message(locale, 'configuration.gated'),
    gatedDetail: message(locale, 'configuration.gated.detail'),
    provenance: message(locale, 'configuration.column.provenance'),
    setAt: message(locale, 'configuration.editor.setAt'),
    usingDefault: message(locale, 'configuration.editor.usingDefault'),
    toc: message(locale, 'configuration.editor.toc'),
    search: message(locale, 'configuration.editor.search'),
    searchEmpty: message(locale, 'configuration.editor.searchEmpty'),
    generalSection: message(locale, 'configuration.editor.generalSection'),
    empty: message(locale, 'configuration.preview.empty.heading'),
    previewFirst: message(locale, 'configuration.editor.previewFirst'),
    clear: message(locale, 'configuration.editor.clear'),
    cleared: message(locale, 'configuration.editor.cleared'),
    redundant: message(locale, 'configuration.editor.redundant'),
    reverts: message(locale, 'configuration.editor.reverts'),
    notEditable: message(locale, 'configuration.editor.notEditable'),
    inherited: message(locale, 'configuration.editor.inherited'),
    useSuggested: message(locale, 'configuration.editor.useSuggested'),
    addEntry: message(locale, 'configuration.editor.addEntry'),
    removeEntry: message(locale, 'configuration.editor.removeEntry'),
    moveUp: message(locale, 'configuration.editor.moveUp'),
    moveDown: message(locale, 'configuration.editor.moveDown'),
    entryPosition: message(locale, 'configuration.editor.entryPosition'),
    emptyList: message(locale, 'configuration.editor.emptyList'),
  };
}

export function AdvancedConfigSection({
  title,
  prefix,
  testId,
  nodeId,
  locale,
  writable,
  fields,
  rawFields,
}: AdvancedConfigSectionProps): ReactNode {
  const catalogue = editableFields(rawFields);
  const rows = effectiveRows(fields, catalogue, locale);

  const scopes = prefixesOf(prefix);
  const editable = catalogue.filter((entry) =>
    scopes.some((scope) => entry.path.startsWith(scope)),
  );

  const anchorId = testId ?? advancedConfigSectionId(prefix);

  return (
    <details
      id={anchorId}
      data-testid={anchorId}
      className="edge border-border rounded-2 px-3 py-2"
    >
      <summary className="cursor-pointer select-none text-strong">{title}</summary>
      <div className="pt-3 flex flex-col gap-4">
        <EffectiveFieldsTable
          rows={rows}
          labels={{
            setting: message(locale, 'configuration.column.setting'),
            value: message(locale, 'configuration.column.value'),
            origin: message(locale, 'configuration.column.provenance'),
          }}
        />

        {writable && nodeId !== '' ? (
          <ConfigEditor
            nodeId={nodeId}
            fields={editable}
            labels={configEditorLabels(locale)}
            locale={locale}
          />
        ) : null}
      </div>
    </details>
  );
}
