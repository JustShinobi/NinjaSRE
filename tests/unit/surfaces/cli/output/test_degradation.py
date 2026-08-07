"""What the CLI decides about a terminal before it renders anything.

The assertion behind readable-anywhere: readable at 80 columns, without colour,
and when piped. Each of the three is a separate decision here, taken from the
stream and the environment rather than assumed, because the terminal somebody is
holding at 03:00 is not the one the developer wrote the code in.
"""

from __future__ import annotations

import io

import pytest

from config.constants.surfaces import (
    DEFAULT_TERMINAL_WIDTH,
    FORCE_COLOR_ENV,
    MINIMUM_TABLE_WIDTH,
    NINJASRE_NO_COLOR_ENV,
    NO_COLOR_ENV,
    TERM_DUMB,
    TERM_ENV,
)
from surfaces.cli.output.degradation import ASCII_GLYPHS, UNICODE_GLYPHS, Terminal, detect

pytestmark = pytest.mark.unit


class _Stream(io.StringIO):
    """A writable stream that can claim to be a terminal, or not."""

    def __init__(self, *, tty: bool, encoding: str = "utf-8") -> None:
        super().__init__()
        self._tty = tty
        self._encoding = encoding

    def isatty(self) -> bool:
        return self._tty

    @property
    def encoding(self) -> str:
        return self._encoding


def test_a_piped_stream_is_not_interactive_and_gets_no_colour() -> None:
    terminal = detect(stream=_Stream(tty=False), environ={})

    assert terminal.piped
    assert not terminal.interactive
    assert not terminal.colour


def test_a_piped_stream_falls_back_to_the_default_width() -> None:
    # A pipe has no width. Guessing the developer's terminal would produce a log
    # file wrapped to a size nothing that reads it shares.
    terminal = detect(stream=_Stream(tty=False), environ={"COLUMNS": "220"})

    assert terminal.width == DEFAULT_TERMINAL_WIDTH


def test_a_terminal_reports_its_own_width() -> None:
    terminal = detect(
        stream=_Stream(tty=True), environ={"COLUMNS": "132", "TERM": "xterm-256color"}
    )

    assert terminal.width == 132
    assert terminal.interactive


def test_no_color_is_honoured_whatever_its_value() -> None:
    # no-color.org: presence is the signal, not the value. An empty string is a
    # value somebody deliberately exported.
    for value in ("1", "", "0", "false"):
        terminal = detect(
            stream=_Stream(tty=True),
            environ={NO_COLOR_ENV: value, TERM_ENV: "xterm-256color"},
        )
        assert not terminal.colour, f"NO_COLOR={value!r} should have disabled colour"


def test_the_platforms_own_switch_disables_colour_too() -> None:
    terminal = detect(
        stream=_Stream(tty=True),
        environ={NINJASRE_NO_COLOR_ENV: "1", TERM_ENV: "xterm-256color"},
    )

    assert not terminal.colour


def test_a_dumb_terminal_gets_neither_colour_nor_unicode() -> None:
    terminal = detect(stream=_Stream(tty=True), environ={TERM_ENV: TERM_DUMB})

    assert not terminal.colour
    assert not terminal.unicode


def test_force_color_wins_over_being_piped() -> None:
    # CI systems capture output through a pipe and still render ANSI. Refusing
    # colour there would be correct by the rule and wrong in the log.
    terminal = detect(stream=_Stream(tty=False), environ={FORCE_COLOR_ENV: "1"})

    assert terminal.colour
    assert terminal.piped


def test_no_color_beats_force_color() -> None:
    terminal = detect(
        stream=_Stream(tty=True),
        environ={FORCE_COLOR_ENV: "1", NO_COLOR_ENV: "1", TERM_ENV: "xterm"},
    )

    assert not terminal.colour


def test_an_encoding_that_cannot_carry_the_glyphs_disables_unicode() -> None:
    terminal = detect(stream=_Stream(tty=True, encoding="ascii"), environ={TERM_ENV: "xterm"})

    assert not terminal.unicode
    assert terminal.glyphs is ASCII_GLYPHS


def test_a_utf8_terminal_gets_the_unicode_glyphs() -> None:
    terminal = detect(stream=_Stream(tty=True, encoding="utf-8"), environ={TERM_ENV: "xterm"})

    assert terminal.unicode
    assert terminal.glyphs is UNICODE_GLYPHS


def test_every_ascii_glyph_encodes_as_ascii() -> None:
    # The point of the fallback set: it survives the encoding that caused the
    # fallback. A glyph that raised here would break the very terminal it exists
    # for.
    for name, glyph in ASCII_GLYPHS.items():
        glyph.encode("ascii"), name


def test_the_two_glyph_sets_cover_the_same_names() -> None:
    assert set(ASCII_GLYPHS) == set(UNICODE_GLYPHS)


def test_a_narrow_terminal_is_reported_as_narrow() -> None:
    narrow = Terminal(width=MINIMUM_TABLE_WIDTH - 1)
    wide = Terminal(width=MINIMUM_TABLE_WIDTH)

    assert narrow.narrow
    assert not wide.narrow


def test_a_width_below_the_floor_is_raised_to_it() -> None:
    # A terminal reporting 3 columns is a terminal reporting nonsense. Rendering
    # into it would produce a column of single characters.
    terminal = detect(stream=_Stream(tty=True), environ={"COLUMNS": "3", TERM_ENV: "xterm"})

    assert terminal.width >= Terminal.FLOOR_WIDTH
