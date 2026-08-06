"""Topology as code: a file an operator writes, reviews, and re-applies.

The third way to populate the graph, beside manual entry and discovery, and the
one that suits the part of an estate no adapter can see — the third-party payment
provider, the mainframe behind the batch job, the queue that only exists during a
release. Written as a file, it goes through the same review as any other change,
and re-applying it is idempotent.

Two decisions shape the parser.

**Every problem is reported, not the first.** An operator fixing an import file
one error per run is an operator who stops using the file, and a topology nobody
maintains is worse than none — it is a stale one the agent believes.

**An edge to an undeclared service is an error.** The storage port creates
endpoints it has never seen, which is right for discovery (a source often sees an
edge before both of its ends) and wrong here. In a file that is meant to be the
source of truth, ``paymnets`` is a typo, and silently creating a node for it
would put a service in the graph that does not exist and never gets removed.

Everything an import writes is marked operator-authored. That is what stops the
next discovery run removing the dependency the file exists to record.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import yaml

from config.constants.knowledge import MAX_IMPORT_EDGES, MAX_IMPORT_NODES
from platform.knowledge.clock import now as _utc_now
from platform.knowledge.errors import ImportInvalid
from platform.knowledge.topology.models import (
    OPERATOR_SOURCE,
    DependencyEdge,
    DependencyKind,
    ServiceNode,
)
from platform.knowledge.topology.write import TopologyWriter, TopologyWriteReport
from platform.observability.logging import get_logger
from platform.persistence.ports.topology_graph import NodeKind
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope

logger = get_logger(__name__)

#: The document version this parser understands. A file declaring anything else
#: is refused rather than interpreted: a schema change that silently ignored the
#: fields it did not recognise would apply half a topology and report success.
SUPPORTED_VERSION = 1

#: The keys a document may carry at the top level.
DOCUMENT_KEYS = frozenset({"version", "services", "dependencies"})

#: The keys one service entry may carry.
SERVICE_KEYS = frozenset({"id", "kind", "name", "environment", "owner", "annotations"})

#: The keys one dependency entry may carry.
DEPENDENCY_KEYS = frozenset({"from", "to", "kind", "metadata", "annotations"})


@dataclass(frozen=True, slots=True)
class TopologyDocument:
    """A parsed, validated topology file."""

    services: tuple[ServiceNode, ...] = ()
    dependencies: tuple[DependencyEdge, ...] = ()
    version: int = SUPPORTED_VERSION

    @property
    def empty(self) -> bool:
        """Return whether the document declares nothing."""
        return not self.services and not self.dependencies


def parse_topology(source: str | Mapping[str, Any]) -> TopologyDocument:
    """Return the document ``source`` describes, or raise naming every problem.

    Accepts YAML text or an already-parsed mapping. Both, because the console
    posts a structure and an operator applies a file, and making one of them
    serialise to the other's shape first would be a translation to keep in
    agreement with this one.
    """
    document = _loaded(source)
    problems: list[str] = []

    unknown = set(document) - DOCUMENT_KEYS
    if unknown:
        problems.append(f"unknown top-level key(s): {', '.join(sorted(unknown))}")

    version = document.get("version", SUPPORTED_VERSION)
    if version != SUPPORTED_VERSION:
        problems.append(f"version {version!r} is not supported; this parser reads version 1")

    services = _services(document.get("services") or (), problems)
    dependencies = _dependencies(document.get("dependencies") or (), set(services), problems)

    if problems:
        raise ImportInvalid(tuple(problems))

    return TopologyDocument(
        services=tuple(services.values()),
        dependencies=tuple(dependencies),
        version=SUPPORTED_VERSION,
    )


def _loaded(source: str | Mapping[str, Any]) -> Mapping[str, Any]:
    """Return ``source`` as a mapping, or raise if it is not one."""
    if isinstance(source, Mapping):
        return source
    try:
        parsed = yaml.safe_load(source)
    except yaml.YAMLError as error:
        raise ImportInvalid((f"the document is not valid YAML: {error}",)) from error
    if not isinstance(parsed, Mapping):
        raise ImportInvalid(("the document must be a mapping with a 'services' key",))
    return parsed


def _services(entries: Any, problems: list[str]) -> dict[str, ServiceNode]:
    """Return the services an entry list declares, collecting every problem."""
    services: dict[str, ServiceNode] = {}
    if not isinstance(entries, Sequence) or isinstance(entries, str | bytes):
        problems.append("'services' must be a list")
        return services
    if len(entries) > MAX_IMPORT_NODES:
        problems.append(
            f"{len(entries)} services declared, above the {MAX_IMPORT_NODES} an import may "
            f"carry — a file this large wanted a discovery adapter"
        )
        return services

    for position, entry in enumerate(entries):
        where = f"services[{position}]"
        if not isinstance(entry, Mapping):
            problems.append(f"{where} must be a mapping")
            continue
        unknown = set(entry) - SERVICE_KEYS
        if unknown:
            problems.append(f"{where} has unknown key(s): {', '.join(sorted(unknown))}")

        identifier = str(entry.get("id", "")).strip()
        if not identifier:
            problems.append(f"{where} has no 'id'")
            continue
        if identifier in services:
            problems.append(f"{where} declares {identifier!r} a second time")
            continue

        kind = str(entry.get("kind", NodeKind.SERVICE.value)).strip().lower()
        try:
            node_kind = NodeKind(kind)
        except ValueError:
            allowed = ", ".join(member.value for member in NodeKind)
            problems.append(f"{where} has kind {kind!r}; expected one of {allowed}")
            continue

        services[identifier] = ServiceNode(
            node_id=identifier,
            kind=node_kind,
            name=str(entry.get("name", "")),
            environment=str(entry.get("environment", "")),
            owner=str(entry.get("owner", "")),
            annotations=_mapping(entry.get("annotations"), where, problems),
            source=OPERATOR_SOURCE,
            operator_authored=True,
        )

    return services


def _dependencies(entries: Any, declared: set[str], problems: list[str]) -> list[DependencyEdge]:
    """Return the dependencies an entry list declares, collecting every problem."""
    edges: list[DependencyEdge] = []
    if not isinstance(entries, Sequence) or isinstance(entries, str | bytes):
        problems.append("'dependencies' must be a list")
        return edges
    if len(entries) > MAX_IMPORT_EDGES:
        problems.append(
            f"{len(entries)} dependencies declared, above the {MAX_IMPORT_EDGES} an import "
            f"may carry"
        )
        return edges

    seen: set[tuple[str, str, str]] = set()
    for position, entry in enumerate(entries):
        where = f"dependencies[{position}]"
        if not isinstance(entry, Mapping):
            problems.append(f"{where} must be a mapping")
            continue
        unknown = set(entry) - DEPENDENCY_KEYS
        if unknown:
            problems.append(f"{where} has unknown key(s): {', '.join(sorted(unknown))}")

        origin = str(entry.get("from", "")).strip()
        target = str(entry.get("to", "")).strip()
        if not origin or not target:
            problems.append(f"{where} must name both 'from' and 'to'")
            continue
        for endpoint in (origin, target):
            if endpoint not in declared:
                problems.append(
                    f"{where} names {endpoint!r}, which no service in this document "
                    f"declares — declare it, or correct the spelling"
                )
        if origin == target:
            problems.append(f"{where} makes {origin!r} depend on itself")
            continue

        kind = DependencyKind.parse(str(entry.get("kind", DependencyKind.DEPENDS_ON.value)))
        key = (origin, target, kind.value)
        if key in seen:
            problems.append(f"{where} declares {origin} -> {target} ({kind.value}) a second time")
            continue
        seen.add(key)

        edges.append(
            DependencyEdge(
                from_node_id=origin,
                to_node_id=target,
                kind=kind,
                metadata=_mapping(entry.get("metadata"), where, problems),
                annotations=_mapping(entry.get("annotations"), where, problems),
                source=OPERATOR_SOURCE,
                operator_authored=True,
            )
        )

    return edges


def _mapping(value: Any, where: str, problems: list[str]) -> dict[str, str]:
    """Return a string-to-string mapping, or record why ``value`` is not one."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        problems.append(f"{where} has a non-mapping where a mapping was expected")
        return {}
    return {str(key): str(item) for key, item in value.items()}


