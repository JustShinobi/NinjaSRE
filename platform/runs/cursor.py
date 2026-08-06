"""A client's position in one run's event stream.

One integer and a run id, and both halves matter. The integer alone would be
ambiguous across runs — sequences restart per run, which is what stops two busy
investigations contending on one counter — and a client that presented a
position from a different run would silently receive the wrong backlog.

Serialised as a string because that is how it travels: an SSE ``Last-Event-ID``
header, a query parameter, a field in a WebSocket resume frame. Parsing is
strict and unparseable input raises rather than defaulting to the beginning of
the stream: a client whose cursor was mangled and which then received the whole
run again would look like it was working.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Separates the run from the position. Neither half may contain it, and a run
#: id is an opaque identifier the platform itself generates, so it does not.
_SEPARATOR = ":"


class CursorError(ValueError):
    """A cursor string is not one."""


@dataclass(frozen=True, slots=True, order=True)
class Cursor:
    """Where one subscriber has got to in one run's log."""

    run_id: str
    position: int

    def __post_init__(self) -> None:
        if not self.run_id:
            raise CursorError("A cursor needs the run it is a position within.")
        if _SEPARATOR in self.run_id:
            raise CursorError(f"A run id may not contain {_SEPARATOR!r}: {self.run_id!r}")
        if self.position < -1:
            raise CursorError(
                f"A position of {self.position} is before the start of the stream; "
                "-1 is what 'nothing seen yet' is spelled as."
            )

    @classmethod
    def start_of(cls, run_id: str) -> Cursor:
        """Return the cursor of a client that has seen nothing of ``run_id``."""
        return cls(run_id=run_id, position=-1)

    @classmethod
    def parse(cls, raw: str) -> Cursor:
        """Return the cursor ``raw`` encodes, or raise ``CursorError``."""
        run_id, separator, position = raw.rpartition(_SEPARATOR)
        if not separator:
            raise CursorError(f"A cursor is 'run-id{_SEPARATOR}position', not {raw!r}.")
        try:
            return cls(run_id=run_id, position=int(position))
        except ValueError as broken:
            raise CursorError(f"{position!r} is not a stream position.") from broken

    @property
    def after(self) -> int | None:
        """Return the exclusive lower bound this cursor reads from.

        ``None`` for a client that has seen nothing, because "everything after
        position -1" and "everything" are the same request and the store's
        signature says the second one with ``None``.
        """
        return None if self.position < 0 else self.position

    def advanced_to(self, position: int) -> Cursor:
        """Return this cursor moved forward to ``position``.

        Never backwards. A cursor that could move back is one a duplicated
        delivery could rewind, and the exactly-once property is precisely that
        this number only ever increases for a given subscriber.
        """
        return self if position <= self.position else Cursor(run_id=self.run_id, position=position)

    def __str__(self) -> str:
        """Return the wire form: ``run-id:position``."""
        return f"{self.run_id}{_SEPARATOR}{self.position}"


__all__ = ["Cursor", "CursorError"]
