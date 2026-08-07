"""What the destination of this output can actually render.

Three independent questions, each answered from the stream and the environment
rather than assumed:

- **Is anybody watching?** A pipe is not a terminal, so progress that overwrites
  its own line becomes a file full of escape sequences.
- **Can it show colour?** ``NO_COLOR`` is honoured whatever its value, because
  that is the convention's whole point; ``FORCE_COLOR`` is honoured even when
  piped, because a CI log is captured through a pipe and still renders ANSI.
- **Can it encode the glyphs?** Asked of the stream's encoding rather than
  guessed from the locale, and answered by trying to encode the glyphs that
  would be used.

Everything downstream renders against a ``Terminal``, so "what does this look
like on a bad terminal" is a test that constructs one rather than a terminal
somebody has to find.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from typing import IO, Any, ClassVar, Final

from config.constants.surfaces import (
    COLUMNS_ENV,
    DEFAULT_TERMINAL_WIDTH,
    FORCE_COLOR_ENV,
    MINIMUM_TABLE_WIDTH,
    NINJASRE_NO_COLOR_ENV,
    NO_COLOR_ENV,
    TERM_DUMB,
    TERM_ENV,
)

#: The glyphs a rendered line may use, by what they mean rather than by what
#: they look like. Two sets with the same keys, so choosing between them is one
#: decision taken once rather than a conditional at every call site.
UNICODE_GLYPHS: Final[Mapping[str, str]] = {
    "ok": "✓",
    "failed": "✗",
    "warning": "⚠",
    "pending": "…",
    "bullet": "•",
    "arrow": "→",
    "ellipsis": "…",
    "vertical": "│",
    "horizontal": "─",
    "branch": "├",
    "corner": "└",
    "spinner": "⠋",
}

ASCII_GLYPHS: Final[Mapping[str, str]] = {
    "ok": "OK",
    "failed": "X",
    "warning": "!",
    "pending": "..",
    "bullet": "*",
    "arrow": "->",
    "ellipsis": "...",
    "vertical": "|",
    "horizontal": "-",
    "branch": "+",
    "corner": "\\",
    "spinner": "-",
}


@dataclass(frozen=True, slots=True)
class Terminal:
    """What one output stream can render, decided once and passed around."""

    #: Below this a rendered line stops being a line. A terminal reporting less
    #: is reporting nonsense — a resize race, a pty with no size set — and
    #: honouring it would produce a column of single characters.
    FLOOR_WIDTH: ClassVar[int] = 20

    width: int = DEFAULT_TERMINAL_WIDTH
    colour: bool = False
    unicode: bool = False
    interactive: bool = False
    piped: bool = True

    @property
    def narrow(self) -> bool:
        """Return whether this is too narrow for a table to be readable."""
        return self.width < MINIMUM_TABLE_WIDTH

    @property
    def glyphs(self) -> Mapping[str, str]:
        """Return the glyph set this terminal can encode."""
        return UNICODE_GLYPHS if self.unicode else ASCII_GLYPHS

    def glyph(self, name: str) -> str:
        """Return the glyph meaning ``name``, in whichever set applies."""
        return self.glyphs[name]

    @property
    def animates(self) -> bool:
        """Return whether output may overwrite a line it already wrote.

        A pipe cannot. Neither can a terminal with no capabilities, which is
        what ``TERM=dumb`` means and why it is folded in here rather than
        checked separately by every progress renderer.
        """
        return self.interactive and not self.piped


#: A terminal that can do nothing. What the CLI renders against when it is
#: writing to a file, and the fixture every degradation test starts from.
PLAIN: Final = Terminal()


def _is_set(environ: Mapping[str, str], name: str) -> bool:
    """Return whether ``name`` is present, whatever it is set to.

    Presence is the signal for ``NO_COLOR`` and ``FORCE_COLOR`` by convention,
    so ``NO_COLOR=0`` still disables colour. Surprising once, and the
    alternative — every tool inventing its own truthiness — is the reason the
    convention exists.
    """
    return name in environ


def _encodable(sample: str, encoding: str) -> bool:
    """Return whether ``encoding`` can carry ``sample``."""
    try:
        sample.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _stream_encoding(stream: IO[str] | Any) -> str:
    """Return the stream's encoding, defaulting to the safe answer."""
    encoding = getattr(stream, "encoding", None)
    return encoding if isinstance(encoding, str) and encoding else "ascii"


def _stream_is_tty(stream: IO[str] | Any) -> bool:
    """Return whether ``stream`` claims to be a terminal.

    A stream that cannot answer is not one: a closed or wrapped stream raising
    from ``isatty`` is exactly the case where assuming a terminal would write
    escape sequences into something that will never interpret them.
    """
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def _width(environ: Mapping[str, str], *, interactive: bool) -> int:
    """Return the width to render at."""
    if not interactive:
        # A pipe has no width. Guessing the developer's terminal produces a log
        # file wrapped to a size nothing that reads it shares.
        return DEFAULT_TERMINAL_WIDTH

    columns = environ.get(COLUMNS_ENV, "")
    if columns.strip().isdigit():
        return max(int(columns), Terminal.FLOOR_WIDTH)

    return max(shutil.get_terminal_size((DEFAULT_TERMINAL_WIDTH, 24)).columns, Terminal.FLOOR_WIDTH)


def detect(
    *,
    stream: IO[str] | Any,
    environ: Mapping[str, str] | None = None,
) -> Terminal:
    """Return what ``stream`` can render, given ``environ``.

    Pure over its two arguments apart from the terminal-size probe, so a test
    describes a terminal by passing one rather than by finding one.
    """
    env = dict(environ if environ is not None else os.environ)

    interactive = _stream_is_tty(stream)
    term = env.get(TERM_ENV, "")
    dumb = term == TERM_DUMB

    forced = _is_set(env, FORCE_COLOR_ENV)
    refused = _is_set(env, NO_COLOR_ENV) or _is_set(env, NINJASRE_NO_COLOR_ENV)
    colour = not refused and not dumb and (forced or interactive)

    sample = "".join(sorted(set("".join(UNICODE_GLYPHS.values()))))
    unicode_ok = not dumb and _encodable(sample, _stream_encoding(stream))

    return Terminal(
        width=_width(env, interactive=interactive),
        colour=colour,
        unicode=unicode_ok,
        interactive=interactive,
        piped=not interactive,
    )


__all__ = [
    "ASCII_GLYPHS",
    "PLAIN",
    "UNICODE_GLYPHS",
    "Terminal",
    "detect",
]
