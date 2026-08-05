"""What this team can run, as the investigation holds it.

The capability layer resolves a team's catalogue; this is the pipeline's copy
of the answer, and it exists because state has to be two things at once.

**Runnable.** ``tools`` and ``metadata`` are live handles: the gathering stage
hands them to the runtime and the planning stage scores them.

**Writable down.** A trace that cannot be replayed offline is a summary of an
investigation rather than evidence of one, and a tool handle does not
round-trip through JSON.

So the record carries the names and the exclusions and not the handles, and
``from_record`` says so: a replayed catalogue describes what the run had, and
is deliberately not something a second run can execute from. The alternative —
serialising schemas into the trace — would make every stored investigation
carry a copy of the catalogue it ran against, and the catalogue is the largest
thing in the process.

The exclusions are the part worth keeping either way. "Datadog tools: 14
available, 6 excluded (no Splunk integration)" is a sentence an operator can
act on; an absence is not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.capability.metadata import CapabilityKind, CapabilityMetadata, ExcludedCapability
from core.capability.registered import RegisteredTool


@dataclass(frozen=True, slots=True)
class ResolvedCapabilities:
    """The team's catalogue, with what was left out and why."""

    available: tuple[str, ...] = ()
    excluded: tuple[ExcludedCapability, ...] = ()
    tools: tuple[RegisteredTool, ...] = ()
    metadata: tuple[CapabilityMetadata, ...] = ()

    def __len__(self) -> int:
        """Return how many capabilities this team can run."""
        return len(self.available)

    def __bool__(self) -> bool:
        """Return whether this team can run anything at all."""
        return bool(self.available)

    def tool(self, name: str) -> RegisteredTool | None:
        """Return the available tool called ``name``, or ``None``."""
        return next((found for found in self.tools if found.name == name), None)

    def exclusion(self, name: str) -> ExcludedCapability | None:
        """Return why ``name`` is unavailable to this team, if it is."""
        return next((found for found in self.excluded if found.name == name), None)

    def missing_integrations(self) -> tuple[str, ...]:
        """Return every integration an excluded capability needed, most-wanted first.

        This is what makes the zero-integration outcome specific. "Connect an
        integration" is not actionable; "eleven capabilities are waiting on
        Datadog and four on Loki" is.
        """
        counts: dict[str, int] = {}
        for excluded in self.excluded:
            for name in excluded.unmet:
                counts[name] = counts.get(name, 0) + 1
        return tuple(sorted(counts, key=lambda name: (-counts[name], name)))

    def blocked_by(self, integration: str) -> tuple[str, ...]:
        """Return the capabilities ``integration`` would make available, in name order."""
        return tuple(
            sorted(excluded.name for excluded in self.excluded if integration in excluded.unmet)
        )

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record: the names and the exclusions."""
        return {
            "available": list(self.available),
            "excluded": [
                {
                    "name": excluded.name,
                    "kind": excluded.kind.value,
                    "unmet": list(excluded.unmet),
                }
                for excluded in self.excluded
            ],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ResolvedCapabilities:
        """Return the catalogue a stored record describes, without the handles.

        A replayed catalogue is a description of what the run had. It is not
        runnable, on purpose: reconstructing tool handles from a trace would
        mean the trace decided which code executes.
        """
        return cls(
            available=tuple(str(item) for item in record.get("available") or ()),
            excluded=tuple(
                ExcludedCapability(
                    name=str(item["name"]),
                    kind=CapabilityKind(item["kind"]),
                    unmet=tuple(str(name) for name in item.get("unmet") or ()),
                )
                for item in record.get("excluded") or ()
            ),
        )

    @classmethod
    def of(
        cls,
        tools: Sequence[RegisteredTool],
        metadata: Sequence[CapabilityMetadata],
        excluded: Sequence[ExcludedCapability] = (),
    ) -> ResolvedCapabilities:
        """Return the catalogue holding ``tools`` and ``metadata``, names derived."""
        return cls(
            available=tuple(entry.name for entry in metadata),
            excluded=tuple(excluded),
            tools=tuple(tools),
            metadata=tuple(metadata),
        )


#: What a team with nothing configured has.
NO_CAPABILITIES: ResolvedCapabilities = ResolvedCapabilities()


__all__ = [
    "NO_CAPABILITIES",
    "ResolvedCapabilities",
]
