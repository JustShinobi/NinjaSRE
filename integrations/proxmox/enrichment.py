"""The operator's own inventory, read as annotations on what the cluster reports.

A hypervisor knows a container exists. It does not know whether a container
stopping is a Tuesday or an outage. That answer lives in a repository somebody
maintains by hand — five YAML documents declaring the zones a cluster is divided
into, what each node and guest is for, how much each matters, and the domain
each workload answers on — and this module reads it.

**The direction of truth is fixed and is enforced one layer up.** What this
produces is an ``EnrichmentPlan``: a zone map, a set of annotations keyed by the
value the file and the API both chose, and the disagreements found on the way.
``platform.estate.enrichment.apply_enrichment`` may only *annotate* resources
the live source reported, so nothing here can bring a deleted machine back.

**Nothing in the repository is executed and nothing outside it is read.** The
ingestion holds an ``InventoryReader`` and asks it for five names. The shipped
reader is a directory; a deployment that fetches the documents over HTTPS
composes a reader that does, and neither has a code path the other does not.

**Validation is against the schemas the repository publishes, bundled here.**
Bundled rather than fetched, because a validator that downloads its own contract
validates whatever it was served. The validator is a deliberate subset of JSON
Schema — the keywords these documents actually use — and a test asserts that no
bundled schema uses a keyword it would silently ignore, so a schema that grows
one fails the build rather than quietly checking less than it claims.

**A value shaped like a credential is refused rather than stored.** Somebody's
inventory will eventually carry a token in a description field. The refusal
names the file and the field and never the value, which is the same line every
other refusal in this repository holds.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

import yaml

from config.constants.estate import (
    MAX_ENRICHMENT_DOCUMENT_BYTES,
    MAX_ENRICHMENT_ENTRIES,
)
from integrations.proxmox.inventory import InventoryInvalid
from platform.estate.enrichment import (
    Annotation,
    Divergence,
    DivergenceKind,
    EnrichmentPlan,
    ZoneMap,
    zone_networks,
)
from platform.estate.kinds import KIND_CONTAINER, KIND_NODE, KIND_VIRTUAL_MACHINE
from platform.guardrails.engine import GuardrailEngine

#: The five documents this reads, and the key each one's entries live under.
#: Ordered, so a refusal reads in the order somebody would fix the files.
INVENTORY_DOCUMENTS: Final[tuple[tuple[str, str], ...]] = (
    ("zones", "zones"),
    ("nodes", "nodes"),
    ("cts", "containers"),
    ("vms", "virtual_machines"),
    ("services", "services"),
)

#: Where in the repository the documents live. Only this directory is read; the
#: rest of the tree is somebody else's business and none of it is executed.
INVENTORY_SUBPATH: Final[tuple[str, ...]] = ("inventory", "cluster")

#: The document without which an ingestion is meaningless. A missing
#: ``vms.yaml`` means a cluster with no virtual machines, which is a statement.
#: A missing ``zones.yaml`` means every guest is unplaced and every one of them
#: reported as a divergence, which is what a wrong path looks like — so it is
#: refused instead.
REQUIRED_DOCUMENT: Final = "zones"

#: The JSON Schema keywords the validator below implements. Anything else in a
#: bundled schema would be silently ignored, which is why a test asserts that
#: none of them uses one.
SUPPORTED_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "$schema",
        "title",
        "description",
        "type",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "enum",
        "minimum",
    }
)

_SCHEMA_ROOT: Final = Path(__file__).resolve().parent / "inventory_schemas"

_JSON_TYPES: Final[Mapping[str, type | tuple[type, ...]]] = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}

_ENGINE = GuardrailEngine()

#: The kinds these five documents speak about. A datastore, a thin pool and a
#: physical disk are outside what an operator declares here, so they are neither
#: annotated nor reported as undeclared — a report that named every disk as
#: missing from the inventory would bury the one guest that genuinely is.
ANNOTATED_KINDS: Final[tuple[str, ...]] = (KIND_NODE, KIND_CONTAINER, KIND_VIRTUAL_MACHINE)

#: Which annotation each declared field becomes. The file's vocabulary is the
#: operator's; the estate's is closed. Mapping them here rather than passing the
#: file's keys through is what keeps a document that grew a field from growing
#: the estate a column.
_DECLARED_ANNOTATIONS: Final[tuple[str, ...]] = ("criticality", "tier", "owner")


class InventoryTooLarge(ValueError):
    """A document is larger, or declares more, than the deployment will read.

    Refused before parsing rather than after. The bound exists because the file
    arrives from somewhere this deployment does not control, and a bound checked
    after the parse is a bound the parse already paid.
    """

    def __init__(self, document: str, *, measured: int, limit: int, unit: str) -> None:
        super().__init__(
            f"{document} is {measured} {unit}, above the limit of {limit}. A declared "
            f"inventory arrives from somewhere this deployment does not control, so the "
            f"size of it is not a decision this process takes."
        )
        self.document = document


@runtime_checkable
class InventoryReader(Protocol):
    """Where the five documents are read from.

    One method, and it is the whole seam between "a directory this container can
    see" and "raw files over HTTPS". A reader returns the document's bytes or
    ``None`` when it does not have that name — absent and empty are different
    facts, and a reader that returned empty bytes for a missing file would make
    a wrong path look like a cluster with no zones.
    """

    def read(self, name: str) -> bytes | None:
        """Return ``name``'s bytes, or ``None`` when this source has no such document."""


