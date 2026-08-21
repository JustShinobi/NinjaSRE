"""Referential integrity: every identifier a record names resolves to a record that exists.

A dataset that validates against the contract can still be incoherent — a run
naming resources that are not in the estate, an incident about a guest nobody
discovered, a backup job covering a container that does not exist. Every one of
those renders as a blank panel or a dash, and a reviewer looking at a blank
panel cannot tell a design problem from a data problem.

Two declarations, both explicit rather than inferred. What each endpoint
*declares* into a namespace, and which field names *refer* into one. Inferring
either from the shape of the payload would silently stop checking the moment a
field was renamed.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from core.domain.alerts.sources import ALERT_SOURCES
from platform.estate.alert_resolution import UNRESOLVED_TARGET_PREFIX
from tools.mockplane.records import CapturedRecord


@dataclass(frozen=True, slots=True)
class Declaration:
    """One endpoint's contribution to a namespace."""

    slug: str
    #: The key holding the list, empty when the payload is one object.
    records_key: str
    #: The field of each record holding its identifier.
    identifier_key: str
    namespace: str


#: What exists, and where it is declared. A namespace nothing declares into is a
#: namespace every reference to it fails, which is the correct outcome: it means
#: the dataset references a kind of thing it does not contain.
DECLARATIONS: Final[tuple[Declaration, ...]] = (
    Declaration("runs", "runs", "run_id", "run"),
    Declaration("approvals", "approvals", "approval_id", "approval"),
    Declaration("interactions", "interactions", "interaction_id", "interaction"),
    Declaration("episodes", "episodes", "episode_id", "episode"),
    Declaration("documents", "documents", "document_id", "document"),
    Declaration("config-tree", "nodes", "node_id", "config-node"),
    Declaration("principals", "users", "user_id", "principal"),
    # ``/auth/me`` is authoritative about who is looking, and it has to be:
    # a deployment with an empty directory still has the principal that is
    # signed in to it, and a check that said otherwise would be asking the
    # empty scenario to sign in as nobody.
    Declaration("principal", "", "principal_id", "principal"),
    Declaration("tokens", "tokens", "token_id", "token"),
    Declaration("grants", "grants", "grant_id", "grant"),
    Declaration("estate-resources", "resources", "resource_id", "resource"),
    Declaration("incidents", "incidents", "incident_id", "incident"),
    Declaration("detectors", "detectors", "detector_id", "detector"),
    Declaration("observations", "observations", "observation_id", "observation"),
    Declaration("estate-backups", "jobs", "job_id", "backup-job"),
)

#: Field names that point at something, and the namespace they point into.
#: ``node_id`` is deliberately absent: it means a configuration node in one
#: payload and a cluster node in another, and a check that guessed which would
#: report a failure nobody could act on.
REFERENCE_KEYS: Final[Mapping[str, str]] = {
    "run_id": "run",
    "approval_id": "approval",
    "interaction_id": "interaction",
    "episode_id": "episode",
    "document_id": "document",
    "resource_id": "resource",
    "resource_ids": "resource",
    "incident_id": "incident",
    "incidents": "incident",
    "detector": "detector",
    "observation_id": "observation",
    "observation_ids": "observation",
    "principal_id": "principal",
    "subjects": "subject",
}

#: A record that carries a kind beside its identifier says which namespace it
#: points into. An audit event's ``resource_id`` is a run, an approval, a
#: configuration node, a token or a grant depending on its ``resource_kind``,
#: and a check that picked one of those would report a failure nobody could act
#: on.
TYPED_REFERENCE_KEYS: Final[Mapping[str, str]] = {"resource_id": "resource_kind"}

#: The ``subject`` namespace is a union: an observation is about a resource, a
#: datastore, a thin pool, a backup job, the cluster itself, or — for an
#: ingested alert nothing resolved — the target that could not be found.
#: Declared here so the union is a decision rather than an accident of what
#: happened to resolve.
SUBJECT_NAMESPACES: Final = (
    "resource",
    "backup-job",
    "datastore",
    "thin-pool",
    "cluster",
    "unresolved-target",
)


@dataclass(frozen=True, slots=True)
class Reference:
    """One identifier a record names, and where it names it."""

    slug: str
    pointer: str
    namespace: str
    identifier: str

    def __str__(self) -> str:
        return f"{self.slug}{self.pointer} refers to {self.namespace} {self.identifier!r}"


