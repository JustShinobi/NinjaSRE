"""The scale scenario, generated from a seed rather than committed.

Ten thousand runs, ten thousand events, ten thousand resources and five hundred
configuration nodes come to tens of megabytes of JSON. Committing that would
breach the size budget on its own and would make every clone of this repository
pay for a scenario most contributors never open.

So it is generated, from a fixed seed, which gives the same property committing
it would have given: the tenth generation is the first one again, and a
performance measurement taken against it is comparable with one taken last
month.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Final

from config.constants.fixtures import (
    SCALE_CONFIG_NODE_COUNT,
    SCALE_EVENT_COUNT,
    SCALE_RESOURCE_COUNT,
    SCALE_RUN_COUNT,
    SCALE_SEED,
)
from tools.mockplane.dataset import served
from tools.mockplane.dataset.stream import LIVE_RUN
from tools.mockplane.records import CapturedRecord, Provenance, Request

_STATUSES: Final = ("succeeded", "failed", "cancelled", "running")
_KINDS: Final = ("container", "virtual-machine")
_STATES: Final = ("running", "stopped", "paused", "unknown")


def _pseudorandom(ordinal: int) -> int:
    """Return a stable pseudorandom number for ``ordinal``.

    A multiplicative congruential step rather than ``random``: it needs no
    global state, it is the same on every platform and every Python version, and
    a scenario that changed with the interpreter would not be a fixed point to
    measure against.
    """
    return (SCALE_SEED + ordinal * 2_654_435_761) % 2_147_483_647


def _record(slug: str, body: Any, arguments: dict[str, str] | None = None) -> CapturedRecord:
    return CapturedRecord(
        slug=slug,
        arguments=arguments or {},
        status=200,
        body=body,
        provenance=Provenance.GATEWAY,
        request=Request(method="GET", path=slug),
    )


def runs() -> list[dict[str, Any]]:
    """Return ten thousand runs, the scenario's own runs among them, newest first.

    The declared runs come first rather than being replaced. ``scale`` is the
    same deployment with more in it, not a parallel one: the approvals, the
    episodes and the audit trail underneath it name those runs, and a scenario
    that renumbered them would be a scenario where every reference was broken.
    """
    found: list[dict[str, Any]] = [dict(run) for run in served.RUNS]
    for ordinal in range(SCALE_RUN_COUNT - len(served.RUNS)):
        number = _pseudorandom(ordinal)
        status = _STATUSES[number % len(_STATUSES)]
        found.append(
            {
                "run_id": f"run-1{ordinal:05d}",
                "status": status,
                "trigger": "alert" if number % 3 else "schedule",
                "started_at": served.at(minutes=ordinal + 10),
                "finished_at": None if status == "running" else served.at(minutes=ordinal + 7),
                "summary": None if status == "running" else f"Investigation {ordinal} concluded.",
            }
        )
    return found


def resources() -> list[dict[str, Any]]:
    """Return ten thousand resources, the surveyed estate among them.

    Same reason as the runs: the incidents and observations in this scenario are
    about the surveyed guests, and dropping them would leave every subject
    dangling.
    """
    from tools.mockplane.capture.projection import project
    from tools.mockplane.dataset import profile

    surveyed: list[dict[str, Any]] = []
    for record in project(profile.cluster_reading()):
        if record.slug == "estate-resources" and isinstance(record.body, dict):
            surveyed = [dict(item) for item in record.body["resources"]]
            break

    found = list(surveyed)
    for ordinal in range(SCALE_RESOURCE_COUNT - len(surveyed)):
        number = _pseudorandom(ordinal)
        node = "node01" if number % 3 else "node02"
        found.append(
            {
                "resource_id": f"ct-1{ordinal:05d}",
                "name": f"guest-{ordinal:05d}",
                "kind": _KINDS[0] if number % 41 else _KINDS[1],
                "node": node,
                "state": _STATES[number % len(_STATES)],
                "owner": None,
                "tags": [],
                "cpu_percent": round((number % 1000) / 10.0, 2),
                "memory_percent": round((number % 900) / 10.0, 2),
                "volume_percent": round((number % 990) / 10.0, 2),
                "volume_id": f"vm-1{ordinal:05d}-disk-0",
                "backed_up": number % 5 != 0,
                "last_seen_at": served.at(minutes=1),
            }
        )
    return found


def events() -> list[dict[str, Any]]:
    """Return a ten-thousand-event transcript for one run."""
    return [
        {
            "run_id": LIVE_RUN,
            "kind": "tool_succeeded" if ordinal % 2 else "tool_called",
            "sequence": ordinal,
            "occurred_at": served.at(minutes=SCALE_EVENT_COUNT - ordinal),
            "turn_id": f"turn-{ordinal // 8:05d}",
            "payload": {"name": "estate.storage_pressure", "index": ordinal},
        }
        for ordinal in range(SCALE_EVENT_COUNT)
    ]


def config_nodes() -> list[dict[str, Any]]:
    """Return a five-hundred-node configuration tree, the declared nodes at its root."""
    found: list[dict[str, Any]] = [dict(node) for node in served.CONFIG_NODES]
    for ordinal in range(SCALE_CONFIG_NODE_COUNT - len(found)):
        parent = served.ORG_NODE if ordinal < 20 else f"unit-{(ordinal % 20):04d}"
        found.append(
            {
                "node_id": f"unit-{ordinal:04d}",
                "name": f"Unit {ordinal}",
                "kind": "team" if ordinal < 20 else "environment",
                "parent_id": parent,
            }
        )
    return found


def generate_scale() -> Iterator[CapturedRecord]:
    """Yield the scale scenario's records, in the order a scenario load reads them."""
    yield _record("runs", {"runs": runs()})
    yield _record("estate-resources", {"resources": resources()})
    yield _record("config-tree", {"nodes": config_nodes()})
    yield _record(
        "run-stream",
        {"run_id": LIVE_RUN, "events": events()},
        {"run_id": LIVE_RUN},
    )


__all__ = [
    "config_nodes",
    "events",
    "generate_scale",
    "resources",
    "runs",
]
