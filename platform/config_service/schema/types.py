"""The field types every section is built from, and how a failure becomes an error.

Two jobs, both about making Pydantic report what an *operator* needs rather than
what a validator produces.

**Paths.** A ``ValidationError`` carries ``loc`` tuples — ``('agents',
'subagents', 0, 'name')`` — and everything else in this package speaks dotted
paths. ``field_errors`` converts them, rendering a list index as ``[0]`` so the
path reads the way the document was written.

**Bounds.** ``ConfiguredInt`` refuses a boolean where a number is expected.
Pydantic's lax mode reads ``True`` as ``1``, which would silently turn
``tool_budget: true`` into a budget of one, and a run that spent one tool call
because somebody typed the wrong thing is a run whose result means nothing. The
string coercions are deliberately left lax: a template written by hand says
``on`` and ``8`` at least once, and both are unambiguous.

**Help.** ``field_help`` and ``section_help`` declare the short, operator-facing
sentence a form shows, beside the field and the section it belongs to. The long
docstring stays where it is, for whoever is reading the schema; the two are
separate because they have different readers, and one text serving both readers
serves the operator badly.

Every section sets ``extra="forbid"``. That is what makes configuration a typed
surface rather than key-value storage that happens to have documented keys — a
typo in a field name is otherwise a setting that is stored, rendered in the
console, and never read.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from config.constants.config_service import MAX_CONFIG_LIST_ITEMS, MAX_CONFIG_STRING_CHARS
from platform.config_service.errors import FieldError

#: The message an undeclared key reports. Pydantic says "Extra inputs are not
#: permitted", which is true and says nothing about what to do; this says what
#: the operator got wrong.
UNDECLARED_FIELD_MESSAGE = "is not a configuration field"

#: Pydantic's own name for that failure.
_EXTRA_FORBIDDEN = "extra_forbidden"


def _reject_boolean(value: Any) -> Any:
    """Raise if ``value`` is a boolean where a number belongs."""
    if isinstance(value, bool):
        raise ValueError("expected a number, found true or false")
    return value


#: A whole number an operator configured. Bounded by the section that uses it.
ConfiguredInt = Annotated[int, BeforeValidator(_reject_boolean)]

#: A real number an operator configured.
ConfiguredFloat = Annotated[float, BeforeValidator(_reject_boolean)]

#: A string an operator configured, bounded so a pasted log file is refused
#: rather than stored. Prompts are the long ones and they fit comfortably.
ConfiguredStr = Annotated[str, Field(max_length=MAX_CONFIG_STRING_CHARS)]

#: A list of strings, bounded for the same reason.
ConfiguredStrList = Annotated[tuple[str, ...], Field(max_length=MAX_CONFIG_LIST_ITEMS)]


def field_help(text: str, **constraints: Any) -> Any:
    """Return a ``Field`` carrying ``text`` as the help a form puts under the control.

    The short, operator-facing half of a field's documentation, declared beside
    the field rather than in a table somewhere else. A table keyed by dotted
    path agrees with the schema on the day it is written; a keyword on the field
    moves when the field moves and disappears when the field does.

    It travels as ``json_schema_extra`` because that is the one channel Pydantic
    already carries into the generated document, which is what the field
    catalogue reads — so the help arrives by the same route as the type, the
    range and the default, and cannot be present for one and missing for the
    other. ``description`` is not that channel: it is where the docstring goes,
    and the docstring is the long text this exists to stop showing.

    Any further ``constraints`` are passed to ``Field`` unchanged, so a bounded
    field declares its bound and its help in one place.
    """
    return Field(json_schema_extra={"help": text}, **constraints)


def section_help(text: str) -> ConfigDict:
    """Return the model configuration that gives a section its operator-facing help.

    The class-level twin of ``field_help``, and the same argument: a section's
    long docstring is written for whoever is reading the schema, and a form
    needs one or two sentences written for whoever is filling it in.

    Declared as ``model_config`` because a section's own text belongs to the
    section rather than to any field on it, and Pydantic merges configuration
    down the class hierarchy — so a section that sets this keeps the closed,
    frozen behaviour ``ConfigSection`` declares.
    """
    return ConfigDict(json_schema_extra={"help": text})


class ConfigSection(BaseModel):
    """The base every configuration section shares.

    ``frozen`` because an effective configuration is cached and handed to
    whatever asks; a section a caller could mutate is a cache entry that
    disagrees with the database. ``extra="forbid"`` is the closed schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    def declared(self) -> frozenset[str]:
        """Return the field names this section was explicitly given.

        The difference between "set to the default" and "not set", which the
        console shows and which ``ModelsConfig.bound_roles`` needs — a role
        nobody configured must not appear as though somebody had.
        """
        return frozenset(self.model_fields_set)


SectionT = TypeVar("SectionT", bound=ConfigSection)


def field_errors(invalid: ValidationError, prefix: str = "") -> tuple[FieldError, ...]:
    """Return ``invalid`` as field-level errors at dotted paths."""
    return tuple(
        FieldError(
            path=dotted(item["loc"], prefix),
            message=(
                UNDECLARED_FIELD_MESSAGE if item["type"] == _EXTRA_FORBIDDEN else str(item["msg"])
            ),
        )
        for item in invalid.errors()
    )


def dotted(loc: Sequence[str | int], prefix: str = "") -> str:
    """Return the dotted path a Pydantic ``loc`` names.

    A list index renders as ``[0]`` and attaches to the field before it, so
    ``('agents', 'subagents', 0, 'name')`` reads ``agents.subagents[0].name`` —
    the way the operator wrote it rather than the way the validator walked it.
    """
    text = prefix
    for entry in loc:
        if isinstance(entry, int):
            text += f"[{entry}]"
        elif text:
            text += f".{entry}"
        else:
            text = str(entry)
    return text


__all__ = [
    "UNDECLARED_FIELD_MESSAGE",
    "ConfigSection",
    "ConfiguredFloat",
    "ConfiguredInt",
    "ConfiguredStr",
    "ConfiguredStrList",
    "dotted",
    "field_errors",
    "field_help",
    "section_help",
]
