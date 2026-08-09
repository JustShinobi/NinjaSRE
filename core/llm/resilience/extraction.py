"""Reading the call a model plainly meant out of the shape it wrote it in.

A small model asked to call a tool frequently writes the call instead: as a bare
JSON object, inside a Markdown fence, with ``tool``/``parameters`` where the
provider expects ``name``/``arguments``. The intent is unambiguous and the
provider adapter has nothing to hand the runtime, so the turn is lost to a
formatting difference.

The line this module lives on is the whole feature, so it is worth stating
plainly. **Extracting the call the model wrote is resilience. Supplying an
argument it did not write is invention**, and invention produces a capability
run with parameters nobody chose, which is evidence of nothing.

That line is enforced rather than intended. ``_verified_call`` is the only place
in this entire package where a :class:`~core.llm.types.ToolCall` is constructed,
and it refuses any argument value whose JSON text does not appear in the model's
own output. A test walks the package's syntax tree and asserts that no other
construction site exists, so the guarantee survives the next person to add a
format to the recognised set.

The recognised set is deliberately small. A parser for every model's quirks is a
maintenance surface that grows forever and starts guessing; what is not
recognised is refused with a correction, and the model gets a chance to say it
again properly.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.llm.structured.prose_parsing import parse_prose
from core.llm.types import ToolCall, ToolSchema

#: Where a tool call may be constructed, as ``module:function``. The structural
#: test reads this rather than hard-coding the name, so moving the function is a
#: one-line change and deleting the guard is not.
SOLE_CONSTRUCTION_SITE = "extraction.py:_verified_call"

#: The keys a model uses for the capability's name, in the order they are tried.
_NAME_KEYS = ("name", "tool", "tool_name", "function")

#: And for its arguments. ``input`` is Anthropic's spelling, which local models
#: trained on its transcripts reproduce.
_ARGUMENT_KEYS = ("arguments", "parameters", "args", "input", "parameter")

_FENCE = re.compile(r"```(?:json|JSON)?\s*(?P<body>.*?)```", re.DOTALL)


class InventedValueError(ValueError):
    """An argument value that is not in the model's output.

    Raised rather than dropped. A value nobody can point at in what the model
    wrote came from somewhere else, and the only correct response to discovering
    that is to refuse the whole call.
    """


@dataclass(frozen=True, slots=True)
class Extraction:
    """What could be read out of a model's prose.

    ``named`` carries a capability the text mentions when no call could be read
    from it. That is the difference between "the model said nothing" and "the
    model was clearly trying to call ``prometheus_query`` and its arguments were
    cut off mid-generation", and the correction for each is different.
    """

    call: ToolCall | None = None
    named: str = ""


def _leaves(value: Any) -> list[Any]:
    """Return every scalar inside ``value``, however deeply nested."""
    if isinstance(value, Mapping):
        found: list[Any] = []
        for key, item in value.items():
            found.append(key)
            found.extend(_leaves(item))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for item in value:
            found.extend(_leaves(item))
        return found
    return [value]


def verified_arguments(arguments: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    """Return ``arguments`` if every value in them appears in ``source``.

    The check is on the JSON text of each scalar, which is what makes it strict
    without being brittle: whitespace and key order may differ between the
    document the model wrote and the object parsed out of it, but the literal
    ``"checkout"`` cannot appear in the second unless it appeared in the first.

    Raises:
        InventedValueError: naming the first value that is not in ``source``.
    """
    for leaf in _leaves(arguments):
        rendered = json.dumps(leaf, ensure_ascii=False)
        if rendered not in source:
            raise InventedValueError(
                f"{rendered} is not in the model's output; nothing may be supplied for it"
            )
    return dict(arguments)


def _verified_call(
    name: str, arguments: Mapping[str, Any], *, source: str, call_id: str
) -> ToolCall:
    """Return the call ``source`` describes, or raise rather than invent one.

    The only place in this package a tool call is built. Every argument value is
    checked against the model's own output first, so a repair path that tried to
    fill in a default would fail here rather than reach a capability.
    """
    return ToolCall(id=call_id, name=name, arguments=verified_arguments(arguments, source=source))


def _documents(text: str) -> list[str]:
    """Return the substrings worth reading as a call, most likely first."""
    candidates: list[str] = []
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)
    for match in _FENCE.finditer(text):
        body = match.group("body").strip()
        if body:
            candidates.append(body)
    return candidates


def _named_and_arguments(document: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]] | None:
    """Return the capability and arguments ``document`` declares, if it declares them."""
    name = next(
        (str(document[key]) for key in _NAME_KEYS if isinstance(document.get(key), str)), ""
    )
    if not name:
        return None
    arguments: Mapping[str, Any] = next(
        (dict(document[key]) for key in _ARGUMENT_KEYS if isinstance(document.get(key), Mapping)),
        {},
    )
    return name, arguments


def extract_tool_call(
    text: str,
    offered: Sequence[ToolSchema],
    *,
    call_id: str = "extracted-1",
) -> Extraction:
    """Return the call ``text`` contains, where it contains a recognisable one.

    A call is only recognised when it names a capability that was actually
    offered this turn. That single condition does most of the work: a model
    describing a hypothetical, quoting a log line, or reasoning about braces is
    not naming one of this turn's schemas, so nothing in its prose becomes a
    call. A name that was offered but whose arguments could not be read comes
    back as ``named``, for a correction that says which call failed.
    """
    if not text or not offered:
        return Extraction()

    names = {schema.name for schema in offered}

    for candidate in _documents(text):
        parsed = parse_prose(candidate)
        if parsed is None:
            continue
        declared = _named_and_arguments(parsed)
        if declared is None:
            continue
        name, arguments = declared
        if name not in names:
            continue
        try:
            return Extraction(call=_verified_call(name, arguments, source=text, call_id=call_id))
        except InventedValueError:
            return Extraction(named=name)

    mentioned = next((name for name in sorted(names) if name in text), "")
    return Extraction(named=mentioned)


def assemble_fragments(name: str, fragments: Sequence[str], *, call_id: str) -> ToolCall | None:
    """Return the call a streamed argument document adds up to, if it parses.

    Reassembly is not invention: every character came off the wire from the
    model, and the pieces are only meaningless because a stream cut them up.
    """
    source = "".join(fragments)
    parsed = parse_prose(source) if source.strip() else {}
    if parsed is None:
        return None
    try:
        return _verified_call(name, parsed, source=source, call_id=call_id)
    except InventedValueError:  # pragma: no cover — a parse cannot produce this
        return None


__all__ = [
    "SOLE_CONSTRUCTION_SITE",
    "Extraction",
    "InventedValueError",
    "assemble_fragments",
    "extract_tool_call",
    "verified_arguments",
]
