import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { panelLabels } from '../labels';
import { editableFields } from '../editable';
import { Panel } from '../panel';
import { ConfigEditor } from '../preview';
import {
  authorised,
  dataOf,
  dependencyOf,
  pairs,
  panelRead,
  read,
  stateOf,
} from '../read';
import { OrgTree, placedTree } from '../tree';
import { readViewState, resolveNode, type FilterName } from '../url-state';

/**
 * The organisation tree, what applies at a node, and where each value came from.
 *
 * Provenance on every value is the part worth defending. "Where is this set" is
 * the question every configuration screen gets asked and almost none answers,
 * and without it an operator changes a value at the wrong level, sees no effect,
 * and concludes the console is broken.
 */

export const CONFIG_FILTERS: readonly FilterName[] = ['node'];

/** The permission that decides whether the editor is on the page at all. */
const WRITE = 'config.write';

export async function ConfigurationScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, search } = context;
  const state = readViewState(search, CONFIG_FILTERS);
  const init = authorised(credential);

  const tree = await panelRead('/v1/config', () => read('/v1/config', init));
  const placed = placedTree(dataOf(tree));
  const selected = resolveNode(state, viewer, placed);

  const effective =
    selected === ''
      ? { status: 'ready' as const, data: {} as unknown }
      : await panelRead<unknown>('/v1/config/{node_id}', () =>
          read('/v1/config/{node_id}', { ...init, params: { node_id: selected } }),
        );

  const values = pairs(dataOf(effective), 'values');
  const provenance = new Map(pairs(dataOf(effective), 'provenance'));
  const writable = may(viewer, WRITE);

  // Asked for only by somebody who may write. A viewer who may not has no
  // editor on the page, so the read behind it would be a request nothing uses.
  const fields =
    !writable || selected === ''
      ? { status: 'ready' as const, data: {} as unknown }
      : await panelRead<unknown>('/v1/config/{node_id}/fields', () =>
          read('/v1/config/{node_id}/fields', {
            ...init,
            params: { node_id: selected },
          }),
        );
  const editable = editableFields(dataOf(fields));

  return (
    <>
      <AreaHeader area={areaFor('configuration')} locale={locale} />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="min-w-0">
          <Panel
            title={message(locale, 'configuration.tree.title')}
            state={stateOf(tree, placed.length === 0)}
            dependency={dependencyOf(tree)}
            labels={panelLabels(locale, message(locale, 'configuration.tree.title'))}
            empty={{
              heading: message(locale, 'configuration.empty.heading'),
              body: message(locale, 'configuration.empty.body'),
              actionLabel: message(locale, 'configuration.empty.action'),
              href: '/configuration',
            }}
          >
            <OrgTree
              nodes={placed}
              selected={selected}
              label={message(locale, 'configuration.tree.title')}
              hrefFor={(id) => `/configuration?node=${encodeURIComponent(id)}`}
            />
          </Panel>
        </div>

        <div className="lg:col-span-2 min-w-0 flex flex-col gap-5">
          <Panel
            title={message(locale, 'configuration.values.title')}
            state={stateOf(effective, values.length === 0)}
            dependency={dependencyOf(effective)}
            labels={panelLabels(locale, message(locale, 'configuration.values.title'))}
            empty={{
              heading: message(locale, 'configuration.empty.heading'),
              body: message(locale, 'configuration.empty.body'),
              actionLabel: message(locale, 'configuration.empty.action'),
              href: '/configuration',
            }}
          >
            <table className="w-full text-small">
              <caption className="sr-only">
                {message(locale, 'configuration.values.title')}
              </caption>
              <thead>
                <tr>
                  {[
                    message(locale, 'configuration.column.setting'),
                    message(locale, 'configuration.column.value'),
                    message(locale, 'configuration.column.provenance'),
                  ].map((header) => (
                    <th
                      key={header}
                      scope="col"
                      className="text-left text-micro uppercase text-muted px-3 pb-2 edge border-border border-t-0 border-x-0"
                    >
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {values.map(([name, value]) => (
                  <tr key={name} data-testid="config-value" data-setting={name}>
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-all">
                      {name}
                    </td>
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0 break-all">
                      {value}
                    </td>
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                      {/* Which level set it. Without this, a value changed at
                          the wrong level looks like a console that ignored the
                          change. */}
                      <span data-testid="provenance" data-setting={name}>
                        <Badge status={provenance.get(name) ?? 'unknown'} />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>

          {/* Absent, not disabled, for a viewer who may not write. */}
          {writable ? (
            <Panel
              title={message(locale, 'configuration.editor.title')}
              state={stateOf(fields, editable.length === 0)}
              dependency={dependencyOf(fields)}
              labels={panelLabels(
                locale,
                message(locale, 'configuration.editor.title'),
              )}
              empty={{
                heading: message(locale, 'configuration.preview.empty.heading'),
                body: message(locale, 'configuration.preview.empty.body'),
                actionLabel: message(locale, 'configuration.preview.empty.action'),
                href: '/configuration',
              }}
            >
              <p className="text-meta text-muted mb-3">
                {message(locale, 'configuration.editor.lead')}
              </p>
              <ConfigEditor
                nodeId={selected}
                fields={editable}
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
                  empty: message(locale, 'configuration.preview.empty.heading'),
                  previewFirst: message(locale, 'configuration.editor.previewFirst'),
                  clear: message(locale, 'configuration.editor.clear'),
                  cleared: message(locale, 'configuration.editor.cleared'),
                  redundant: message(locale, 'configuration.editor.redundant'),
                  reverts: message(locale, 'configuration.editor.reverts'),
                  notEditable: message(locale, 'configuration.editor.notEditable'),
                  inherited: message(locale, 'configuration.editor.inherited'),
                }}
              />
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}
