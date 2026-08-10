"""The demonstration dataset, read from the fixture tree, and its coherence.

This reads `fixtures/` directly rather than going through the tooling that
built it. That is deliberate and it is the only honest option: `tools/` is
repository tooling, not a packaged runtime, and a deployment that imported it to
serve a demonstration would be a shipped product depending on a directory the
package does not include. The fixture tree, by contrast, is data — the root
`AGENTS.md` already names the demo seeder as one of its three readers.

What is shared is the vocabulary, not the code: the label field, the label value
and the organisation live in `config/constants/fixtures.py`, so the tooling that
writes the dataset and the seeder that loads it cannot disagree about them.

**Coherence is asserted rather than assumed.** ``unresolved_references`` walks
every reference the dataset makes and returns the ones that do not land. A
demonstration where a run cites a resource that is not there looks fine on the
runs screen and falls apart the moment somebody clicks through, which is the
failure a screenshot never catches.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from config.constants.fixtures import (
    DEFAULT_FIXTURE_SCENARIO,
    FIXTURE_MANIFEST_FILENAME,
    FIXTURE_ROOT_DIR_NAME,
    FIXTURE_SCENARIO_DIR_NAME,
    NINJASRE_FIXTURE_ROOT_ENV,
)
from platform.estate.alert_resolution import UNRESOLVED_TARGET_PREFIX

#: Where the tree is when nothing says otherwise: the repository root, four
#: directories above this module.
_DEFAULT_ROOT = Path(__file__).resolve().parents[3] / FIXTURE_ROOT_DIR_NAME


def fixture_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return where the dataset lives on this host."""
    source = environ if environ is not None else os.environ
    configured = source.get(NINJASRE_FIXTURE_ROOT_ENV)
    return Path(configured) if configured else _DEFAULT_ROOT


