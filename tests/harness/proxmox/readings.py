"""The readings, produced by the shipped tools, over recorded API responses.

This is the half of the suite that catches a change to the *system* rather than
to a model. Nothing here is a stand-in: the investigation tools are the ones the
agent calls, the client underneath them is the real one, and the only thing
replaced is the hypervisor at the end of the wire. So a contributor who changes
the quorum tool's synthesis until it stops saying "quorum margin 0" fails the
scenario that declared that reading, in the change that caused it, by name.

Two properties fall out of doing it this way, and both are requirements.

**Reproducibility is free.** The recorded responses are a value, the tools are
pure over them, and there is no clock in the path — so the same scenario
produces the same readings on every machine and every run.

**Staleness is detectable.** A recording answering a path nothing requests any
more is a fixture that has rotted, and a suite that quietly stopped exercising it
would pass while testing less than it did last month. ``verify_fresh`` makes that
a loud failure rather than a slow decay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from tests.harness.proxmox.declaration import Scenario, ToolCall
from tests.support.proxmox import ClusterState, RecordedProxmox, investigating


class StaleFixture(Exception):
    """A scenario's recorded responses no longer match what the system asks for.

    Raised rather than scored around. A recording that has drifted from the API
    produces a suite that passes and tests nothing, which is strictly worse than
    one that fails: the second gets fixed.
    """

    def __init__(self, scenario_id: str, problem: str) -> None:
        self.scenario_id = scenario_id
        self.problem = problem
        super().__init__(f"{scenario_id}: {problem}")


@dataclass(frozen=True, slots=True)
class ToolReading:
    """What one investigation tool said, as the scenario's readings record it."""

    tool: str
    succeeded: bool
    summary: str
    value: Any = None
    detail: str = ""

    @property
    def text(self) -> str:
        """Return everything this reading said, as one searchable block.

        Sorted keys, so the same value renders identically whatever order the
        tool happened to build its mapping in — which is the difference between
        a reproducible reading and one that depends on a dictionary.
        """
        rendered = json.dumps(self.value, sort_keys=True, default=str)
        return f"{self.summary}\n{rendered}\n{self.detail}"

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a scored run retains (FR-019)."""
        return {
            "tool": self.tool,
            "succeeded": self.succeeded,
            "summary": self.summary,
            "value": self.value,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class Readings:
    """Everything the tools saw for one scenario, and what they failed to say."""

    scenario_id: str
    entries: tuple[ToolReading, ...] = ()
    #: Declared readings the tools did not produce. Non-empty means the corpus
    #: and the system have diverged, and the suite refuses to score against it.
    missing: tuple[str, ...] = ()
    #: Recorded responses nothing asked for. The other half of the same
    #: divergence, and the half that decays quietly.
    unused_fixtures: tuple[str, ...] = ()
    #: Every path the run actually requested, in request order, so a failure can
    #: show what was asked as well as what came back.
    requested: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        """Return every reading as one block, which is what assertions search."""
        return "\n".join(entry.text for entry in self.entries)

    @property
    def fresh(self) -> bool:
        """Return whether the corpus and the system still agree about this scenario."""
        return not self.missing and not self.unused_fixtures

    def to_record(self) -> dict[str, Any]:
        """Return the readings a scored run keeps beside its verdict."""
        return {
            "scenario": self.scenario_id,
            "entries": [entry.to_record() for entry in self.entries],
            "missing": list(self.missing),
            "unused_fixtures": list(self.unused_fixtures),
            "requested": list(self.requested),
        }


def _registered(name: str) -> Any:
    """Return the shipped registration for the tool called ``name``.

    Raises:
        StaleFixture: no tool of that name is shipped any more, which is a
            scenario naming something that has been renamed or removed.
    """
    from core.capability.registered import capability_marker
    from integrations.proxmox import tools as proxmox_tools

    function = getattr(proxmox_tools, name, None)
    if function is None:
        raise StaleFixture(
            name, f"{name!r} is not a Proxmox investigation tool this repository ships"
        )
    registered = capability_marker(function)
    if registered is None:  # pragma: no cover - a tool that lost its declaration
        raise StaleFixture(name, f"{name!r} is no longer declared as a capability")
    return registered


async def _run_tool(call: ToolCall) -> ToolReading:
    """Return what one tool said, whatever it said, including a failure."""
    registered = _registered(call.name)
    result = await registered.invoke(dict(call.arguments))
    # The one-sentence finding a tool wants an operator to read is on its
    # evidence rather than on the result, and it is the half of a reading a
    # scenario is most likely to assert against — a value can carry the number
    # while the sentence stops saying what it means.
    return ToolReading(
        tool=call.name,
        succeeded=result.succeeded,
        summary="\n".join(found.summary for found in result.evidence),
        value=result.value,
        detail=str(result.error.message) if result.error is not None else "",
    )


def _unused(scenario: Scenario, transport: RecordedProxmox) -> tuple[str, ...]:
    """Return the scenario's overlaid recordings that nothing requested."""
    asked = tuple(transport.seen)
    unused: list[str] = []
    for path in scenario.fixtures.responses:
        if not any(seen == path or seen.startswith(f"{path}?") for seen in asked):
            unused.append(path)
    return tuple(sorted(unused))


async def read(scenario: Scenario) -> Readings:
    """Return the readings the shipped tools produce for ``scenario``.

    Runs against the recorded cluster in the state the scenario names, with its
    own responses overlaid — so the scenario states the one or two readings it is
    about rather than restating a whole hypervisor.
    """
    state = ClusterState(scenario.fixtures.cluster_state)
    overlay = scenario.fixtures.overlaid()
    entries: list[ToolReading] = []

    with investigating(
        state, unreachable=scenario.fixtures.unreachable, responses=overlay
    ) as bench:
        for call in scenario.readings.tools:
            entries.append(await _run_tool(call))
        requested = tuple(bench.seen)
        unused = _unused(scenario, bench)

    produced = "\n".join(entry.text for entry in entries).lower()
    missing = tuple(
        needle for needle in scenario.readings.must_report if needle.lower() not in produced
    )
    return Readings(
        scenario_id=scenario.scenario_id,
        entries=tuple(entries),
        missing=missing,
        unused_fixtures=unused,
        requested=requested,
    )


def verify_fresh(readings: Readings) -> None:
    """Raise unless ``readings`` still match the corpus that declared them.

    NFR-004 in one function. A scenario that scores against a recording the
    system stopped asking for, or that no longer produces the reading its answer
    key rests on, is scoring against stale data — and finding that out from a
    slowly drifting number is finding it out too late.

    Raises:
        StaleFixture: the corpus and the shipped tools have diverged.
    """
    if readings.missing:
        raise StaleFixture(
            readings.scenario_id,
            f"the shipped investigation tools no longer report {list(readings.missing)}. The "
            f"readings they did produce were: {readings.text[:2000]}",
        )
    if readings.unused_fixtures:
        raise StaleFixture(
            readings.scenario_id,
            f"nothing requested the recorded responses for {list(readings.unused_fixtures)}; the "
            f"paths this run actually asked for were {list(readings.requested)}. Regenerate the "
            f"scenario's fixtures rather than scoring against a recording nobody reads.",
        )


__all__ = ["Readings", "StaleFixture", "ToolReading", "read", "verify_fresh"]
