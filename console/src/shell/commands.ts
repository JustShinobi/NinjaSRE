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
import { visibleAreas } from './routes';

/** The sections the palette groups by, in the order it shows them. */
export const COMMAND_GROUPS = ['navigate', 'runs', 'actions'] as const;

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
export function navigationCommands(viewer: Viewer, locale: Locale): readonly Command[] {
  return visibleAreas(viewer).map((area) => ({
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
): readonly Command[] {
  const everything = [
    ...navigationCommands(viewer, locale),
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
