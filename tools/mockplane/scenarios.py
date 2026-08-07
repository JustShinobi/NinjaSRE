"""The named datasets, what each is for, and how one is composed from another.

Seven scenarios, and the reason there are seven rather than one is that most of
what a console gets wrong is not visible against a full, healthy deployment. An
empty state is only reviewable when something renders it. Panel-level error
handling is only exercised when a panel actually fails. A ten-thousand-event
transcript is only slow when there are ten thousand events.

Composition keeps the committed size down and the intent legible: a scenario
that differs from ``populated`` in three endpoints holds three files, not forty.
``degraded`` holds none at all — it is ``populated`` plus a declaration of which
endpoints misbehave and how, which is exactly what it is.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final

from config.constants.fixtures import (
    DEFAULT_FIXTURE_SCENARIO,
    FIXTURE_MANIFEST_FILENAME,
    FIXTURE_SCENARIO_NAMES,
    GENERATED_FIXTURE_SCENARIOS,
)
from tools.mockplane.endpoints import ConsoleEndpoint, endpoint_by_slug
from tools.mockplane.paths import fixture_root, scenario_dir
from tools.mockplane.records import CapturedRecord

#: The slug an override uses to mean "every endpoint".
EVERY_ENDPOINT: Final = "*"


class ScenarioError(RuntimeError):
    """The manifest names something that is not there, or names it twice."""


@dataclass(frozen=True, slots=True)
class Override:
    """One declared misbehaviour, for one endpoint or for all of them."""

    slug: str = EVERY_ENDPOINT
    #: Answer with this status instead. ``None`` leaves the status alone.
    status: int | None = None
    #: Wait this long before answering. The console's loading states are only
    #: reviewable against an endpoint that is actually slow.
    latency_ms: int = 0
    #: Answer with the shape the endpoint returns and no records in it.
    empty: bool = False
    #: Answer with a body that stops mid-document. A client that assumes a
    #: complete JSON payload fails here rather than in front of an operator.
    truncate: bool = False
    #: Do not answer at all: close the connection. Different from a 500, and the
    #: difference is the whole point of having both.
    refuse: bool = False
    #: Answer with this instead of the fixture.
    body: Any = None

    def applies_to(self, slug: str) -> bool:
        """Return whether this override governs ``slug``."""
        return self.slug in {EVERY_ENDPOINT, slug}

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> Override:
        """Return the override a manifest entry describes."""
        return cls(
            slug=str(document.get("slug", EVERY_ENDPOINT)),
            status=int(document["status"]) if document.get("status") is not None else None,
            latency_ms=int(document.get("latency_ms", 0)),
            empty=bool(document.get("empty", False)),
            truncate=bool(document.get("truncate", False)),
            refuse=bool(document.get("refuse", False)),
            body=document.get("body"),
        )


@dataclass(frozen=True, slots=True)
class Scenario:
    """One named dataset: where its records come from, and how they misbehave."""

    name: str
    description: str
    #: The scenario whose records this one starts from, before its own files and
    #: its overrides are applied.
    derives_from: str = ""
    overrides: tuple[Override, ...] = field(default_factory=tuple)
    #: Built from a seed at load time rather than committed, because committing
    #: it would breach the size budget on its own.
    generated: bool = False
    #: The principal this scenario signs in as, for the role-matrix screens.
    principal_role: str = ""

    def override_for(self, slug: str) -> Override | None:
        """Return the override governing ``slug``, most specific first."""
        for override in self.overrides:
            if override.slug == slug:
                return override
        for override in self.overrides:
            if override.slug == EVERY_ENDPOINT:
                return override
        return None

    def with_override(self, override: Override) -> Scenario:
        """Return this scenario with ``override`` taking precedence over its own.

        The composition FR-020 asks for: a test takes ``populated`` and makes one
        endpoint fail, without a new scenario and without touching the console.
        """
        return replace(self, overrides=(override, *self.overrides))


@dataclass(frozen=True, slots=True)
class Manifest:
    """Every declared scenario, in the order the file lists them."""

    scenarios: tuple[Scenario, ...]
    default: str = DEFAULT_FIXTURE_SCENARIO

    def __iter__(self) -> Any:
        return iter(self.scenarios)

    def names(self) -> tuple[str, ...]:
        """Return the declared scenario names."""
        return tuple(scenario.name for scenario in self.scenarios)

    def get(self, name: str) -> Scenario:
        """Return the scenario ``name``.

        Raises:
            ScenarioError: nothing declares it.
        """
        for scenario in self.scenarios:
            if scenario.name == name:
                return scenario
        raise ScenarioError(
            f"{name!r} is not a declared scenario; the manifest declares {', '.join(self.names())}"
        )

    @classmethod
    def load(cls, root: Path | None = None) -> Manifest:
        """Return the committed manifest.

        Raises:
            ScenarioError: it is missing, malformed, or declares a name twice.
        """
        path = fixture_root(root) / FIXTURE_MANIFEST_FILENAME
        if not path.exists():
            raise ScenarioError(f"{path} does not exist")
        document = json.loads(path.read_text(encoding="utf-8"))
        entries = document.get("scenarios") if isinstance(document, Mapping) else None
        if not isinstance(entries, Sequence):
            raise ScenarioError(f"{path} declares no 'scenarios' list")

        scenarios: list[Scenario] = []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ScenarioError(f"{path} holds a scenario that is not an object")
            name = str(entry.get("name", ""))
            if not name:
                raise ScenarioError(f"{path} holds a scenario with no name")
            if name in seen:
                raise ScenarioError(f"{path} declares {name!r} twice")
            seen.add(name)
            raw_overrides = entry.get("overrides")
            scenarios.append(
                Scenario(
                    name=name,
                    description=str(entry.get("description", "")),
                    derives_from=str(entry.get("derives_from", "") or ""),
                    overrides=tuple(
                        Override.from_json(item)
                        for item in (raw_overrides if isinstance(raw_overrides, Sequence) else ())
                        if isinstance(item, Mapping)
                    ),
                    generated=bool(entry.get("generated", False)),
                    principal_role=str(entry.get("principal_role", "") or ""),
                )
            )
        return cls(
            scenarios=tuple(scenarios),
            default=str(document.get("default", DEFAULT_FIXTURE_SCENARIO)),
        )


def arguments_key(arguments: Mapping[str, str]) -> str:
    """Return the stable key one record's path variables are held under."""
    return ",".join(f"{name}={value}" for name, value in sorted(arguments.items()))


