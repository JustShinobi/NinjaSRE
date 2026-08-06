"""What changed, as something a reviewer reads rather than a blob they scroll.

A structured diff, not a text one. The five change types have five shapes — a
configuration document is a tree of paths, a prompt is prose, a capability
toggle is a set — and rendering all five as unified text would make four of them
harder to read than the values they describe. A ``DiffLine`` carries the path,
what it was, and what it would become, and each renderer's job is to decide what
counts as a path.

**Every value passes the guardrail engine before it is rendered.** The diff is
shown to a reviewer and then retained in the audit trail, which is the one table
nobody may delete from. A credential somebody pasted into a configuration field
by mistake must not be preserved there for the retention period by the very
mechanism that was refusing to store it.

**A long value is reported, not printed.** Above the ceiling, a value is
rendered by its size and its fingerprint. Those are what a reviewer can actually
compare; ten kilobytes of certificate inline is a diff they scroll past.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final, Protocol, runtime_checkable

from config.constants.security import MAX_DIFF_VALUE_CHARS
from platform.approvals.models import ChangeType, fingerprint_of
from platform.guardrails.engine import GuardrailEngine


class DiffOperation(StrEnum):
    """What happened to one path."""

    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"

    @property
    def marker(self) -> str:
        """Return the character a rendered line starts with."""
        return _MARKERS[self]


_MARKERS: Final[Mapping[DiffOperation, str]] = {
    DiffOperation.ADDED: "+",
    DiffOperation.REMOVED: "-",
    DiffOperation.CHANGED: "~",
}

#: What a value renders as when there is not one. Distinct from the string
#: ``"None"``, which is what a configuration value of ``None`` renders as, and
#: the difference matters when the diff is what somebody is arguing about.
ABSENT: Final = "∅"


@dataclass(frozen=True, slots=True)
class DiffLine:
    """One path, and what would happen to it."""

    path: str
    operation: DiffOperation
    before: str = ABSENT
    after: str = ABSENT

    def render(self) -> str:
        """Return this line as one string a console or a chat message shows."""
        if self.operation is DiffOperation.ADDED:
            return f"+ {self.path}: {self.after}"
        if self.operation is DiffOperation.REMOVED:
            return f"- {self.path}: {self.before}"
        return f"~ {self.path}: {self.before} → {self.after}"

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this line."""
        return {
            "path": self.path,
            "operation": self.operation.value,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True, slots=True)
class DiffSection:
    """A named group of lines: one file, one field, one set of capabilities.

    Sections exist so a summary can drop whole ones and say which. Dropping
    individual lines from an undifferentiated list would produce a summary
    nobody can navigate back into.
    """

    title: str
    lines: tuple[DiffLine, ...] = field(default_factory=tuple)

    def __len__(self) -> int:
        """Return how many lines this section holds."""
        return len(self.lines)

    def render(self) -> tuple[str, ...]:
        """Return the section's heading followed by its lines."""
        return (f"{self.title}:", *(line.render() for line in self.lines))

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this section."""
        return {"title": self.title, "lines": [line.to_record() for line in self.lines]}


@dataclass(frozen=True, slots=True)
class StructuredDiff:
    """Everything one change would do, grouped and ready to render."""

    change_type: ChangeType
    sections: tuple[DiffSection, ...] = field(default_factory=tuple)

    @property
    def line_count(self) -> int:
        """Return how many changed paths this diff describes."""
        return sum(len(section) for section in self.sections)

    @property
    def is_empty(self) -> bool:
        """Return whether this change would alter nothing at all."""
        return self.line_count == 0

    def lines(self) -> tuple[DiffLine, ...]:
        """Return every line, in section order."""
        return tuple(line for section in self.sections for line in section.lines)

    def render(self) -> tuple[str, ...]:
        """Return the whole diff as lines of text."""
        return tuple(text for section in self.sections for text in section.render())

    def to_record(self) -> dict[str, Any]:
        """Return the stored form retained in the audit trail."""
        return {
            "change_type": self.change_type.value,
            "line_count": self.line_count,
            "sections": [section.to_record() for section in self.sections],
        }


@runtime_checkable
class DiffRenderer(Protocol):
    """How one change type turns a before and an after into sections."""

    def render(
        self, current: Mapping[str, Any], proposed: Mapping[str, Any]
    ) -> tuple[DiffSection, ...]:
        """Return the sections describing the move from ``current`` to ``proposed``."""


@dataclass(slots=True)
class DiffEngine:
    """Builds a structured diff for any change type, filtered on the way out.

    The guardrail engine is optional and defaults to the shipped ruleset. A
    caller that passed nothing would otherwise get an unfiltered diff, and
    "unfiltered by default" is the wrong direction for the one value that ends
    up in the audit trail.
    """

    renderers: Mapping[ChangeType, DiffRenderer]
    guardrails: GuardrailEngine | None = None

    def diff(
        self,
        change_type: ChangeType,
        current: Mapping[str, Any],
        proposed: Mapping[str, Any],
    ) -> StructuredDiff:
        """Return what moving from ``current`` to ``proposed`` would change."""
        renderer = self.renderers[change_type]
        sections = renderer.render(current, proposed)
        return StructuredDiff(
            change_type=change_type,
            sections=tuple(self._filtered(section) for section in sections if section.lines),
        )

    def _filtered(self, section: DiffSection) -> DiffSection:
        """Return ``section`` with every rendered value passed through the rules."""
        engine = self.guardrails if self.guardrails is not None else _default_engine()
        return DiffSection(
            title=section.title,
            lines=tuple(
                DiffLine(
                    path=line.path,
                    operation=line.operation,
                    before=engine.scan(line.before).text,
                    after=engine.scan(line.after).text,
                )
                for line in section.lines
            ),
        )


_SHARED_ENGINE: GuardrailEngine | None = None


def _default_engine() -> GuardrailEngine:
    """Return the shipped ruleset, built once.

    Once, because loading and compiling the ruleset per diff would put pattern
    compilation on the path of every queue listing, and the engine is
    stateless once built.
    """
    global _SHARED_ENGINE
    if _SHARED_ENGINE is None:
        _SHARED_ENGINE = GuardrailEngine()
    return _SHARED_ENGINE


def render_value(value: Any) -> str:
    """Return ``value`` as the string a diff line shows.

    Long values are described rather than printed: the length and a short
    fingerprint are what a reviewer compares, and the alternative — a truncation
    that looks like the whole value — is the thing this feature exists to avoid
    doing to a *diff*, so it must not be done to a value either.
    """
    if value is None:
        return ABSENT
    rendered = value if isinstance(value, str) else _canonical(value)
    if len(rendered) <= MAX_DIFF_VALUE_CHARS:
        return rendered
    digest = fingerprint_of(value)[:12]
    return f"<{len(rendered)} characters, fingerprint {digest}>"


def _canonical(value: Any) -> str:
    """Return a non-string value as the text a diff line shows."""
    if isinstance(value, Mapping):
        inner = ", ".join(f"{key}={render_value(item)}" for key, item in sorted(value.items()))
        return f"{{{inner}}}"
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return f"[{', '.join(render_value(item) for item in value)}]"
    return str(value)


__all__ = [
    "ABSENT",
    "DiffEngine",
    "DiffLine",
    "DiffOperation",
    "DiffRenderer",
    "DiffSection",
    "StructuredDiff",
    "render_value",
]