@dataclass(frozen=True, slots=True)
class DirectoryInventory:
    """The documents as files under ``inventory/cluster`` in a checked-out tree.

    The shipped reader. Nothing in the tree is executed and nothing outside that
    one directory is opened — a repository is a place to read five files from,
    not a program to run.
    """

    root: Path

    def read(self, name: str) -> bytes | None:
        """Return the document's bytes, or ``None`` when the file is not there."""
        path = self.root.joinpath(*INVENTORY_SUBPATH, f"{name}.yaml")
        try:
            return path.read_bytes()
        except OSError:
            return None


@cache
def schema_for_document(name: str) -> Mapping[str, Any]:
    """Return the bundled JSON Schema ``name`` is validated against."""
    loaded: Any = json.loads((_SCHEMA_ROOT / f"{name}.json").read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"the bundled schema for {name} is not an object")
    return loaded


def ingest(reader: InventoryReader, *, cluster: str) -> EnrichmentPlan:
    """Return the plan the declared inventory describes.

    Raises:
        InventoryTooLarge: a document exceeds the byte or entry bound.
        InventoryInvalid: any document fails its schema, carries a value shaped
            like a credential, declares overlapping zones, or the one document
            an ingestion cannot proceed without is missing. Every problem is
            reported at once, each naming its file and its field path.
    """
    problems: list[str] = []
    documents: dict[str, list[Mapping[str, Any]]] = {}

    for name, key in INVENTORY_DOCUMENTS:
        raw = reader.read(name)
        if raw is None:
            if name == REQUIRED_DOCUMENT:
                problems.append(
                    f"{name}.yaml is not there. Without the declared zones every guest is "
                    f"unplaced, which is what a wrong path looks like rather than a cluster."
                )
            documents[name] = []
            continue
        documents[name] = _entries(name, key, raw, problems)

    if problems:
        raise InventoryInvalid(problems)

    zones = _zone_map(documents["zones"], problems)
    annotations = _annotations(documents, cluster=cluster)
    divergences = _service_divergences(documents, cluster=cluster, annotated=set(annotations))

    if problems:
        raise InventoryInvalid(problems)

    return EnrichmentPlan(
        zones=zones,
        kinds=ANNOTATED_KINDS,
        annotations=tuple(
            Annotation(correlation_key=key, values=values)
            for key, values in sorted(annotations.items())
        ),
        divergences=tuple(divergences),
    )