# Not ``slots=True``, unlike almost everything else here: the collections below
# are ``cached_property``, which caches into the instance ``__dict__`` a slotted
# class does not have. The dataset is read dozens of times while seeding and
# re-deriving the topology's node set each time is measurable against NFR-002.
@dataclass(frozen=True)
class DemoDataset:
    """One scenario's answers, keyed by the endpoint that would have served them."""

    scenario: str
    bodies: Mapping[str, Mapping[str, Any]]

    def body(self, slug: str) -> Mapping[str, Any]:
        """Return one endpoint's answer, or an empty mapping if it has none."""
        return self.bodies.get(slug, {})

    def rows(self, slug: str, key: str) -> tuple[Mapping[str, Any], ...]:
        """Return one collection out of one endpoint's answer."""
        found = self.body(slug).get(key)
        if not isinstance(found, Sequence) or isinstance(found, str | bytes):
            return ()
        return tuple(row for row in found if isinstance(row, Mapping))

    # The collections the seeder loads. Named properties rather than string keys
    # at each call site, so a renamed fixture breaks in one place.

    @cached_property
    def config_nodes(self) -> tuple[Mapping[str, Any], ...]:
        """Return the organisation tree."""
        return self.rows("config-tree", "nodes")

    @cached_property
    def organisation_id(self) -> str:
        """Return the tenant this deployment lives in, read from its own tree.

        Read rather than declared. The identifier of the fictional deployment
        belongs to the dataset that defines it, and writing it down a second time
        in the code that loads it is how a second fictional deployment starts —
        which is a property ``tests/architecture/
        test_one_fictional_deployment.py`` enforces rather than merely prefers.
        """
        for row in self.config_nodes:
            if not row.get("parent_id"):
                return str(row.get("node_id", ""))
        return ""

    @cached_property
    def organisation_name(self) -> str:
        """Return what that tenant is called, from the same row."""
        for row in self.config_nodes:
            if not row.get("parent_id"):
                return str(row.get("name") or row.get("node_id", ""))
        return ""

    @cached_property
    def guests(self) -> tuple[Mapping[str, Any], ...]:
        """Return the containers and virtual machines."""
        return self.rows("estate-resources", "resources")

    @cached_property
    def nodes(self) -> tuple[Mapping[str, Any], ...]:
        """Return the cluster's hosts."""
        return self.rows("estate-nodes", "nodes")

    @cached_property
    def datastores(self) -> tuple[Mapping[str, Any], ...]:
        """Return the storage the guests live on."""
        return self.rows("estate-storage", "datastores")

    @cached_property
    def thin_pools(self) -> tuple[Mapping[str, Any], ...]:
        """Return the thin pools behind the local storage."""
        return self.rows("estate-storage", "thin_pools")

    @cached_property
    def backup_jobs(self) -> tuple[Mapping[str, Any], ...]:
        """Return the backup jobs, including the one that is disabled."""
        return self.rows("estate-backups", "jobs")

    @cached_property
    def incidents(self) -> tuple[Mapping[str, Any], ...]:
        """Return the open and closed incidents."""
        return self.rows("incidents", "incidents")

    @cached_property
    def timeline(self) -> tuple[Mapping[str, Any], ...]:
        """Return the timeline of the one incident the capture detailed."""
        return self.rows("incident-detail", "timeline")

    @cached_property
    def detailed_incident(self) -> Mapping[str, Any]:
        """Return the incident the timeline belongs to."""
        found = self.body("incident-detail").get("incident")
        return found if isinstance(found, Mapping) else {}

    @cached_property
    def observations(self) -> tuple[Mapping[str, Any], ...]:
        """Return what the detectors found."""
        return self.rows("observations", "observations")

    @cached_property
    def runs(self) -> tuple[Mapping[str, Any], ...]:
        """Return the completed and running investigations."""
        return self.rows("runs", "runs")

    @cached_property
    def replay_turns(self) -> tuple[Mapping[str, Any], ...]:
        """Return the turns of the one run the capture replayed."""
        return self.rows("run-replay", "turns")

    @cached_property
    def replayed_run_id(self) -> str:
        """Return which run those turns belong to."""
        return str(self.body("run-replay").get("run_id", ""))

    @cached_property
    def episodes(self) -> tuple[Mapping[str, Any], ...]:
        """Return what was learned from the runs."""
        return self.rows("episodes", "episodes")

    @cached_property
    def approvals(self) -> tuple[Mapping[str, Any], ...]:
        """Return the decisions waiting on a person, with their rollback plans."""
        return self.rows("approvals", "approvals")

    @cached_property
    def topology_nodes(self) -> tuple[Mapping[str, Any], ...]:
        """Return every distinct node the topology answer mentions."""
        body = self.body("topology")
        seen: dict[str, Mapping[str, Any]] = {}
        for row in (*self.rows("topology", "dependencies"), *self.rows("topology", "dependents")):
            seen[str(row.get("node_id", ""))] = row
        for entry in self.rows("topology", "blast_radius"):
            node = entry.get("node")
            if isinstance(node, Mapping):
                seen[str(node.get("node_id", ""))] = node
        origin = str(body.get("node_id", ""))
        if origin:
            seen.setdefault(origin, {"node_id": origin, "kind": "service", "name": origin})
        seen.pop("", None)
        return tuple(seen[key] for key in sorted(seen))

    @cached_property
    def topology_edges(self) -> tuple[tuple[str, str], ...]:
        """Return the edges the topology answer describes, as ``(from, to)``.

        The origin depends on its dependencies and its dependents depend on it,
        which is the direction the answer is written from and the direction the
        graph has to be stored in.
        """
        origin = str(self.body("topology").get("node_id", ""))
        if not origin:
            return ()
        edges = [
            (origin, str(row.get("node_id", ""))) for row in self.rows("topology", "dependencies")
        ]
        edges.extend(
            (str(row.get("node_id", "")), origin) for row in self.rows("topology", "dependents")
        )
        return tuple(edge for edge in edges if all(edge))


