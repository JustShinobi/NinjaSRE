"""``<server>__<tool>``, and why that is the spelling.

The point of namespacing a bridged tool is that a third-party server must not be
able to shadow a native capability — an operator who installs a community server
called ``kubernetes`` should not find that the agent's ``kubernetes_restart_pod``
now reaches somewhere else. Two collisions have to be ruled out and they are
ruled out by different arguments.

**Between two bridged tools.** A server name may not contain the separator, so
``(server, tool)`` maps injectively onto the joined name: splitting on the first
separator recovers the pair, whatever the tool's own name contains.

**Between a bridged tool and a native one.** No native capability name contains
``__`` — every one of them is a single run of lowercase words. That is asserted
by a test against the shipped catalogue rather than assumed, because it is a
property of the names people write rather than one the type system holds.

The separator is underscores rather than the dot an operator would write. A dot
is not in ``TOOL_NAME_PATTERN``, and more importantly every provider's schema
normaliser would rewrite it to an underscore on the way to the model — leaving a
trace whose tool name matches no declaration, which is precisely the failure the
tool-name rules exist to prevent. So the operator-facing *qualified* name keeps
the dot, the callable name does not, and one function produces each.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Final

from config.constants.protocols import (
    PROTOCOL_NAMESPACE_SEPARATOR,
    PROTOCOL_QUALIFIED_SEPARATOR,
    PROTOCOL_SERVER_NAME_PATTERN,
)

_SERVER_NAME = re.compile(PROTOCOL_SERVER_NAME_PATTERN)

#: Anything a tool name may not carry into the catalogue, replaced with ``_``.
#: A server names its tools to suit itself; the catalogue has a grammar.
_UNSAFE_IN_TOOL_NAME: Final = re.compile(r"[^a-z0-9_]")

#: How many hex characters stand in for a tool name that cleaned to nothing.
#: Enough that two different unprintable names do not become one tool.
_DIGEST_LENGTH: Final[int] = 8


class InvalidServerName(ValueError):
    """A registered server's name is not one a bridged tool name can be built from."""


@dataclass(frozen=True, slots=True)
class BridgedName:
    """The server and tool a catalogue name was built from."""

    server: str
    tool: str

    @property
    def qualified(self) -> str:
        """Return the operator-facing ``<server>.<tool>``."""
        return qualified_name(self.server, self.tool)

    @property
    def catalogue(self) -> str:
        """Return the name the model calls."""
        return catalogue_name(self.server, self.tool)


def validate_server_name(server: str) -> str:
    """Return ``server`` unchanged, or raise ``InvalidServerName``.

    Validated rather than cleaned. A server name is written by an operator in
    configuration, and silently rewriting it would mean the name they classify
    against is not the name they typed.
    """
    if PROTOCOL_NAMESPACE_SEPARATOR in server:
        raise InvalidServerName(
            f"{server!r} contains {PROTOCOL_NAMESPACE_SEPARATOR!r}, which joins a server "
            f"to its tools — a server name carrying one would make two different tools "
            f"share a catalogue name"
        )
    if not _SERVER_NAME.match(server):
        raise InvalidServerName(
            f"{server!r} is not a server name: it must match "
            f"{PROTOCOL_SERVER_NAME_PATTERN} so that <server>{PROTOCOL_NAMESPACE_SEPARATOR}"
            f"<tool> is still a legal capability name"
        )
    return server


def clean_tool_name(tool: str) -> str:
    """Return ``tool`` in the grammar a catalogue name is built from.

    A name that cleans away to nothing becomes a digest of the original rather
    than a shared placeholder: two unprintable names must not arrive as one
    tool, because the model would then call one of them and reach the other.
    """
    cleaned = _UNSAFE_IN_TOOL_NAME.sub("_", tool.strip().lower()).strip("_")
    cleaned = re.sub(r"_{3,}", "__", cleaned)
    if not cleaned:
        digest = hashlib.sha256(tool.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
        return f"tool_{digest}"
    return cleaned


def catalogue_name(server: str, tool: str) -> str:
    """Return the name the model calls this bridged tool by."""
    return f"{validate_server_name(server)}{PROTOCOL_NAMESPACE_SEPARATOR}{clean_tool_name(tool)}"


def qualified_name(server: str, tool: str) -> str:
    """Return the name an operator reads and classifies against.

    The tool's own spelling is preserved here. An operator classifying
    ``deploys.Roll-Out`` should see what the server called it, not what the
    catalogue had to rename it to.
    """
    return f"{server}{PROTOCOL_QUALIFIED_SEPARATOR}{tool}"


def is_bridged_name(name: str) -> bool:
    """Return whether ``name`` is one this module could have produced."""
    return parse_catalogue_name(name) is not None


def parse_catalogue_name(name: str) -> BridgedName | None:
    """Return the pair ``name`` was built from, or ``None`` if it is not bridged.

    Split on the *first* separator. The server may not contain one and a tool
    may, so the first occurrence is always the join.
    """
    server, separator, tool = name.partition(PROTOCOL_NAMESPACE_SEPARATOR)
    if not separator or not tool:
        return None
    if not _SERVER_NAME.match(server):
        return None
    return BridgedName(server=server, tool=tool)


__all__ = [
    "BridgedName",
    "InvalidServerName",
    "catalogue_name",
    "clean_tool_name",
    "is_bridged_name",
    "parse_catalogue_name",
    "qualified_name",
    "validate_server_name",
]
