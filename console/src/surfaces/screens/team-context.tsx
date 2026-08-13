import type { ReactNode } from 'react';

import { Breadcrumb } from '@/components/navigation';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { panelLabels } from '../labels';
import { OperatingContextEditor, type ContextSection } from '../operating-context';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  list,
  number,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { OrgTree, placedTree } from '../tree';
import { readViewState, resolveNode, type FilterName } from '../url-state';

/**
 * What this team knows about its own environment, and the prompt it becomes.
 *
 * The screen exists because the facts here are not fields. "Container metrics
 * come from the host, by vmid" has no type, no range and no closed set — it is
 * a paragraph somebody writes once and every investigation reads afterwards —
 * and a form generated from a schema has nothing useful to say about one.
 *
 * Two things are load-bearing and both are the deployment's rather than this
 * console's. **Provenance per section**, because a section is the unit of
 * inheritance here: an organisation states what is true everywhere and a team
 * adds what is only theirs, and a screen that could not say which was which
 * would have somebody editing at the wrong level and concluding nothing
 * happened. **The preview is the prompt**, which is the 058 discipline applied
 * where the effect of saving is most literal: the text that comes back is what
 * the model will read.
 *
 * The starting document is offered only where nothing has been written. It is
 * derived from what the estate has already discovered, and it is offered rather
 * than applied for the same reason a suggested address is: derived text is
 * evidence, and typing it is a decision.
 */

export const TEAM_CONTEXT_FILTERS: readonly FilterName[] = ['node'];

/** The permission that decides whether the editor is on the page at all. */
const WRITE = 'config.write';

function sectionsOf(record: unknown, name: string): readonly ContextSection[] {
  return list(record, name).map((entry) => ({
    name: text(entry, 'name'),
    body: text(entry, 'body'),
    provenance: text(entry, 'provenance'),
  }));
}

export async function TeamContextScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer, search } = context;
  const state = readViewState(search, TEAM_CONTEXT_FILTERS);
  const init = authorised(credential);

  const tree = await panelRead('/v1/config', () => read('/v1/config', init));
  const placed = placedTree(dataOf(tree));
  const selected = resolveNode(state, viewer, placed);

  const held =
    selected === ''
      ? { status: 'ready' as const, data: {} as unknown }
      : await panelRead<unknown>('/v1/config/{node_id}/operating-context', () =>
          read('/v1/config/{node_id}/operating-context', {
            ...init,
            params: { node_id: selected },
          }),
        );

  const document = dataOf(held);
  const sections = sectionsOf(document, 'sections');
  const template = sectionsOf(document, 'template');
  const roles = list(document, 'roles').map((role) => String(role));

  return (
    <>
      <AreaHeader area={areaFor('team-context')} locale={locale} />

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
              href: '/team-context',
            }}
          >
            {/* A tree earns the space it takes. One node — the common case for a
                deployment with a single team — has nothing to navigate, and a
                nav-and-list rendering of it is a whole column spent on a name
                already in the panel's own title. That case collapses to a
                breadcrumb; the tree itself is drawn only where there is one. */}
            {placed.length > 1 ? (
              <OrgTree
                nodes={placed}
                selected={selected}
                label={message(locale, 'configuration.tree.title')}
                hrefFor={(id) => `/team-context?node=${encodeURIComponent(id)}`}
              />
            ) : (
              <div data-testid="org-breadcrumb">
                <Breadcrumb
                  label={message(locale, 'configuration.tree.title')}
                  trail={placed.map((node) => ({ label: node.name }))}
                />
              </div>
            )}
          </Panel>
        </div>

        <div className="lg:col-span-2 min-w-0 flex flex-col gap-5">
          <Panel
            title={message(locale, 'teamContext.sections.title')}
            state={stateOf(held, sections.length === 0 && template.length === 0)}
            dependency={dependencyOf(held)}
            labels={panelLabels(locale, message(locale, 'teamContext.sections.title'))}
            empty={{
              heading: message(locale, 'teamContext.empty.heading'),
              // Composed rather than a body of its own: an empty editor with
              // nothing but "nothing written here yet" gives no sense of what a
              // section actually is. `factNotInstruction` already carries the
              // concrete example the rest of this screen shows once something
              // is written — "Container metrics come from the host, by vmid" —
              // so the same sentence appears here, before there is anything to
              // point at.
              body: `${message(locale, 'teamContext.empty.body')} ${message(locale, 'teamContext.factNotInstruction')}`,
              actionLabel: message(locale, 'teamContext.empty.action'),
              href: '/configuration',
            }}
          >
            <p className="text-meta text-muted mb-3">
              {message(locale, 'teamContext.sections.lead')}
            </p>
            <OperatingContextEditor
              nodeId={selected}
              sections={sections}
              template={template}
              tokensUsed={number(document, 'tokens_used')}
              tokenBudget={number(document, 'token_budget')}
              roles={roles}
              writable={may(viewer, WRITE)}
              labels={{
                section: message(locale, 'teamContext.column.section'),
                body: message(locale, 'teamContext.column.body'),
                provenance: message(locale, 'teamContext.provenance'),
                budget: message(locale, 'teamContext.budget'),
                budgetUsed: message(locale, 'teamContext.budgetUsed'),
                overBudget: message(locale, 'teamContext.overBudget'),
                addSection: message(locale, 'teamContext.addSection'),
                sectionName: message(locale, 'teamContext.sectionName'),
                remove: message(locale, 'teamContext.remove'),
                factNotInstruction: message(locale, 'teamContext.factNotInstruction'),
                runbooks: message(locale, 'teamContext.runbooks'),
                policy: message(locale, 'teamContext.policy'),
                previewTitle: message(locale, 'teamContext.preview.title'),
                previewLead: message(locale, 'teamContext.preview.lead'),
                submit: message(locale, 'teamContext.preview.submit'),
                previewing: message(locale, 'teamContext.preview.previewing'),
                previewFirst: message(locale, 'teamContext.preview.first'),
                save: message(locale, 'teamContext.save'),
                saving: message(locale, 'teamContext.saving'),
                saved: message(locale, 'teamContext.saved'),
                failed: message(locale, 'teamContext.failed'),
                unreachable: message(locale, 'teamContext.unreachable'),
                roles: message(locale, 'teamContext.roles'),
                templateUse: message(locale, 'teamContext.template.use'),
              }}
            />
          </Panel>
        </div>
      </div>
    </>
  );
}