@dataclass(slots=True)
class TopologyImporter:
    """Applies a declarative topology document to one team's graph."""

    gateway: PersistenceGateway
    scope: TenantScope
    clock: Callable[[], datetime] = _utc_now
    writer: TopologyWriter = field(init=False)

    def __post_init__(self) -> None:
        self.writer = TopologyWriter(gateway=self.gateway, scope=self.scope, clock=self.clock)

    async def apply(self, document: TopologyDocument) -> TopologyWriteReport:
        """Write everything ``document`` declares, in one transaction.

        Idempotent: re-applying an unchanged file writes the same records and
        moves their verification stamps forward. Services first, so an edge's
        endpoints already carry their environment and owner by the time the edge
        creates them — the store would otherwise create bare nodes and the
        properties would arrive a moment later, which is correct but produces a
        confusing intermediate state in anything watching.
        """
        async with self.gateway.begin(self.scope) as uow:
            for service in document.services:
                await self.writer.write_service(uow, service)
            for edge in document.dependencies:
                await self.writer.write_dependency(uow, edge)

        report = TopologyWriteReport(
            services=len(document.services), dependencies=len(document.dependencies)
        )
        logger.info(
            "topology.imported",
            services=report.services,
            dependencies=report.dependencies,
            team=self.scope.team_node_id,
        )
        return report

    async def apply_text(self, text: str) -> TopologyWriteReport:
        """Parse a YAML document and apply it."""
        return await self.apply(parse_topology(text))


__all__ = [
    "DEPENDENCY_KEYS",
    "DOCUMENT_KEYS",
    "SERVICE_KEYS",
    "SUPPORTED_VERSION",
    "TopologyDocument",
    "TopologyImporter",
    "parse_topology",
]
