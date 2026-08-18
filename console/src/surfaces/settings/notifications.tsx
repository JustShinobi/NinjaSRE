import type { ReactNode } from 'react';

import type { MessageKey } from '@/i18n/en';
import { message, type Locale } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { editableFields } from '../editable';
import { effectiveRows, formatSeconds } from '../effective-fields';
import { readSetupState } from '../emptiness';
import { requestedSetupReturn, SetupReturnBanner } from '../first-run/return-banner';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import { ConfigEditor } from '../preview';
import { authorised, dataOf, dependencyOf, panelRead, read, stateOf } from '../read';
import { placedTree } from '../tree';
import { readViewState, resolveNode, type FilterName } from '../url-state';
import { EffectiveFieldsTable } from '@/design/resolution-preview';

/**
 * The attention policy, as controls with names — instead of the schema
 * section `surfaces.notification_policy` buried among thirty-eight others.
 *
 * Six fields, and every one of them narrows the platform ceiling rather than
 * widening it — `NotificationPolicySettings`'s own `section_help` says so,
 * and this page carries the same sentence rather than inventing a new one for
 * a contract that already has words.
 */

export const NOTIFICATIONS_FILTERS: readonly FilterName[] = ['node'];

const WRITE = 'config.write';
const SECTION_PREFIX = 'surfaces.notification_policy.';

/** The six fields, in the order the schema declares them, and their catalogue keys. */
const FIELDS: readonly {
  readonly name: string;
  readonly label: MessageKey;
  /** Overrides the type-driven formatting for a field the schema's own type
   * ('integer') does not say is a duration. */
  readonly format?: ((value: unknown, locale: Locale) => string) | undefined;
}[] = [
  {
    name: 'quiet_hours_enabled',
    label: 'settings.notifications.field.quiet_hours_enabled',
  },
  {
    name: 'quiet_hours_start',
    label: 'settings.notifications.field.quiet_hours_start',
  },
  { name: 'quiet_hours_end', label: 'settings.notifications.field.quiet_hours_end' },
  { name: 'timezone', label: 'settings.notifications.field.timezone' },
  {
    name: 'cooldown_seconds',
    label: 'settings.notifications.field.cooldown_seconds',
    format: formatSeconds,
  },
  {
    name: 'notifications_per_hour',
    label: 'settings.notifications.field.notifications_per_hour',
  },
];

export async function NotificationsSettingsScreen(
  context: SurfaceContext,
): Promise<ReactNode> {
  const { credential, locale, viewer, search } = context;
  const state = readViewState(search, NOTIFICATIONS_FILTERS);
  const init = authorised(credential);
  const writable = may(viewer, WRITE);

  const tree = await panelRead('/v1/config', () => read('/v1/config', init));
  const nodeId = resolveNode(state, viewer, placedTree(dataOf(tree)));

  const nothing = { status: 'ready' as const, data: {} as unknown };
  const effective =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/config/{node_id}', () =>
          read('/v1/config/{node_id}', { ...init, params: { node_id: nodeId } }),
        );

  // Read regardless of `writable`, exactly like the guardrails table this
  // mirrors — see `settings/autonomy.tsx`'s own note on the same read.
  const fields =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/config/{node_id}/fields', () =>
          read('/v1/config/{node_id}/fields', { ...init, params: { node_id: nodeId } }),
        );

  const catalogue = editableFields(dataOf(fields));
  const rows = effectiveRows(
    FIELDS.map(({ name, label, format }) => ({
      path: `${SECTION_PREFIX}${name}`,
      label: message(locale, label),
      format,
    })),
    catalogue,
    locale,
  );

  const editable = catalogue.filter((entry) => entry.path.startsWith(SECTION_PREFIX));

  const setup = await readSetupState(credential);
  const page = settingsPageFor('settings-notifications');

  return (
    <>
      <SettingsPageHeader page={page} locale={locale} />
      <SetupReturnBanner
        locale={locale}
        setup={setup}
        requested={requestedSetupReturn(search.get('return'))}
      />

      <p
        data-testid="notifications-contract-note"
        className="text-meta text-muted mb-4 max-w-prose"
      >
        {message(locale, 'settings.notifications.contractNote')}
      </p>

      <Panel
        title={message(locale, page.label)}
        state={nodeId === '' ? 'empty' : stateOf(effective, false)}
        dependency={dependencyOf(effective)}
        labels={panelLabels(locale, message(locale, page.label))}
        empty={{
          heading: message(locale, page.label),
          body: message(locale, 'settings.models.empty.body'),
          actionLabel: message(locale, 'settings.models.empty.action'),
          href: '/integrations',
        }}
      >
        <EffectiveFieldsTable
          rows={rows}
          labels={{
            setting: message(locale, 'configuration.column.setting'),
            value: message(locale, 'configuration.column.value'),
            origin: message(locale, 'configuration.column.provenance'),
          }}
        />

        {writable && nodeId !== '' ? (
          <div className="mt-5">
            <ConfigEditor
              nodeId={nodeId}
              fields={editable}
              locale={locale}
              labels={{
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
              }}
            />
          </div>
        ) : null}
      </Panel>
    </>
  );
}
