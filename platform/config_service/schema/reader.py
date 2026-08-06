"""Reading a section out of an untyped mapping, one field-level error at a time.

Every section model is built from a mapping an operator wrote, and the two
things that matter about that are stated here rather than in each section.

**Errors accumulate; they do not raise.** A reader collects into a shared list
and returns the default for whatever it could not read, so one submission
reports every problem in the document. An operator fixing a configuration one
field per attempt stops using configuration.

**The schema is closed.** ``close`` reports every key the section did not
declare, which is what makes configuration a typed surface rather than
key-value storage that happens to have some documented keys. A typo in a field
name is otherwise a setting that is stored, shown in the console, and never
read — and nothing in the system can tell that apart from a field that is
working.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.config_service import (
    MAX_CONFIG_LIST_ITEMS,
    MAX_CONFIG_STRING_CHARS,
    PATH_SEPARATOR,
)
from platform.config_service.errors import FieldError

#: Values a boolean field accepts besides a real boolean. YAML and JSON both
#: reach here, and a template written by hand says ``on`` at least once.
_TRUE_TEXT = frozenset({"true", "yes", "on", "1"})
_FALSE_TEXT = frozenset({"false", "no", "off", "0"})


@dataclass(slots=True)
class Reader:
    """One mapping, the path it sits at, and the errors found reading it."""

    values: Mapping[str, Any]
    path: str = ""
    errors: list[FieldError] = field(default_factory=list)

    def child_path(self, key: str) -> str:
        """Return the full dotted path of ``key`` within this section."""
        return f"{self.path}{PATH_SEPARATOR}{key}" if self.path else key

    def fail(self, key: str, message: str) -> None:
        """Record a problem with ``key``."""
        self.errors.append(FieldError(path=self.child_path(key), message=message))

    def has(self, key: str) -> bool:
        """Return whether the operator set ``key`` at all."""
        return key in self.values

    def section(self, key: str) -> Reader:
        """Return a reader over the mapping at ``key``, empty if it is not one."""
        raw = self.values.get(key)
        if raw is None:
            return Reader(values={}, path=self.child_path(key), errors=self.errors)
        if not isinstance(raw, Mapping):
            self.fail(key, f"expected a section, found {_named(raw)}")
            return Reader(values={}, path=self.child_path(key), errors=self.errors)
        return Reader(values=raw, path=self.child_path(key), errors=self.errors)

    def string(
        self,
        key: str,
        default: str = "",
        *,
        allowed: Sequence[str] | None = None,
        max_chars: int = MAX_CONFIG_STRING_CHARS,
    ) -> str:
        """Return the string at ``key``, or ``default`` if it is absent or wrong."""
        raw = self.values.get(key)
        if raw is None:
            return default
        if not isinstance(raw, str):
            self.fail(key, f"expected text, found {_named(raw)}")
            return default
        if len(raw) > max_chars:
            self.fail(key, f"is {len(raw)} characters and the limit is {max_chars}")
            return default
        if allowed is not None and raw not in allowed:
            self.fail(key, f"must be one of {', '.join(allowed)}; found {raw!r}")
            return default
        return raw

    def optional_string(self, key: str, *, allowed: Sequence[str] | None = None) -> str | None:
        """Return the string at ``key``, or ``None`` if it is unset."""
        if not self.has(key) or self.values.get(key) is None:
            return None
        return self.string(key, allowed=allowed) or None

    def integer(
        self, key: str, default: int, *, minimum: int | None = None, maximum: int | None = None
    ) -> int:
        """Return the whole number at ``key``, bounded, or ``default``."""
        raw = self.values.get(key)
        if raw is None:
            return default
        if isinstance(raw, bool) or not isinstance(raw, int):
            self.fail(key, f"expected a whole number, found {_named(raw)}")
            return default
        return default if self._out_of_range(key, raw, minimum, maximum) else raw

    def number(
        self,
        key: str,
        default: float,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        """Return the number at ``key``, bounded, or ``default``."""
        raw = self.values.get(key)
        if raw is None:
            return default
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            self.fail(key, f"expected a number, found {_named(raw)}")
            return default
        return default if self._out_of_range(key, float(raw), minimum, maximum) else float(raw)

    def boolean(self, key: str, default: bool) -> bool:
        """Return the switch at ``key``, or ``default``.

        A mis-spelled value is an error rather than a silent ``False``. A switch
        that reads as off because somebody typed ``ture`` is an ablation
        reporting a result it never measured.
        """
        raw = self.values.get(key)
        if raw is None:
            return default
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            text = raw.strip().lower()
            if text in _TRUE_TEXT:
                return True
            if text in _FALSE_TEXT:
                return False
        self.fail(key, f"expected true or false, found {raw!r}")
        return default

    def strings(
        self, key: str, default: tuple[str, ...] = (), *, allowed: Sequence[str] | None = None
    ) -> tuple[str, ...]:
        """Return the list of strings at ``key``, or ``default``."""
        raw = self.values.get(key)
        if raw is None:
            return default
        if isinstance(raw, str) or not isinstance(raw, Sequence):
            self.fail(key, f"expected a list, found {_named(raw)}")
            return default
        if len(raw) > MAX_CONFIG_LIST_ITEMS:
            self.fail(key, f"has {len(raw)} entries and the limit is {MAX_CONFIG_LIST_ITEMS}")
            return default

        found: list[str] = []
        for index, item in enumerate(raw):
            if not isinstance(item, str):
                self.fail(f"{key}[{index}]", f"expected text, found {_named(item)}")
                continue
            if allowed is not None and item not in allowed:
                self.fail(f"{key}[{index}]", f"must be one of {', '.join(allowed)}")
                continue
            found.append(item)
        return tuple(found)

    def sections(self, key: str) -> tuple[Reader, ...]:
        """Return a reader per mapping in the list at ``key``."""
        raw = self.values.get(key)
        if raw is None:
            return ()
        if isinstance(raw, str) or not isinstance(raw, Sequence):
            self.fail(key, f"expected a list, found {_named(raw)}")
            return ()
        if len(raw) > MAX_CONFIG_LIST_ITEMS:
            self.fail(key, f"has {len(raw)} entries and the limit is {MAX_CONFIG_LIST_ITEMS}")
            return ()

        found: list[Reader] = []
        for index, item in enumerate(raw):
            if not isinstance(item, Mapping):
                self.fail(f"{key}[{index}]", f"expected a section, found {_named(item)}")
                continue
            found.append(
                Reader(
                    values=item,
                    path=f"{self.child_path(key)}[{index}]",
                    errors=self.errors,
                )
            )
        return tuple(found)

    def keyed_strings(self, key: str, *, keys: Sequence[str]) -> dict[str, str]:
        """Return the ``{name: text}`` mapping at ``key``, restricted to ``keys``."""
        section = self.section(key)
        section.close(keys)
        return {name: section.string(name) for name in keys if section.has(name)}

    def free_mapping(self, key: str) -> dict[str, Any]:
        """Return the mapping at ``key`` with its values uninspected.

        The one open door in the schema, and it is deliberately narrow: a
        capability's own parameters and an integration's vendor settings are
        defined by that capability and that integration, not here. Everything
        else is a declared field.
        """
        raw = self.values.get(key)
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            self.fail(key, f"expected a section, found {_named(raw)}")
            return {}
        return dict(raw)

    def close(self, known: Iterable[str]) -> None:
        """Report every key this section does not declare (FR-010)."""
        declared = set(known)
        for key in self.values:
            if key not in declared:
                self.fail(key, "is not a configuration field")

    def _out_of_range(
        self, key: str, value: float, minimum: float | None, maximum: float | None
    ) -> bool:
        if minimum is not None and value < minimum:
            self.fail(key, f"must be at least {minimum}; found {value}")
            return True
        if maximum is not None and value > maximum:
            self.fail(key, f"must be at most {maximum}; found {value}")
            return True
        return False


def _named(value: Any) -> str:
    """Return what a wrong-typed value is, for an error an operator can act on."""
    if isinstance(value, Mapping):
        return "a section"
    if isinstance(value, str):
        return "text"
    if isinstance(value, bool):
        return "true or false"
    if isinstance(value, Sequence):
        return "a list"
    return type(value).__name__


__all__ = ["Reader"]