@dataclass(frozen=True, slots=True)
class ScenarioData:
    """One scenario's records, indexed the way a request looks them up."""

    scenario: Scenario
    #: ``(slug, arguments key)`` to the record answering it.
    records: Mapping[tuple[str, str], CapturedRecord]

    def slugs(self) -> frozenset[str]:
        """Return the endpoints this scenario has any record for."""
        return frozenset(slug for slug, _ in self.records)

    def all_records(self) -> tuple[CapturedRecord, ...]:
        """Return every record, in a stable order."""
        return tuple(self.records[key] for key in sorted(self.records))

    def lookup(self, slug: str, arguments: Mapping[str, str]) -> CapturedRecord | None:
        """Return the record answering ``slug`` with ``arguments``, or the collection's.

        A templated endpoint falls back to no arguments so a scenario can answer
        every identifier with one record — which is what ``empty`` wants and what
        ``scale`` needs, since it has ten thousand of them.
        """
        exact = self.records.get((slug, arguments_key(arguments)))
        if exact is not None:
            return exact
        return self.records.get((slug, ""))


def scenario_files(scenario: str, root: Path | None = None) -> tuple[Path, ...]:
    """Return the fixture files one scenario declares of its own."""
    directory = scenario_dir(scenario, root)
    if not directory.is_dir():
        return ()
    return tuple(sorted(directory.glob("*.json")))


def read_fixture(path: Path) -> tuple[ConsoleEndpoint, tuple[CapturedRecord, ...]]:
    """Return the endpoint and records one fixture file holds.

    Raises:
        ScenarioError: the file names an endpoint the catalogue does not have,
            which is how a renamed endpoint leaves a fixture behind.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    slug = str(document.get("slug", path.stem)) if isinstance(document, Mapping) else path.stem
    try:
        endpoint = endpoint_by_slug(slug)
    except KeyError as error:
        raise ScenarioError(f"{path} answers {slug!r}, which is not an endpoint") from error
    raw = document.get("responses") if isinstance(document, Mapping) else None
    if not isinstance(raw, Sequence):
        raise ScenarioError(f"{path} declares no 'responses' list")
    records = tuple(
        CapturedRecord.from_json({"slug": slug, **item})
        for item in raw
        if isinstance(item, Mapping)
    )
    return endpoint, records


def write_fixture(path: Path, slug: str, records: Sequence[CapturedRecord]) -> None:
    """Write one endpoint's records as a fixture file.

    Not a public path into the dataset: everything that calls this has already
    been through the anonymisation pipeline, and an architecture test asserts it.
    """
    from tools.mockplane.records import dumps

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "slug": slug,
        "responses": [
            {key: value for key, value in record.as_json().items() if key != "slug"}
            for record in records
        ],
    }
    path.write_text(dumps(payload), encoding="utf-8")


def load(
    name: str = "",
    root: Path | None = None,
    manifest: Manifest | None = None,
) -> ScenarioData:
    """Return one scenario's records, its base scenario's records underneath.

    Raises:
        ScenarioError: the scenario is not declared, or its inheritance is a
            cycle.
    """
    declared = manifest if manifest is not None else Manifest.load(root)
    scenario = declared.get(name or declared.default)
    records: dict[tuple[str, str], CapturedRecord] = {}

    for ancestor in _lineage(scenario, declared):
        if ancestor.generated:
            from tools.mockplane.dataset.scale import generate_scale

            for record in generate_scale():
                records[(record.slug, arguments_key(record.arguments))] = record
            continue
        for path in scenario_files(ancestor.name, root):
            _, found = read_fixture(path)
            for record in found:
                records[(record.slug, arguments_key(record.arguments))] = record

    return ScenarioData(scenario=scenario, records=records)


def _lineage(scenario: Scenario, manifest: Manifest) -> tuple[Scenario, ...]:
    """Return ``scenario``'s ancestry, base first, so later files win."""
    chain: list[Scenario] = []
    seen: set[str] = set()
    current: Scenario | None = scenario
    while current is not None:
        if current.name in seen:
            raise ScenarioError(f"{scenario.name!r} derives from itself, through {current.name!r}")
        seen.add(current.name)
        chain.append(current)
        current = manifest.get(current.derives_from) if current.derives_from else None
    return tuple(reversed(chain))


def declared_names() -> tuple[str, ...]:
    """Return the scenario names the constants tier declares."""
    return FIXTURE_SCENARIO_NAMES


def generated_names() -> tuple[str, ...]:
    """Return the scenarios built from a seed rather than committed."""
    return GENERATED_FIXTURE_SCENARIOS


__all__ = [
    "EVERY_ENDPOINT",
    "Manifest",
    "Override",
    "Scenario",
    "ScenarioData",
    "ScenarioError",
    "arguments_key",
    "declared_names",
    "generated_names",
    "load",
    "read_fixture",
    "scenario_files",
    "write_fixture",
]
