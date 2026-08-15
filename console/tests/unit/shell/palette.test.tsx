import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  commandsFor,
  matching,
  navigationCommands,
  type SearchAnswer,
} from '@/shell/commands';
import { message } from '@/i18n/messages';
import { isPaletteShortcut, Palette } from '@/shell/palette';
import { visibleAreas, visibleSettingsPages } from '@/shell/routes';

import { owner, ROLE_ORDER, viewerAt } from './support';

/**
 * The palette, operated without a pointer from beginning to end.
 *
 * Every one of these presses a key. That is the criterion — "fully operable
 * without a pointer" is not satisfied by a control being focusable, it is
 * satisfied by opening, filtering, moving, running and dismissing from the
 * keyboard, and each of those is a separate way to have got it wrong.
 */

const VIEWER = owner();

function commands(): ReturnType<typeof commandsFor> {
  return commandsFor(VIEWER, 'en', [
    { id: 'run-0001', status: 'succeeded', summary: 'A volume filled.' },
    { id: 'run-0002', status: 'failed', summary: null },
  ]);
}

describe('the registry areas contribute to', () => {
  it('offers every area the viewer may reach, and no other', () => {
    const offered = navigationCommands(VIEWER, 'en').map((command) => command.href);
    expect(offered).toEqual(visibleAreas(VIEWER).map((area) => area.path));
  });

  it('offers every Settings page by its display name, not only the areas', () => {
    // A page reached by opening Settings and then picking from a second
    // navigation is two steps away from somebody who already knows its name.
    // The palette is what makes the name enough, so every page the viewer may
    // reach is offered by the words on it — "Single sign-on", not "Settings".
    const offered = commandsFor(VIEWER, 'en');
    const reachable = visibleSettingsPages(VIEWER);

    expect(reachable.length).toBeGreaterThan(0);
    for (const page of reachable) {
      const found = offered.find((command) => command.href === page.path);
      expect(found, `no palette command reaches ${page.path}`).toBeDefined();
      expect(found?.label).toBe(message('en', page.label));
    }
  });

  it('drops a Settings page command the viewer may not reach', () => {
    const least = ROLE_ORDER[0];
    if (least === undefined) throw new Error('the role catalogue is empty');
    const offered = commandsFor(viewerAt(least), 'en').map((command) => command.href);

    // Absent, not disabled — the same rule the subnav and the sidebar keep.
    expect(offered).not.toContain('/settings/members-roles');
    expect(offered).not.toContain('/settings/audit-log');
  });

  it('drops an area command the viewer may not run', () => {
    const least = ROLE_ORDER[0];
    if (least === undefined) throw new Error('the role catalogue is empty');
    const offered = commandsFor(viewerAt(least), 'en').map((command) => command.id);

    expect(offered).toContain('go:dashboard');
    expect(offered).not.toContain('go:administration');
    // The action, too: a palette entry that refuses is a palette entry that has
    // told somebody the capability exists.
    expect(offered).not.toContain('act:investigate');
  });

  it('offers recent runs by identifier, which is what three letters are for', () => {
    expect(commands().map((command) => command.id)).toContain('run:run-0001');
  });

  it('offers the tour again as an explicit action', () => {
    const tour = commands().find((command) => command.id === 'act:view-tour');

    expect(tour).toMatchObject({ group: 'actions', href: '/?tour=1' });
  });

  it('groups navigation, then runs, then actions', () => {
    const groups = [...new Set(commands().map((command) => command.group))];
    expect(groups).toEqual(['navigate', 'runs', 'actions']);
  });

  it('filters on the label and on the hint, and keeps the order it was given', () => {
    const found = matching(commands(), 'run-000');
    expect(found.map((command) => command.id)).toEqual([
      'run:run-0001',
      'run:run-0002',
    ]);
  });

  it('matches without regard to case, because nobody types the case', () => {
    expect(matching(commands(), 'KNOWLEDGE').length).toBeGreaterThan(0);
  });
});

describe('the shortcut', () => {
  it('is the one both kinds of keyboard have learned', () => {
    expect(isPaletteShortcut({ key: 'k', metaKey: true, ctrlKey: false })).toBe(true);
    expect(isPaletteShortcut({ key: 'K', metaKey: false, ctrlKey: true })).toBe(true);
    expect(isPaletteShortcut({ key: 'k', metaKey: false, ctrlKey: false })).toBe(false);
    expect(isPaletteShortcut({ key: 'j', metaKey: true, ctrlKey: false })).toBe(false);
  });
});

