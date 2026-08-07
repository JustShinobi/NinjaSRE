"""Reading a line, with history and completion, on whatever terminal is there.

``prompt_toolkit`` when the terminal supports it, and a plain ``input()`` when
it does not. Both are here because the fallback is not hypothetical: a container
exec, a serial console, and a Windows terminal in a mode prompt_toolkit refuses
are all places somebody has to be able to type an incident description.

Completion offers slash commands only. Completing free text would mean guessing
what somebody is about to describe, which is both useless and the beginning of
the intent-routing the REPL forbids — a completer that learned phrasings would
be a keyword table by another name.

History is a file on the operator's own host and holds what was typed. It
therefore holds incident descriptions, and it deliberately does not hold
credentials: nothing that reads a credential reads it through here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.constants.paths import state_dir
from config.constants.surfaces import (
    REPL_HISTORY_FILE_NAME,
    REPL_HISTORY_LIMIT,
    SLASH_COMMAND_PREFIX,
)
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: What the REPL shows before a line of input.
PROMPT = "ninjasre> "

#: Shown while an investigation is running and input is still accepted, so it is
#: visibly not the same state as an idle prompt.
BUSY_PROMPT = "…> "


def history_path() -> Path:
    """Return where REPL history is kept."""
    return state_dir() / REPL_HISTORY_FILE_NAME


class InputClosed(Exception):
    """Standard input ended. Ctrl+D, or a pipe that ran out.

    Distinct from an interrupt: Ctrl+D means "I am finished", and Ctrl+C means
    "stop what you are doing". Treating the first as the second would leave a
    session open with nobody attached to it.
    """


@dataclass(slots=True)
class Reader:
    """Reads one line at a time, however this terminal allows it."""

    completions: tuple[str, ...] = ()
    history_file: Path | None = None
    #: The prompt_toolkit session, when one could be built. Held as ``Any``
    #: because the fallback path must not require the library to be importable
    #: for this module to be.
    _session: Any = field(default=None, repr=False)
    _rich_terminal: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        self._build()

    def _build(self) -> None:
        """Try to build a rich reader, and fall back quietly when it is not possible."""
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.completion import WordCompleter
            from prompt_toolkit.history import FileHistory, InMemoryHistory
        except ImportError:
            logger.debug("repl.plain_reader", reason="prompt_toolkit is not installed")
            return

        try:
            history: Any
            if self.history_file is not None:
                self.history_file.parent.mkdir(parents=True, exist_ok=True)
                history = FileHistory(str(self.history_file))
            else:
                history = InMemoryHistory()

            self._session = PromptSession(
                history=history,
                completer=WordCompleter(
                    list(self.completions),
                    # Only after the prefix. A completer that fired on ordinary
                    # words would be suggesting commands to somebody describing
                    # an incident.
                    pattern=None,
                    sentence=False,
                ),
                complete_while_typing=False,
                enable_history_search=True,
            )
            self._rich_terminal = True
        except (OSError, ValueError) as failure:
            # A terminal prompt_toolkit will not drive. Not an error: the plain
            # reader below works everywhere, and refusing to start would make a
            # container exec unusable.
            logger.info("repl.plain_reader", reason=str(failure))
            self._session = None

    @property
    def rich(self) -> bool:
        """Return whether history and completion are available."""
        return self._rich_terminal

    def read(self, prompt: str = PROMPT) -> str:
        """Return one line of input.

        Raises:
            InputClosed: standard input ended.
            KeyboardInterrupt: the operator pressed Ctrl+C. Propagated rather
                than swallowed, because the loop is the thing that knows what
                is running and therefore what to cancel.
        """
        try:
            if self._session is not None:
                return str(self._session.prompt(prompt))
            return input(prompt)
        except EOFError as ended:
            raise InputClosed from ended

    def remember(self, line: str) -> None:
        """Add ``line`` to history without it having been typed.

        Used when a session is resumed, so the last thing somebody asked is one
        up-arrow away rather than something they have to retype.
        """
        if self._session is None or not line.strip():
            return
        self._session.history.append_string(line)


def build_reader(completions: Sequence[str], *, persist: bool = True) -> Reader:
    """Return a reader offering ``completions``, with history when asked for.

    ``persist`` is false in a test and in an ephemeral shell: writing a history
    file from a test run would put whatever the fixtures typed into the
    developer's own history.
    """
    return Reader(
        completions=tuple(completions),
        history_file=history_path() if persist else None,
    )


def trim_history(path: Path | None = None, *, limit: int = REPL_HISTORY_LIMIT) -> int:
    """Keep the history file to ``limit`` lines and return how many were dropped.

    Bounded because it grows for the life of an install and nothing else ever
    prunes it. A file that has been accumulating incident descriptions for two
    years is a file nobody meant to keep.
    """
    target = path or history_path()
    if not target.is_file():
        return 0
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= limit:
        return 0
    target.write_text("\n".join(lines[-limit:]) + "\n", encoding="utf-8")
    return len(lines) - limit


def looks_like_command(line: str) -> bool:
    """Return whether ``line`` starts with the slash prefix.

    Exposed for the reader's own prompt hinting only. **Routing does not use
    this** — ``surfaces.repl.routing`` is the single decision, and a second
    function that answered the same question is a second place somebody could
    make it answer differently.
    """
    return line.lstrip().startswith(SLASH_COMMAND_PREFIX)


__all__ = [
    "BUSY_PROMPT",
    "PROMPT",
    "InputClosed",
    "Reader",
    "build_reader",
    "history_path",
    "looks_like_command",
    "trim_history",
]
