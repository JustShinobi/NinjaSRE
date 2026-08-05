"""The two shapes the catalogue holds, and the one thing they have in common.

A tool executes and a skill instructs. They are different enough that merging
them would produce a type that is half empty whichever one you have — and
similar enough that discovery, scoring, selection, and the console must treat
them as one list, because the question "what is relevant to this incident" does
not care which kind the answer is.

So: one supertype for the part selection reads, and two protocols for the parts
only their own callers touch.

Structural typing rather than inheritance is deliberate. A tool declared by
decorator, a tool declared as a class, and a tool bridged in from a remote
protocol server share no base class and never will, but all three satisfy
``Tool`` — which is the only thing the loop needs of them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from core.capability.metadata import CapabilityMetadata, SkillMetadata, ToolMetadata
from core.capability.result import CapabilityResult


@runtime_checkable
class Capability(Protocol):
    """Anything the catalogue can hold, score, and offer for selection."""

    @property
    def metadata(self) -> CapabilityMetadata:
        """Return the declaration this capability is scored and gated on."""


@runtime_checkable
class Tool(Protocol):
    """A typed execution unit.

    ``invoke`` returns a result rather than raising, including when the
    underlying call failed. That is not a style preference: the loop reasons
    about the returned classification, and an exception would take the turn and
    the trace with it.
    """

    @property
    def metadata(self) -> ToolMetadata:
        """Return the declaration this tool is scored, gated, and approved on."""

    @property
    def input_schema(self) -> Mapping[str, Any]:
        """Return the JSON Schema the model fills in to call this tool."""

    @property
    def output_schema(self) -> Mapping[str, Any]:
        """Return the JSON Schema describing what a successful call returns."""

    async def invoke(self, arguments: Mapping[str, Any]) -> CapabilityResult:
        """Return the outcome of one call, with failure classified rather than raised."""


@runtime_checkable
class Skill(Protocol):
    """A methodology document with a cheap index entry and an expensive body.

    ``body`` is a method rather than an attribute because that is what makes
    progressive disclosure real. An attribute would be read whenever anything
    inspected the object — a repr in a debugger, a serialisation for the console
    — and the catalogue would quietly cost what it costs to load every skill.
    """

    @property
    def metadata(self) -> SkillMetadata:
        """Return the index entry: everything paid for on every turn."""

    def body(self) -> str:
        """Return the methodology text, read from disk the first time it is asked for."""


__all__ = [
    "Capability",
    "Skill",
    "Tool",
]
