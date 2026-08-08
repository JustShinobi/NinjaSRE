'use client';

import type { ReactNode } from 'react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';

import { cx } from '@/design/cx';
import { message, type Locale } from '@/i18n/messages';
import { COMMAND_GROUPS, matching, type Command } from './commands';

/**
 * The palette: everywhere, keyboard-only, and without a side effect when it is
 * dismissed.
 *
 * "Keyboard-only operable" is not the same as "reachable by keyboard". The
 * palette is opened, filtered, moved through, run and dismissed without a
 * pointer ever entering it, which means every one of those five is a key
 * binding somebody has learned somewhere else: `Ctrl`/`⌘` and `K` to open,
 * typing to filter, the arrows to move, `Enter` to run, `Escape` to leave.
 *
 * Dismissing changes nothing. That sounds obvious and is the property most
 * easily lost: a palette that committed the highlighted entry on blur would run
 * a command every time somebody pressed the shortcut by accident, and the
 * command they would run is the first one in the list.
 */

export interface PaletteProps {
  readonly open: boolean;
  readonly locale: Locale;
  readonly commands: readonly Command[];
  readonly onClose: () => void;
  /** What running one does. Given in, so the palette itself navigates nothing. */
  readonly onRun: (command: Command) => void;
}

/** Whether this keystroke is the palette's shortcut, on either kind of keyboard. */
export function isPaletteShortcut(event: {
  readonly key: string;
  readonly metaKey: boolean;
  readonly ctrlKey: boolean;
}): boolean {
  return event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey);
}

/**
 * The palette, mounted only while it is open.
 *
 * Splitting the frame from the body is what lets the query be forgotten between
 * openings without an effect that resets it: a closed palette is not rendered,
 * so the next opening is a fresh mount holding nothing. A palette that reopened
 * carrying somebody's last search is one that runs the wrong thing on the first
 * `Enter`, which is the keystroke most likely to arrive before anybody looks.
 */
export function Palette(props: PaletteProps): ReactNode {
  if (!props.open) {
    return null;
  }
  return <PaletteBody {...props} />;
}

function PaletteBody({
  locale,
  commands,
  onClose,
  onRun,
}: Omit<PaletteProps, 'open'>): ReactNode {
  const [query, setQuery] = useState('');
  const [highlighted, setHighlighted] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const titleId = useId();

  const shown = useMemo(() => matching(commands, query), [commands, query]);

  // Focus goes into the palette the moment it exists. A palette a keyboard has
  // to be tabbed into is a palette a keyboard shortcut did not actually open.
  useEffect(() => {
    input.current?.focus();
  }, []);

  function move(delta: number): void {
    if (shown.length === 0) return;
    setHighlighted((at) => (at + delta + shown.length) % shown.length);
  }

  function onKeyDown(event: React.KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      move(1);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      move(-1);
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      const chosen = shown[highlighted];
      if (chosen !== undefined) {
        onRun(chosen);
      }
    }
  }

  return (
    <div
      data-testid="palette"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      className="fixed inset-0 z-10 flex items-start justify-center bg-sunken/80 p-5"
      onKeyDown={onKeyDown}
    >
      <div className="flex w-full max-w-prose flex-col rounded-3 edge border-border bg-raised shadow-2">
        <h2 id={titleId} className="sr-only">
          {message(locale, 'palette.title')}
        </h2>
        <input
          ref={input}
          type="text"
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-label={message(locale, 'palette.title')}
          placeholder={message(locale, 'palette.placeholder')}
          value={query}
          data-testid="palette-query"
          onChange={(event) => {
            setQuery(event.target.value);
            setHighlighted(0);
          }}
          className="w-full rounded-3 bg-transparent px-4 py-3 text-body outline-none"
        />
        {shown.length === 0 ? (
          <p data-testid="palette-empty" className="px-4 py-3 text-small text-muted">
            {message(locale, 'palette.empty')}
          </p>
        ) : (
          <ul id={listId} role="listbox" className="max-h-screen overflow-y-auto pb-2">
            {COMMAND_GROUPS.map((group) => {
              const inGroup = shown.filter((command) => command.group === group);
              if (inGroup.length === 0) return null;
              return (
                <li key={group}>
                  <p className="px-4 pt-2 pb-1 text-micro uppercase text-muted">
                    {message(locale, `palette.group.${group}`)}
                  </p>
                  <ul>
                    {inGroup.map((command) => {
                      const index = shown.indexOf(command);
                      const active = index === highlighted;
                      return (
                        <li key={command.id}>
                          <button
                            type="button"
                            role="option"
                            aria-selected={active}
                            data-testid="palette-command"
                            data-command={command.id}
                            tabIndex={-1}
                            onMouseEnter={() => {
                              setHighlighted(index);
                            }}
                            onClick={() => {
                              onRun(command);
                            }}
                            className={cx(
                              'flex w-full items-baseline gap-3 px-4 py-2 text-left text-small motion-hover',
                              active ? 'bg-accent-bg text-accent' : 'text-text',
                            )}
                          >
                            <span className="truncate">{command.label}</span>
                            {command.hint === undefined ? null : (
                              <span className="ml-auto truncate text-meta text-muted">
                                {command.hint}
                              </span>
                            )}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
