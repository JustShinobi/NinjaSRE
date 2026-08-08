"""Demo mode: the dataset, the seeder, the transport that refuses a real call.

``python -m tools.mockplane`` serves the same dataset to the console over HTTP.
This loads it into the database instead, so a demonstration exercises the real
read path rather than a second one that only demonstrations use.
"""

from __future__ import annotations

from platform.startup.demo.dataset import (
    CLUSTER_RESOURCE_ID,
    DemoDataset,
    component_identifiers,
    estate_identifiers,
    fixture_root,
    load_dataset,
    unresolved_references,
)
from platform.startup.demo.labels import is_demonstration, labelled
from platform.startup.demo.scripted import (
    ScriptedEvent,
    scripted_events,
    stream_scripted_investigation,
)
from platform.startup.demo.seeder import (
    DemoRefused,
    RemovalReport,
    SeedReport,
    demonstration_residue,
    estate_of,
    remove_demonstration,
    seed_demonstration,
)
from platform.startup.demo.transport import (
    FixtureTransport,
    RealRequestInDemoMode,
    demo_mode_enabled,
)

__all__ = [
    "CLUSTER_RESOURCE_ID",
    "DemoDataset",
    "DemoRefused",
    "FixtureTransport",
    "RealRequestInDemoMode",
    "RemovalReport",
    "ScriptedEvent",
    "SeedReport",
    "component_identifiers",
    "demo_mode_enabled",
    "demonstration_residue",
    "estate_identifiers",
    "estate_of",
    "fixture_root",
    "is_demonstration",
    "labelled",
    "load_dataset",
    "remove_demonstration",
    "scripted_events",
    "seed_demonstration",
    "stream_scripted_investigation",
    "unresolved_references",
]
