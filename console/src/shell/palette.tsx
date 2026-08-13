'use client';

import type { ReactNode } from 'react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';

import { cx } from '@/design/cx';
import { message, type Locale } from '@/i18n/messages';
import { COMMAND_GROUPS, matching, type Command, type SearchAnswer } from './commands';
import { worthSearching } from './search';

/** What the palette holds before anything has been asked. */
const UNASKED: SearchAnswer = { commands: [], partial: false };

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
 *
 * **It also asks the deployment.** The placeholder promised "Search resources,
 * runs, incidents" while the list held the navigation, the recent runs and one
 * action — so typing the name of a resource on the Resources screen answered
 * "Nothing matches that". The lookup is debounced, and every keystroke aborts
 * the request the last one started: a slow answer that arrives after somebody
 * has typed three more letters is an answer to a question they are no longer
 * asking, and rendering it would move the row out from under the Enter key.
 */

/**
 * How long a keystroke waits before the deployment is asked.
 *
 * Long enough that typing a resource name is one request rather than twelve,
 * short enough that it feels like the list is keeping up. Every request is
 * aborted by the next one regardless, so this is about the deployment's load
 * and not about correctness.
 */
export const SEARCH_DEBOUNCE_MS = 180;

export interface PaletteProps {
  readonly open: boolean;
  readonly locale: Locale;
  readonly commands: readonly Command[];
  readonly onClose: () => void;
  /** What running one does. Given in, so the palette itself navigates nothing. */
  readonly onRun: (command: Command) => void;
  /**
   * How the deployment is asked what answers to a query.
   *
   * Returns commands rather than records, because deciding which results this
   * viewer may see is a permission question and the palette is not where
   * permission is decided — the shell holds the viewer and does the same
   * filtering it does for the local commands. Injected so the suite can drive
   * it without a network. Absent, the palette is exactly what it used to be:
   * the navigation, the recent runs and the actions, matched locally.
   */
  readonly search?: (query: string, signal: AbortSignal) => Promise<SearchAnswer>;
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
  search,
}: Omit<PaletteProps, 'open'>): ReactNode {
  const [query, setQuery] = useState('');
  const [highlighted, setHighlighted] = useState(0);
  // Kept with the question it answers, and read back only when the two still
  // agree. That is what makes a stale answer unrenderable rather than merely
  // unlikely: an answer to "sig" cannot appear under "signoz-col" even if it
  // arrives late, and clearing the results when somebody deletes back to one
  // character needs no second state write.
  const [answered, setAnswered] = useState<{
    readonly query: string;
    readonly answer: SearchAnswer;
  }>({ query: '', answer: UNASKED });
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const titleId = useId();

  const results = answered.query === query.trim() ? answered.answer : UNASKED;

  // Ask the deployment once the typing settles, and abandon the answer to the
  // previous question. Both halves matter: without the delay this is a request
  // per keystroke, and without the abort a slow answer lands under somebody's
  // Enter key after they have moved on.
  useEffect(() => {
    if (search === undefined || !worthSearching(query)) return;
    const asked = query.trim();
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void search(asked, controller.signal)
        .then((answer) => {
          if (!controller.signal.aborted) setAnswered({ query: asked, answer });
        })
        .catch(() => {
          // A search that could not be run finds nothing, and says so by
          // showing the local commands alone. It is not an error state: the
          // palette's other half still works, and a dialog about it would be
          // in the way of the navigation somebody can still use.
          if (!controller.signal.aborted) {
            setAnswered({ query: asked, answer: UNASKED });
          }
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, search]);

  const shown = useMemo(
    () => [...results.commands, ...matching(commands, query)],
    [commands, query, results],
  );

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
            {message(
              locale,
              results.partial ? 'palette.empty.partial' : 'palette.empty',
            )}
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
