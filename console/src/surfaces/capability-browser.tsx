'use client';

import { Fragment, useMemo, useState, type ReactNode } from 'react';

import { CapabilityAvailabilityChip, SideEffectChip } from '@/components/status';
import { Input } from '@/components/form';
import type { Locale } from '@/i18n/messages';

/**
 * 233 tools in 17 domains, searchable, with an anchor per domain.
 *
 * Everything a reader needs to find one tool by name is here: a filter over
 * name and domain, a jump list that tracks the filter rather than a fixed
 * table of contents, and a count that answers "how many of this can I
 * actually run" without scrolling to find out. All of it client-side and
 * over data the server already resolved — filtering 233 rows in the browser
 * costs nothing a network round trip for the same question would not have
 * cost far more of.
 */

/** One tool, exactly as this browser needs to draw it. */
export interface BrowsableTool {
  readonly name: string;
  readonly domain: string;
  readonly sideEffect: string;
  /** Whether the node's catalogue had an opinion about this tool at all. */
  readonly known: boolean;
  readonly available: boolean;
  /**
   * What is blocking this tool, already rendered in the caller's language.
   * Empty when the tool is available or nothing is known about it.
   */
  readonly blockedText: string;
  /** Whether `blockedText` names an integration a link can lead to connecting. */
  readonly blockedLinked: boolean;
}

/** One skill, exactly as this browser needs to draw it. */
export interface BrowsableSkill {
  readonly name: string;
  readonly summary: string;
}

interface DomainGroup {
  readonly domain: string;
  readonly tools: readonly BrowsableTool[];
}

/** `tools`, grouped by domain, first-seen order — recomputed as the filter changes. */
function groupedByDomain(tools: readonly BrowsableTool[]): readonly DomainGroup[] {
  const order: string[] = [];
  const byDomain = new Map<string, BrowsableTool[]>();
  for (const tool of tools) {
    if (!byDomain.has(tool.domain)) {
      order.push(tool.domain);
      byDomain.set(tool.domain, []);
    }
    byDomain.get(tool.domain)?.push(tool);
  }
  return order.map((domain) => ({ domain, tools: byDomain.get(domain) ?? [] }));
}