def declared(records: Sequence[CapturedRecord]) -> dict[str, set[str]]:
    """Return every identifier the dataset declares, by namespace."""
    namespaces: dict[str, set[str]] = {}
    for declaration in DECLARATIONS:
        for record in records:
            if record.slug != declaration.slug:
                continue
            for item in _rows(record.body, declaration.records_key):
                identifier = item.get(declaration.identifier_key)
                if isinstance(identifier, str) and identifier:
                    namespaces.setdefault(declaration.namespace, set()).add(identifier)

    # The union namespaces the estate contributes beyond its resource list.
    for record in records:
        if record.slug == "estate-storage" and isinstance(record.body, Mapping):
            for store in _rows(record.body, "datastores"):
                name = store.get("name")
                if isinstance(name, str):
                    namespaces.setdefault("datastore", set()).add(name)
            for pool in _rows(record.body, "thin_pools"):
                name = pool.get("name")
                if isinstance(name, str):
                    namespaces.setdefault("thin-pool", set()).add(name)
        if record.slug == "estate-unresolved-targets" and isinstance(record.body, Mapping):
            for target in _rows(record.body, "targets"):
                value = target.get("value")
                if isinstance(value, str) and value:
                    namespaces.setdefault("unresolved-target", set()).add(
                        f"{UNRESOLVED_TARGET_PREFIX}{value}"
                    )
    namespaces.setdefault("cluster", set()).add("cluster")

    # An incident's ``detector`` field is its *origin*: a detector when something
    # here noticed, and the alert source when something else did. The catalogue
    # is closed on both sides, so both are declared rather than the check being
    # narrowed to whichever kind the dataset happened to hold first.
    namespaces.setdefault("detector", set()).update(source.value for source in ALERT_SOURCES)

    namespaces["subject"] = {
        identifier
        for namespace in SUBJECT_NAMESPACES
        for identifier in namespaces.get(namespace, set())
    }
    return namespaces


def readable(records: Sequence[CapturedRecord]) -> tuple[CapturedRecord, ...]:
    """Return the records that describe the deployment's state, not a change to it.

    A write's answer describes the state *after* a mutation the fixture set does
    not contain — a run that has just been started is not in the run list, and
    it should not be. Checking those for referential integrity would report a
    failure whose only fix would be to make the reads lie.
    """
    from tools.mockplane.endpoints import endpoint_by_slug

    kept: list[CapturedRecord] = []
    for record in records:
        try:
            endpoint = endpoint_by_slug(record.slug)
        except KeyError:
            continue
        if endpoint.method == "GET" and record.status < 400:
            kept.append(record)
    return tuple(kept)


def references(records: Sequence[CapturedRecord]) -> tuple[Reference, ...]:
    """Return every identifier the dataset names, with a pointer to where."""
    found: list[Reference] = []
    for record in records:
        found.extend(_walk(record.slug, record.body, ""))
    return tuple(found)


def broken(records: Sequence[CapturedRecord]) -> tuple[Reference, ...]:
    """Return every reference that resolves to nothing.

    Empty means the dataset is referentially complete. Each entry names the
    endpoint, the pointer inside it, and what it was looking for, so a failure
    is a thing somebody can go and fix.
    """
    state = readable(records)
    namespaces = declared(state)
    return tuple(
        reference
        for reference in references(state)
        if reference.identifier not in namespaces.get(reference.namespace, set())
    )


def _rows(body: Any, key: str) -> Iterator[Mapping[str, Any]]:
    if not isinstance(body, Mapping):
        return
    rows = body.get(key) if key else body
    if isinstance(rows, Mapping):
        yield rows
        return
    if isinstance(rows, Sequence) and not isinstance(rows, str | bytes):
        for item in rows:
            if isinstance(item, Mapping):
                yield item


def _walk(slug: str, value: Any, pointer: str) -> Iterator[Reference]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            here = f"{pointer}/{key}"
            namespace = _namespace_of(str(key), value)
            if namespace is not None:
                yield from _named(slug, here, namespace, item)
            yield from _walk(slug, item, here)
        return
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for index, item in enumerate(value):
            yield from _walk(slug, item, f"{pointer}/{index}")


def _namespace_of(key: str, parent: Mapping[str, Any]) -> str | None:
    """Return the namespace ``key`` points into, honouring a sibling kind field."""
    kind_key = TYPED_REFERENCE_KEYS.get(key)
    if kind_key is not None:
        kind = parent.get(kind_key)
        return str(kind) if isinstance(kind, str) and kind else None
    return REFERENCE_KEYS.get(key)


def _named(slug: str, pointer: str, namespace: str, value: Any) -> Iterator[Reference]:
    if isinstance(value, str) and value:
        yield Reference(slug, pointer, namespace, value)
        return
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for index, item in enumerate(value):
            if isinstance(item, str) and item:
                yield Reference(slug, f"{pointer}/{index}", namespace, item)


__all__ = [
    "DECLARATIONS",
    "REFERENCE_KEYS",
    "SUBJECT_NAMESPACES",
    "Declaration",
    "TYPED_REFERENCE_KEYS",
    "Reference",
    "broken",
    "declared",
    "readable",
    "references",
]