describe('the palette, from the keyboard alone', () => {
  function open(
    onRun = vi.fn(),
    onClose = vi.fn(),
  ): {
    onRun: ReturnType<typeof vi.fn>;
    onClose: ReturnType<typeof vi.fn>;
  } {
    render(
      <Palette
        open
        locale="en"
        commands={commands()}
        onClose={onClose}
        onRun={onRun}
      />,
    );
    return { onRun, onClose };
  }

  it('takes focus the moment it opens', () => {
    open();
    expect(screen.getByTestId('palette-query')).toHaveFocus();
  });

  it('filters as somebody types', async () => {
    open();
    await userEvent.keyboard('knowledge');

    const shown = screen
      .getAllByTestId('palette-command')
      .map((command) => command.getAttribute('data-command'));
    expect(shown).toEqual(['go:knowledge']);
  });

  it('says nothing matches rather than showing an empty list', async () => {
    open();
    await userEvent.keyboard('nothing at all like this');
    expect(screen.getByTestId('palette-empty')).toBeInTheDocument();
  });

  it('moves with the arrows and wraps at both ends', async () => {
    open();
    const selected = (): string | null =>
      screen
        .getAllByTestId('palette-command')
        .find((command) => command.getAttribute('aria-selected') === 'true')
        ?.getAttribute('data-command') ?? null;

    const first = selected();
    await userEvent.keyboard('{ArrowDown}');
    expect(selected()).not.toBe(first);
    await userEvent.keyboard('{ArrowUp}');
    expect(selected()).toBe(first);
    // Up from the first goes to the last: a keyboard user at the top pressing
    // up expects the bottom, not silence.
    await userEvent.keyboard('{ArrowUp}');
    expect(selected()).not.toBe(first);
  });

  it('runs the highlighted command on Enter', async () => {
    const { onRun } = open();
    await userEvent.keyboard('knowledge{Enter}');

    expect(onRun).toHaveBeenCalledOnce();
    expect(onRun.mock.calls[0]?.[0]).toMatchObject({ href: '/knowledge' });
  });

  it('runs nothing at all when nothing matches', async () => {
    const { onRun } = open();
    await userEvent.keyboard('zzzzz{Enter}');
    expect(onRun).not.toHaveBeenCalled();
  });

  it('dismisses on Escape without running anything', async () => {
    const { onRun, onClose } = open();
    await userEvent.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalledOnce();
    // Dismissing must change nothing. A palette that committed the highlighted
    // entry on the way out would run the first command in the list every time
    // somebody pressed the shortcut by mistake.
    expect(onRun).not.toHaveBeenCalled();
  });

  it('is not in the document at all while it is closed', () => {
    render(
      <Palette
        open={false}
        locale="en"
        commands={commands()}
        onClose={vi.fn()}
        onRun={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('palette')).toBeNull();
  });

  it('announces itself as a dialog with a name', () => {
    open();
    expect(
      screen.getByRole('dialog', { name: /command palette/i }),
    ).toBeInTheDocument();
  });
});

describe('searching the deployment from the palette', () => {
  /**
   * The placeholder promised "Search resources, runs, incidents" while the list
   * held the navigation, the recent runs and one action — so typing the name of
   * a resource sitting on the Resources screen answered "Nothing matches that".
   * In an operations tool that is the shortest path there is.
   */

  function found(label: string): SearchAnswer {
    return {
      commands: [
        {
          id: 'resource:r1',
          group: 'resources' as const,
          label,
          href: '/resources?selected=r1',
          permission: 'estate.read',
        },
      ],
      partial: false,
    };
  }

  it('asks the deployment and shows what it found', async () => {
    const search = vi.fn().mockResolvedValue(found('signoz-collector'));
    const person = userEvent.setup();
    render(
      <Palette
        open
        locale="en"
        commands={commands()}
        search={search}
        onClose={vi.fn()}
        onRun={vi.fn()}
      />,
    );

    await person.type(screen.getByTestId('palette-query'), 'signoz');

    expect(await screen.findByText('signoz-collector')).toBeTruthy();
    expect(search).toHaveBeenCalled();
    expect(search.mock.calls[0]?.[0]).toBe('signoz');
  });

  it('puts what was found above the navigation', async () => {
    // Somebody who typed a name is looking for a thing. Putting the navigation
    // first would send the first Enter to a page instead.
    const search = vi.fn().mockResolvedValue(found('signoz-collector'));
    const person = userEvent.setup();
    render(
      <Palette
        open
        locale="en"
        commands={commands()}
        search={search}
        onClose={vi.fn()}
        onRun={vi.fn()}
      />,
    );

    await person.type(screen.getByTestId('palette-query'), 'signoz');
    await screen.findByText('signoz-collector');

    const shown = screen
      .getAllByTestId('palette-command')
      .map((node) => node.getAttribute('data-command'));
    expect(shown[0]).toBe('resource:r1');
  });

  it('does not ask about a single character', async () => {
    // One character matches most of an estate: three reads to hand back what
    // the operator is already looking at.
    const search = vi.fn().mockResolvedValue(found('anything'));
    const person = userEvent.setup();
    render(
      <Palette
        open
        locale="en"
        commands={commands()}
        search={search}
        onClose={vi.fn()}
        onRun={vi.fn()}
      />,
    );

    await person.type(screen.getByTestId('palette-query'), 's');

    expect(search).not.toHaveBeenCalled();
  });

  it('never shows an answer to a question that is no longer being asked', async () => {
    // The property that keeps a slow answer from landing under somebody's Enter
    // key: results are held with the query they answer, and read back only when
    // the two still agree.
    const search = vi.fn().mockResolvedValue(found('stale-result'));
    const person = userEvent.setup();
    render(
      <Palette
        open
        locale="en"
        commands={commands()}
        search={search}
        onClose={vi.fn()}
        onRun={vi.fn()}
      />,
    );

    const box = screen.getByTestId('palette-query');
    await person.type(box, 'signoz');
    await screen.findByText('stale-result');
    await person.clear(box);
    await person.type(box, 'signals');

    expect(screen.queryByText('stale-result')).toBeNull();
  });

  it('still works as a palette when the deployment cannot be asked', async () => {
    // The half that does not need the network keeps working, and there is no
    // dialog in the way of it: the person typing is usually the one whose
    // deployment is already having a bad day.
    const search = vi.fn().mockRejectedValue(new Error('unreachable'));
    const person = userEvent.setup();
    render(
      <Palette
        open
        locale="en"
        commands={commands()}
        search={search}
        onClose={vi.fn()}
        onRun={vi.fn()}
      />,
    );

    await person.type(screen.getByTestId('palette-query'), 'knowledge');

    expect(screen.getAllByTestId('palette-command').length).toBeGreaterThan(0);
  });

  it('says when it only searched part of what there is', async () => {
    // "Nothing matches" and "nothing matches in the first two hundred" are
    // different answers, and only one of them means the thing is not there.
    const search = vi.fn().mockResolvedValue({ commands: [], partial: true });
    const person = userEvent.setup();
    render(
      <Palette
        open
        locale="en"
        commands={[]}
        search={search}
        onClose={vi.fn()}
        onRun={vi.fn()}
      />,
    );

    await person.type(screen.getByTestId('palette-query'), 'nothing-like-this');

    expect(await screen.findByText(/more than one page/)).toBeTruthy();
  });
});

describe('the palette with a pointer, which people also use', () => {
  // Keyboard-only *operable* is the requirement; pointer-usable is what
  // everybody actually does half the time, and clicking a row has to run the
  // same command Enter would have.
  it('runs the command that was clicked', async () => {
    const onRun = vi.fn();
    const person = userEvent.setup();
    render(
      <Palette
        open
        locale="en"
        commands={commands()}
        onClose={vi.fn()}
        onRun={onRun}
      />,
    );

    const knowledge = screen
      .getAllByTestId('palette-command')
      .find((node) => node.getAttribute('data-command') === 'go:knowledge');
    if (knowledge === undefined) {
      throw new Error('the palette did not offer the knowledge row');
    }
    await person.click(knowledge);

    expect(onRun).toHaveBeenCalledOnce();
    expect(onRun.mock.calls[0]?.[0]).toMatchObject({ href: '/knowledge' });
  });

  it('follows the pointer with the highlight, so Enter runs what is under it', async () => {
    const person = userEvent.setup();
    render(
      <Palette
        open
        locale="en"
        commands={commands()}
        onClose={vi.fn()}
        onRun={vi.fn()}
      />,
    );

    const rows = screen.getAllByTestId('palette-command');
    const second = rows[1];
    if (second === undefined) throw new Error('the palette offered one row');
    await person.hover(second);

    expect(second.getAttribute('aria-selected')).toBe('true');
  });
});
