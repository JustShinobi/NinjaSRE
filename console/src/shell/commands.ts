/**
 * The registry the palette shows, and what areas may put in it.
 *
 * A palette whose contents are written out in the palette is a palette that
 * goes stale: an area ships, nobody remembers, and the fastest way to reach the
 * new screen is the one nobody has. So areas contribute, and the palette
 * renders whatever it is given.
 *
 * Every entry carries the permission its target needs, and the registry drops
 * the ones the viewer does not hold. That is the same presence rule the
 * navigation follows and for the same reason: an entry that exists and refuses
 * still tells a reader what this deployment can do.
 */

import { message, type Locale } from '@/i18n/messages';
import { may, type Viewer } from '@/session/viewer';
import { visibleAreas, type AreaContext } from './routes';
import type { Found } from './search';

/** The sections the palette groups by, in the order it shows them.
 *
 * What the deployment was asked about comes first — resources, then incidents,
 * then the runs a search turned up. Somebody who typed a name is looking for a
 * thing, and putting the navigation above it would mean the first `Enter` goes
 * to a page rather than to what they asked for.
 */
export const COMMAND_GROUPS = [
  'resources',
  'incidents',
  'found-runs',
  'navigate',
  'runs',
  'actions',
] as const;

export type CommandGroup = (typeof COMMAND_GROUPS)[number];

/** One thing the palette can do. */
export interface Command {
  readonly id: string;
  readonly group: CommandGroup;
  /** Already in the viewer's language: the registry translates, the palette renders. */
  readonly label: string;
  /** The second line — a status, a summary, whatever distinguishes two alike. */
  readonly hint?: string;
  readonly href: string;
  /** The permission the target needs, or null when it needs none beyond a session. */
  readonly permission: string | null;
}

/** A run recent enough to be worth reaching by three letters of its identifier. */
export interface RecentRun {
  readonly id: string;
  readonly status: string;
  readonly summary: string | null;
}

/** The areas this viewer may reach, as commands. */
export function navigationCommands(
  viewer: Viewer,
  locale: Locale,
  context?: AreaContext,
): readonly Command[] {
  return visibleAreas(viewer, context).map((area) => ({
    id: `go:${area.id}`,
    group: 'navigate' as const,
    label: message(locale, area.label),
    hint: area.path,
    href: area.path,
    permission: area.permission,
  }));
}

/** The recent runs, as commands. Reaching one by identifier is most of what this is for. */
export function runCommands(runs: readonly RecentRun[]): readonly Command[] {
  return runs.map((run) => ({
    id: `run:${run.id}`,
    group: 'runs' as const,
    label: run.id,
    ...(run.summary === null ? {} : { hint: run.summary }),
    href: `/runs/${run.id}`,
    permission: 'investigation.read',
  }));
}

/** What one search of the deployment produced, as the palette takes it. */
export interface SearchAnswer {
  readonly commands: readonly Command[];
  /**
   * Whether some source held more than the search read.
   *
   * Carried rather than dropped: "nothing matches" and "nothing matches in the
   * first two hundred" are different answers, and only one of them means the
   * thing is not there.
   */
  readonly partial: boolean;
}

/**
 * What the deployment found, as commands.
 *
 * The permission each carries is the one its destination demands, so a viewer
 * who may not read the estate does not get estate rows in their palette — the
 * same presence rule the navigation follows, and the reason the filter in
 * `commandsFor` is the only place permission is decided.
 */
export function searchCommands(found: readonly Found[]): readonly Command[] {
  const permissions: Readonly<Record<Found['group'], string>> = {
    resources: 'estate.read',
    incidents: 'incident.read',
    runs: 'investigation.read',
  };
  const groups: Readonly<Record<Found['group'], CommandGroup>> = {
    resources: 'resources',
    incidents: 'incidents',
    runs: 'found-runs',
  };
  return found.map((entry) => ({
    id: entry.id,
    group: groups[entry.group],
    label: entry.label,
    ...(entry.hint === '' ? {} : { hint: entry.hint }),
    href: entry.href,
    permission: permissions[entry.group],
  }));
}

/** The things a viewer can start from anywhere. */
export function actionCommands(locale: Locale): readonly Command[] {
  return [
    {
      id: 'act:investigate',
      group: 'actions',
      label: message(locale, 'shell.investigate'),
      href: '/runs?start=1',
      permission: 'investigation.run',
    },
  ];
}

/** Everything a viewer may run, in group order. */
export function commandsFor(
  viewer: Viewer,
  locale: Locale,
  runs: readonly RecentRun[] = [],
  // The palette offers what the navigation offers. An area that has left the
  // sidebar because its work is done must not still be reachable by typing its
  // name — that is two answers to "what is there" and the palette's is the one
  // nobody maintains.
  context?: AreaContext,
): readonly Command[] {
  const everything = [
    ...navigationCommands(viewer, locale, context),
    ...runCommands(runs),
    ...actionCommands(locale),
  ];
  const permitted = everything.filter(
    (command) => command.permission === null || may(viewer, command.permission),
  );
  return COMMAND_GROUPS.flatMap((group) =>
    permitted.filter((command) => command.group === group),
  );
}

/**
 * The commands `query` selects, in the order they were given.
 *
 * A substring match on the label and the hint, folded to lower case. Not fuzzy:
 * a fuzzy match ranks, and a ranking that reorders while somebody is typing
 * moves the entry out from under the Enter key they were already pressing.
 */
export function matching(
  commands: readonly Command[],
  query: string,
): readonly Command[] {
  const needle = query.trim().toLowerCase();
  if (needle === '') {
    return commands;
  }
  return commands.filter((command) =>
    `${command.label} ${command.hint ?? ''}`.toLowerCase().includes(needle),
  );
}
