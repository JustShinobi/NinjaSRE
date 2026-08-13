import type { ReactNode } from 'react';

import { message, type Locale } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { panelLabels } from '../labels';
import { editableFields, suggestedAddresses, withSuggestions } from '../editable';
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

/** How much of a nested value's compact form shows before the reader has to expand it. */
const VALUE_PREVIEW_LENGTH = 80;

/** Return `value` pretty-printed, or null if it is not JSON worth reformatting. */
function prettyNested(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null;
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2);
  } catch {
    return null;
  }
}

/**
 * One effective-configuration value, collapsed if it is a nested object or list.
 *
 * The API sends a policy or an integration list as one compact JSON string —
 * correct on the wire, unreadable in a table cell. A leaf value (a string, a
 * number) still renders exactly as before; only the shapes nobody could read
 * at a glance gain a disclosure.
 */
function ConfigValue({ value }: { readonly value: string }): ReactNode {
  const pretty = prettyNested(value);
  if (pretty === null) return value;
  const preview =
    value.length > VALUE_PREVIEW_LENGTH
      ? `${value.slice(0, VALUE_PREVIEW_LENGTH)}…`
      : value;
  return (
    <details data-testid="config-value-nested">
      <summary className="cursor-pointer text-muted">{preview}</summary>
      <pre className="mt-2 whitespace-pre-wrap break-all text-meta">{pretty}</pre>
    </details>
  );
}

/**
 * What a row of the effective-configuration table says about where its value
 * came from — in a vocabulary where "no override" and "an override, recorded
 * at a node" never share a word.
 *
 * The deployment's own root node is named `default`, so a provenance string
 * built by printing the node name reads "Set at default" for an override
 * exactly there — indistinguishable, to an operator, from "this is the
 * default value", which is the opposite claim. The fix is not to rename the
 * node; it is to never let the two cases share a sentence. An unset value
 * says "Deployment default" and names no node at all; an overridden one
 * always says "Set at:" before the node, whatever that node is called.
 *
 * `name` may be a leaf path the API attributed directly, or a compound one
 * this table collapsed into a single row (a policy, an integration list). For
 * a compound row with no direct entry, every leaf beneath it is consulted: one
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
  // What the deployment already found running. An endpoint an operator would
  // otherwise have to go and read off a machine is offered here, with the reason
  // it was derived — offered, never applied, because a derived address is
  // evidence and typing one is a decision.
  const catalogue =
    !writable || selected === ''
      ? { status: 'ready' as const, data: {} as unknown }
      : await panelRead<unknown>('/v1/integrations', () =>
          read('/v1/integrations', init),
        );
  const editable = withSuggestions(
    editableFields(dataOf(fields)),
    suggestedAddresses(dataOf(catalogue)),
  );

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
                      <ConfigValue value={value} />
                    </td>
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                      {/* Which level set it, or that nothing does. Without
                          this, a value changed at the wrong level looks like a
                          console that ignored the change. */}
                      <span
                        data-testid="provenance"
                        data-setting={name}
                        className="text-meta text-muted"
                      >
                        {provenanceLabel(locale, name, provenance)}
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
                  setAt: message(locale, 'configuration.editor.setAt'),
                  usingDefault: message(locale, 'configuration.editor.usingDefault'),
                  toc: message(locale, 'configuration.editor.toc'),
                  search: message(locale, 'configuration.editor.search'),
                  searchEmpty: message(locale, 'configuration.editor.searchEmpty'),
                  generalSection: message(
                    locale,
                    'configuration.editor.generalSection',
                  ),
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
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}