def domains_of(plan: EnrichmentPlan) -> tuple[Mapping[str, str], ...]:
    """Return the domain-to-workload pairs an applied plan implies.

    Read back off the annotations rather than carried separately, so the graph
    edge and the resource attribute cannot disagree about which container serves
    a domain.
    """
    return tuple(
        {"domain": entry.values["domain"], "workload": entry.correlation_key}
        for entry in plan.annotations
        if entry.values.get("domain")
    )


# --- reading one document -----------------------------------------------------


def _entries(
    name: str,
    key: str,
    raw: bytes,
    problems: list[str],
) -> list[Mapping[str, Any]]:
    """Return one document's validated entries, appending every problem it has."""
    if len(raw) > MAX_ENRICHMENT_DOCUMENT_BYTES:
        raise InventoryTooLarge(
            f"{name}.yaml", measured=len(raw), limit=MAX_ENRICHMENT_DOCUMENT_BYTES, unit="bytes"
        )

    try:
        document = yaml.safe_load(raw.decode("utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError) as broken:
        problems.append(f"{name}.yaml is not readable YAML: {type(broken).__name__}")
        return []

    if not isinstance(document, dict):
        problems.append(
            f"{name}.yaml is a {type(document).__name__} at the top level and this schema "
            f"declares an object with a {key!r} key"
        )
        return []

    rows = document.get(key)
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        problems.append(f"{name}.yaml: {key} is a {type(rows).__name__} and the schema says array")
        return []
    if len(rows) > MAX_ENRICHMENT_ENTRIES:
        raise InventoryTooLarge(
            f"{name}.yaml", measured=len(rows), limit=MAX_ENRICHMENT_ENTRIES, unit="entries"
        )

    before = len(problems)
    problems.extend(
        f"{name}.yaml: {problem}"
        for problem in _validate(document, schema_for_document(name), where="")
    )
    problems.extend(f"{name}.yaml: {problem}" for problem in _screen(document, where=""))
    if len(problems) > before:
        return []

    return [row for row in rows if isinstance(row, dict)]


def _validate(value: Any, schema: Mapping[str, Any], *, where: str) -> list[str]:
    """Return every way ``value`` fails ``schema``, each named with its path.

    A deliberate subset of JSON Schema. Every keyword it implements is listed in
    ``SUPPORTED_KEYWORDS`` and a test refuses a bundled schema that uses one it
    does not — so this is smaller than the specification and never quieter than
    the schemas it is given.
    """
    problems: list[str] = []
    label = where or "the document"

    declared = schema.get("type")
    if isinstance(declared, str):
        expected = _JSON_TYPES.get(declared)
        matches = expected is not None and isinstance(value, expected)
        if declared in {"integer", "number"} and isinstance(value, bool):
            matches = False
        if not matches:
            return [f"{label} is a {type(value).__name__} and the schema declares {declared}"]

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", ()):
            if name not in value:
                problems.append(f"{label} declares no {name!r}, which the schema requires")
        if schema.get("additionalProperties") is False:
            problems.extend(
                f"{label} carries {name!r}, which the schema does not declare"
                for name in value
                if name not in properties
            )
        for name, child in value.items():
            if name in properties:
                problems.extend(
                    _validate(child, properties[name], where=f"{where}.{name}" if where else name)
                )

    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                problems.extend(_validate(item, item_schema, where=f"{where}[{index}]"))

    allowed = schema.get("enum")
    if isinstance(allowed, list) and value not in allowed:
        problems.append(f"{label} is not one of {allowed}")

    minimum = schema.get("minimum")
    if isinstance(minimum, int | float) and isinstance(value, int | float) and value < minimum:
        problems.append(f"{label} is {value}, below the declared minimum of {minimum}")

    return problems


def _screen(value: Any, *, where: str) -> list[str]:
    """Return the fields carrying something the guardrail ruleset recognises.

    Named without being quoted. The whole point of catching it here is that the
    value must not travel, and a refusal that echoed it would have published the
    secret in the error message that was complaining about it.
    """
    if isinstance(value, str):
        return (
            [f"{where} carries a value the guardrail ruleset recognises as a secret"]
            if _ENGINE.scan(value).text != value
            else []
        )
    if isinstance(value, dict):
        return [
            problem
            for name, child in value.items()
            for problem in _screen(child, where=f"{where}.{name}" if where else str(name))
        ]
    if isinstance(value, list):
        return [
            problem
            for index, item in enumerate(value)
            for problem in _screen(item, where=f"{where}[{index}]")
        ]
    return []


# --- turning documents into a plan --------------------------------------------


def _zone_map(zones: Sequence[Mapping[str, Any]], problems: list[str]) -> ZoneMap:
    """Return the declared networks as a zone map, or record why they are not one."""
    declared = [(str(entry["cidr"]), str(entry["name"])) for entry in zones]
    try:
        return zone_networks(declared)
    except ValueError as refused:
        problems.append(f"zones.yaml: {refused}")
        return ZoneMap()


def _annotations(
    documents: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    cluster: str,
) -> dict[str, dict[str, str]]:
    """Return every annotation the documents declare, keyed by correlation key."""
    annotations: dict[str, dict[str, str]] = {}

    for entry in documents["nodes"]:
        annotations.setdefault(str(entry["name"]), {}).update(_declared(entry))

    for document, kind in (("cts", "lxc"), ("vms", "qemu")):
        for entry in documents[document]:
            key = guest_key(cluster, kind, int(entry["vmid"]))
            annotations.setdefault(key, {}).update(_declared(entry))

    for entry in documents["services"]:
        vmid = entry.get("vmid")
        if not isinstance(vmid, int):
            continue
        served = _guest_of(documents, cluster=cluster, vmid=vmid)
        if served is not None:
            annotations.setdefault(served, {})["domain"] = str(entry["domain"])

    return annotations


def _declared(entry: Mapping[str, Any]) -> dict[str, str]:
    """Return the annotations one declared entry carries, omitting what it does not.

    Omitted rather than defaulted. "nobody has said how much this matters" and
    "somebody said it matters moderately" are different facts, and only one of
    them is a decision.
    """
    return {
        name: str(entry[name]) for name in _DECLARED_ANNOTATIONS if str(entry.get(name, "")).strip()
    }


def _guest_of(
    documents: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    cluster: str,
    vmid: int,
) -> str | None:
    """Return the correlation key for ``vmid``, or ``None`` when nothing declares it."""
    for document, kind in (("cts", "lxc"), ("vms", "qemu")):
        if any(entry.get("vmid") == vmid for entry in documents[document]):
            return guest_key(cluster, kind, vmid)
    return None


def _service_divergences(
    documents: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    cluster: str,
    annotated: set[str],
) -> list[Divergence]:
    """Return a divergence per service naming a guest the inventory does not declare."""
    del annotated
    found: list[Divergence] = []
    for entry in documents["services"]:
        vmid = entry.get("vmid")
        if not isinstance(vmid, int) or _guest_of(documents, cluster=cluster, vmid=vmid):
            continue
        found.append(
            Divergence(
                kind=DivergenceKind.ONLY_IN_FILE,
                subject=guest_key(cluster, "lxc", vmid),
                detail=(
                    f"services.yaml points {entry.get('domain', 'a domain')} at guest {vmid}, "
                    f"which no declared container or virtual machine names"
                ),
            )
        )
    return found


def guest_key(cluster: str, kind: str, vmid: int) -> str:
    """Return the correlation key one guest is matched on, from both sides.

    Deliberately the same expression the discovery source uses for a guest's
    ``correlation_key``. Written once, here, because a file and an API matched
    on two spellings of one identifier is a match that silently never happens.
    """
    return f"{cluster}/{kind}/{vmid}"


__all__ = [
    "ANNOTATED_KINDS",
    "INVENTORY_DOCUMENTS",
    "INVENTORY_SUBPATH",
    "REQUIRED_DOCUMENT",
    "SUPPORTED_KEYWORDS",
    "DirectoryInventory",
    "InventoryReader",
    "InventoryTooLarge",
    "domains_of",
    "guest_key",
    "ingest",
    "schema_for_document",
]