/** A domain name as a fragment identifier. Domains are declared, plain words. */
function anchorId(domain: string): string {
  return `domain-${domain.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
}

const SKILLS_ANCHOR = 'domain-skills';

/**
 * The shape a domain jump-link wears.
 *
 * `border-strong` rather than `border`: at 1.28:1 against the panel the
 * fainter token is not a visible boundary, and the boundary is the whole of
 * what says this is a control. Tall enough to be a target — twelve-pixel text
 * has a line box about half of what WCAG 2.2 asks.
 */
const DOMAIN_CHIP =
  'inline-flex items-center gap-2 min-h-6 rounded-4 px-3 py-1 edge border-border-strong bg-raised text-meta text-text motion-hover hover:bg-hover';

export interface CapabilityBrowserLabels {
  readonly tableCaption: string;
  readonly search: string;
  readonly searchEmpty: string;
  readonly domainsNav: string;
  readonly skillsHeading: string;
  readonly columnName: string;
  readonly columnEffect: string;
  readonly columnEnabled: string;
  readonly none: string;
  readonly blockedAction: string;
}

export interface CapabilityBrowserProps {
  readonly tools: readonly BrowsableTool[];
  readonly skills: readonly BrowsableSkill[];
  /** "14 of 233 enabled", already formatted server-side against the whole catalogue. */
  readonly count: string;
  /** Where a blocked tool's "connect it" link goes: this node's own Configuration. */
  readonly configurationHref: string;
  readonly labels: CapabilityBrowserLabels;
  readonly locale: Locale;
}

/** The tools-and-skills table, searchable, with a jump list and a count. */
export function CapabilityBrowser({
  tools,
  skills,
  count,
  configurationHref,
  labels,
  locale,
}: CapabilityBrowserProps): ReactNode {
  const [query, setQuery] = useState('');
  const needle = query.trim().toLowerCase();

  const matchingTools = useMemo(
    () =>
      needle === ''
        ? tools
        : tools.filter(
            (tool) =>
              tool.name.toLowerCase().includes(needle) ||
              tool.domain.toLowerCase().includes(needle),
          ),
    [tools, needle],
  );
  const matchingSkills = useMemo(
    () =>
      needle === ''
        ? skills
        : skills.filter(
            (skill) =>
              skill.name.toLowerCase().includes(needle) ||
              skill.summary.toLowerCase().includes(needle),
          ),
    [skills, needle],
  );

  const groups = useMemo(() => groupedByDomain(matchingTools), [matchingTools]);
  const namedGroups = groups.filter((group) => group.domain !== '');
  const nothingMatches = matchingTools.length === 0 && matchingSkills.length === 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <Input
          label={labels.search}
          name="capability-search"
          type="search"
          value={query}
          onValueChange={setQuery}
        />
        <p className="text-meta text-muted" data-testid="capability-count">
          {count}
        </p>
      </div>

      {namedGroups.length === 0 && matchingSkills.length === 0 ? null : (
        // Still anchors — they jump to a section rather than filtering — but
        // drawn as chips. Seventeen underlined twelve-pixel words wrapped over
        // two rows read as a paragraph somebody had linked every noun in, and
        // the underline that makes a link legible inside a sentence is what
        // makes a row of them illegible. The border and the ground say
        // "control"; the count stays because it is why you would pick one.
        <nav aria-label={labels.domainsNav} data-testid="domain-nav">
          <ul className="flex flex-wrap gap-2">
            {namedGroups.map((group) => (
              <li key={group.domain}>
                <a href={`#${anchorId(group.domain)}`} className={DOMAIN_CHIP}>
                  {group.domain}
                  <span className="text-muted tabular-nums">{group.tools.length}</span>
                </a>
              </li>
            ))}
            {matchingSkills.length === 0 ? null : (
              <li>
                <a href={`#${SKILLS_ANCHOR}`} className={DOMAIN_CHIP}>
                  {labels.skillsHeading}
                  <span className="text-muted tabular-nums">
                    {matchingSkills.length}
                  </span>
                </a>
              </li>
            )}
          </ul>
        </nav>
      )}

      {nothingMatches ? (
        <p className="text-meta text-muted" data-testid="capability-search-empty">
          {labels.searchEmpty}
        </p>
      ) : (
        <div className="w-full overflow-x-auto">
          <table className="w-full text-small">
            <caption className="sr-only">{labels.tableCaption}</caption>
            <thead>
              <tr>
                {/* No Domain column. The rows are grouped by domain and each
                    group is headed with it, so the column repeated its own
                    heading once per row — twenty-four times under "cloud
                    control plane" — for a table whose subject column was
                    meanwhile breaking names across two lines. */}
                {[labels.columnName, labels.columnEffect, labels.columnEnabled].map(
                  (header) => (
                    <th
                      key={header}
                      scope="col"
                      className="text-left text-micro text-muted px-3 pb-2 edge border-border border-t-0 border-x-0"
                    >
                      {header}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {groups.map(({ domain, tools: domainTools }) => (
                <Fragment key={domain === '' ? ' ' : domain}>
                  {/* Headed even where the tools declare no domain. With the
                      column gone the heading is the only thing saying which
                      group a row is in, so a group without one would be a run
                      of unattributed rows. */}
                  <tr data-testid="capability-domain" data-domain={domain}>
                    <th
                      {...(domain === '' ? {} : { id: anchorId(domain) })}
                      scope="rowgroup"
                      colSpan={3}
                      className="text-left text-meta font-semibold text-strong bg-hover px-3 py-2 edge border-border border-t-0 border-x-0"
                    >
                      {domain === '' ? labels.none : domain}{' '}
                      <span className="text-muted font-normal">
                        ({domainTools.length})
                      </span>
                    </th>
                  </tr>
                  {domainTools.map((tool) => (
                    <tr
                      key={tool.name}
                      data-testid="capability"
                      data-capability={tool.name}
                    >
                      <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-words">
                        {tool.name}
                      </td>
                      <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                        <SideEffectChip locale={locale} level={tool.sideEffect} />
                      </td>
                      <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                        {!tool.known ? (
                          <span className="text-muted text-meta">{labels.none}</span>
                        ) : tool.available ? (
                          <CapabilityAvailabilityChip
                            locale={locale}
                            available={tool.available}
                          />
                        ) : (
                          <span
                            className="text-meta text-muted"
                            data-testid="capability-blocked"
                          >
                            {tool.blockedText}
                            {tool.blockedLinked ? (
                              <>
                                {' '}
                                <a href={configurationHref} className="underline">
                                  {labels.blockedAction}
                                </a>
                              </>
                            ) : null}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </Fragment>
              ))}
              {matchingSkills.length === 0 ? null : (
                <Fragment>
                  <tr data-testid="capability-domain" data-domain="skills">
                    <th
                      id={SKILLS_ANCHOR}
                      scope="rowgroup"
                      colSpan={4}
                      className="text-left text-meta font-semibold text-strong bg-hover px-3 py-2 edge border-border border-t-0 border-x-0"
                    >
                      {labels.skillsHeading}{' '}
                      <span className="text-muted font-normal">
                        ({matchingSkills.length})
                      </span>
                    </th>
                  </tr>
                  {matchingSkills.map((skill) => (
                    <tr key={skill.name} data-testid="capability">
                      <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-words">
                        {skill.name}
                      </td>
                      <td
                        className="px-3 py-2 edge border-border border-t-0 border-x-0 text-muted"
                        colSpan={3}
                      >
                        {skill.summary}
                      </td>
                    </tr>
                  ))}
                </Fragment>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