def _read(path: Path) -> Mapping[str, Any] | None:
    """Return the first successful GET body a fixture file records."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    responses = document.get("responses") if isinstance(document, Mapping) else None
    if not isinstance(responses, Sequence):
        return None
    for response in responses:
        if not isinstance(response, Mapping):
            continue
        if int(response.get("status", 0)) >= 400:
            continue
        body = response.get("body")
        if isinstance(body, Mapping):
            return body
    return None


def _scenario_chain(root: Path, scenario: str) -> Iterator[str]:
    """Yield ``scenario`` and every scenario it derives from, nearest first."""
    manifest_path = root / FIXTURE_MANIFEST_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        yield scenario
        return

    by_name = {
        str(entry.get("name")): entry
        for entry in manifest.get("scenarios", [])
        if isinstance(entry, Mapping)
    }
    seen: set[str] = set()
    current: str | None = scenario
    while current and current not in seen:
        seen.add(current)
        yield current
        entry = by_name.get(current)
        current = str(entry.get("derives_from")) if entry and entry.get("derives_from") else None


def load_dataset(
    scenario: str = DEFAULT_FIXTURE_SCENARIO,
    *,
    root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> DemoDataset:
    """Return the named scenario, with anything it inherits filled in behind it.

    Raises:
        FileNotFoundError: the fixture tree is not where it was looked for. A
            demonstration that silently produced an empty deployment would be
            indistinguishable from the empty console this feature exists to fix.
    """
    tree = root if root is not None else fixture_root(environ)
    if not tree.is_dir():
        raise FileNotFoundError(
            f"the fixture tree is not at {tree}. Demo mode loads the committed dataset; "
            f"set {NINJASRE_FIXTURE_ROOT_ENV} if it lives elsewhere in this deployment."
        )

    bodies: dict[str, Mapping[str, Any]] = {}
    for name in _scenario_chain(tree, scenario):
        directory = tree / FIXTURE_SCENARIO_DIR_NAME / name
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            # ``setdefault``: the nearest scenario in the chain wins, which is
            # what "derives from, with overrides" means.
            body = _read(path)
            if body is not None:
                bodies.setdefault(path.stem, body)

    if not bodies:
        raise FileNotFoundError(
            f"no scenario named {scenario!r} under {tree / FIXTURE_SCENARIO_DIR_NAME}"
        )
    return DemoDataset(scenario=scenario, bodies=bodies)


# --- Coherence --------------------------------------------------------------------


def estate_identifiers(dataset: DemoDataset) -> frozenset[str]:
    """Return every identifier the seeded estate will hold.

    The estate is not one fixture. Guests, hosts, datastores, thin pools and
    backup jobs are five separate reads of the same deployment, and an incident
    about a datastore refers to something that is only in the third of them.
    """
    identifiers = {str(row.get("resource_id", "")) for row in dataset.guests}
    identifiers |= {str(row.get("node_id", "")) for row in dataset.nodes}
    identifiers |= {str(row.get("name", "")) for row in dataset.datastores}
    identifiers |= {str(row.get("name", "")) for row in dataset.thin_pools}
    identifiers |= {str(row.get("job_id", "")) for row in dataset.backup_jobs}
    identifiers.add(CLUSTER_RESOURCE_ID)
    identifiers.discard("")
    return frozenset(identifiers)


#: The cluster itself, which every capture describes and none of them lists as a
#: row. It is derived from the hosts' own quorum arithmetic rather than invented:
#: the votes, the expected votes and the member names all come from the nodes.
CLUSTER_RESOURCE_ID = "cluster"
CLUSTER_RESOURCE_KIND = "cluster"


def component_identifiers(dataset: DemoDataset) -> frozenset[str]:
    """Return everything an episode may name as a component.

    Wider than the resource identifiers, and deliberately so. A component key is
    what a person calls the thing that went wrong, and in this capture that is a
    guest's display name, a host's short name, or the systemd unit that failed on
    it. All three are values the capture recorded, so a component naming one is
    resolved rather than dangling — but a component naming something the capture
    never saw still fails, which is the property the check is for.
    """
    identifiers = set(estate_identifiers(dataset))
    identifiers |= {str(row.get("display_name", "")) for row in dataset.guests}
    identifiers |= {str(row.get("native_id", "")) for row in dataset.guests}
    identifiers |= {str(row.get("name", "")) for row in dataset.nodes}
    for node in dataset.nodes:
        units = node.get("failed_units")
        if isinstance(units, Sequence) and not isinstance(units, str | bytes):
            identifiers |= {str(unit) for unit in units}
    identifiers.discard("")
    return frozenset(identifiers)


def unresolved_references(dataset: DemoDataset) -> tuple[str, ...]:
    """Return every reference in the dataset that does not land, in a readable form.

    FR-016 and SC-007. Returned rather than raised so a caller can report all of
    them at once, which is the same reason the self-check reports in one pass.
    """
    resources = estate_identifiers(dataset)
    components = component_identifiers(dataset)
    runs = {str(row.get("run_id", "")) for row in dataset.runs}
    topology = {str(row.get("node_id", "")) for row in dataset.topology_nodes}

    broken: list[str] = []

    for row in dataset.guests:
        parent = str(row.get("parent_id") or "")
        if parent and parent not in resources:
            broken.append(f"resource {row.get('resource_id')} has parent {parent}, which is absent")

    for incident in dataset.incidents:
        for subject in incident.get("subjects", ()):
            # An unresolved alert target is a subject that is *deliberately* not
            # a resource: it is the record that an alert arrived for something
            # this estate does not hold, and a check that demanded it resolve
            # would be demanding the finding be about the thing whose absence it
            # reports.
            if str(subject).startswith(UNRESOLVED_TARGET_PREFIX):
                continue
            if str(subject) not in resources:
                broken.append(
                    f"incident {incident.get('incident_id')} is about {subject}, which is absent"
                )
        run_id = incident.get("run_id")
        if run_id and str(run_id) not in runs:
            broken.append(
                f"incident {incident.get('incident_id')} cites run {run_id}, which is absent"
            )

    for episode in dataset.episodes:
        run_id = episode.get("run_id")
        if run_id and str(run_id) not in runs:
            broken.append(
                f"episode {episode.get('episode_id')} cites run {run_id}, which is absent"
            )
        for component in episode.get("components", ()):
            if str(component) not in components:
                broken.append(
                    f"episode {episode.get('episode_id')} is about {component}, which is absent"
                )

    for approval in dataset.approvals:
        run_id = approval.get("run_id")
        if run_id and str(run_id) not in runs:
            broken.append(
                f"approval {approval.get('approval_id')} cites run {run_id}, which is absent"
            )
        plan = approval.get("rollback_plan")
        if isinstance(plan, Mapping) and str(plan.get("approval_id")) != str(
            approval.get("approval_id")
        ):
            broken.append(
                f"approval {approval.get('approval_id')} holds a rollback plan for "
                f"{plan.get('approval_id')}"
            )

    for observation in dataset.observations:
        subject = str(observation.get("subject", ""))
        if subject and subject not in resources:
            broken.append(
                f"observation {observation.get('observation_id')} is about {subject}, "
                f"which is absent"
            )

    if dataset.replayed_run_id and dataset.replayed_run_id not in runs:
        broken.append(f"the replayed transcript belongs to run {dataset.replayed_run_id}, absent")

    for origin, target in dataset.topology_edges:
        for end in (origin, target):
            if end not in topology:
                broken.append(f"topology edge {origin}->{target} names {end}, which is absent")

    return tuple(broken)


__all__ = [
    "CLUSTER_RESOURCE_ID",
    "CLUSTER_RESOURCE_KIND",
    "DemoDataset",
    "component_identifiers",
    "estate_identifiers",
    "fixture_root",
    "load_dataset",
    "unresolved_references",
]
