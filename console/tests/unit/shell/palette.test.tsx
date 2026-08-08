import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { commandsFor, matching, navigationCommands } from '@/shell/commands';
import { isPaletteShortcut, Palette } from '@/shell/palette';
import { visibleAreas } from '@/shell/routes';

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

  it('drops an area command the viewer may not run', () => {
    const least = ROLE_ORDER[0];
    if (least === undefined) throw new Error('the role catalogue is empty');
    const offered = commandsFor(viewerAt(least), 'en').map((command) => command.id);

    expect(offered).toContain('go:dashboard');
    expect(offered).not.toContain('go:audit');
    // The action, too: a palette entry that refuses is a palette entry that has
    // told somebody the capability exists.
    expect(offered).not.toContain('act:investigate');
  });

  it('offers recent runs by identifier, which is what three letters are for', () => {
    expect(commands().map((command) => command.id)).toContain('run:run-0001');
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
    expect(matching(commands(), 'AUDIT').length).toBeGreaterThan(0);
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
    await userEvent.keyboard('audit');

    const shown = screen
      .getAllByTestId('palette-command')
      .map((command) => command.getAttribute('data-command'));
    expect(shown).toEqual(['go:audit']);
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
    await userEvent.keyboard('audit{Enter}');

    expect(onRun).toHaveBeenCalledOnce();
    expect(onRun.mock.calls[0]?.[0]).toMatchObject({ href: '/audit' });
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
