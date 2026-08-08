"""The dataset as a demonstration deployment, for loading into a real database.

Two consumers, one dataset. The mock serves it to the console over HTTP; a demo
seeder loads the same records into Postgres. Two fictional deployments would
drift, and the first person to notice would be somebody whose demo looked
nothing like the screenshots — which is why this module exists rather than a
second set of invented records living beside the seeder.

Everything loaded into a real deployment carries a label saying it is a
demonstration. A demo record that could not be told from a real one is a demo
record somebody eventually acts on.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from config.constants.fixtures import (
    DEFAULT_FIXTURE_SCENARIO,
    DEMONSTRATION_LABEL,
    DEMONSTRATION_LABEL_FIELD,
)
from tools.mockplane import scenarios
from tools.mockplane.endpoints import endpoint_by_slug
from tools.mockplane.records import CapturedRecord

# The label field and its value are re-exported from the constants tier rather
# than declared here: the seeder that loads this dataset into a real database and
# the sweep that removes it again both need them, and neither may import
# repository tooling.

#: The organisation the fictional deployment lives under. Declared here rather
#: than in the constants tier, because this tree and the fixture tree are the
#: only two places the deployment may be named at all.
DEMONSTRATION_ORGANISATION: Final = "org-northwind"


@dataclass(frozen=True, slots=True)
class SeedRecord:
    """One record to load, and what sort of thing it is."""

    #: The endpoint it came from, which is what says what kind of record it is.
    slug: str
    #: The collection it belongs to, empty when the payload is a single object.
    collection: str
    payload: Mapping[str, Any]

    def labelled(self) -> dict[str, Any]:
        """Return the payload carrying the demonstration label."""
        return {**self.payload, DEMONSTRATION_LABEL_FIELD: DEMONSTRATION_LABEL}


def records_for_seeding(
    scenario: str = DEFAULT_FIXTURE_SCENARIO, root: Path | None = None
) -> tuple[SeedRecord, ...]:
    """Return every record of ``scenario`` as something a seeder can load.

    Reads only what describes the deployment's state — the answers to writes
    describe a change that has not happened in a freshly seeded database, and
    loading one would put a run in the trace that nothing ever started.
    """
    return tuple(_flatten(scenarios.load(scenario, root).all_records()))


def _flatten(records: Sequence[CapturedRecord]) -> Iterator[SeedRecord]:
    for record in records:
        endpoint = endpoint_by_slug(record.slug)
        if endpoint.method != "GET" or endpoint.streaming or record.status >= 400:
            continue
        if not isinstance(record.body, Mapping):
            continue
        if endpoint.records_key:
            rows = record.body.get(endpoint.records_key)
            if isinstance(rows, Sequence) and not isinstance(rows, str | bytes):
                for row in rows:
                    if isinstance(row, Mapping):
                        yield SeedRecord(record.slug, endpoint.records_key, row)
            continue
        yield SeedRecord(record.slug, "", record.body)


__all__ = [
    "DEMONSTRATION_LABEL",
    "DEMONSTRATION_LABEL_FIELD",
    "DEMONSTRATION_ORGANISATION",
    "SeedRecord",
    "records_for_seeding",
]
