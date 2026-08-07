"""Putting the fault on the cluster, declaratively, and never losing track of it.

Two decisions, both about the moment things go wrong.

**The manifest is checked before it is applied.** Only the chaos framework's own
API group is allowed through, because that is the set of objects cleanup knows
how to remove — and an experiment that applied a Deployment would be a fault
this suite created and cannot undo.

**The fault is registered before it exists.** Registering afterwards leaves a
window in which the object is on the cluster and nothing is responsible for it,
and an interruption landing in that window leaks exactly the kind of fault
somebody notices a week later. So the ledger is written first and an apply that
*fails* leaves the registration behind: a refused apply may still have created
the object, and one unnecessary deletion is cheaper than one leaked fault.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from config.constants.chaos import CHAOS_API_GROUP
from tests.chaos.framework.catalogue import Experiment
from tests.chaos.framework.cleanup import CleanupLedger, FaultRecord
from tests.chaos.framework.cluster import Cluster, ClusterResource, suite_labels


class InjectionError(Exception):
    """A fault could not be applied, or should not have been."""


@dataclass(frozen=True, slots=True)
class InjectedFault:
    """One fault, on the cluster, and the record responsible for removing it."""

    experiment_id: str
    record: FaultRecord
    resource: ClusterResource


def prepare_manifest(
    manifest: Mapping[str, Any], *, experiment_id: str, run_id: str
) -> dict[str, Any]:
    """Return ``manifest`` ready to apply: labelled, named for this run, checked.

    The run identifier is appended to the object's name so two runs against two
    clusters — or one cluster after a sweep — never collide on a name that is
    still terminating.

    Raises:
        InjectionError: the manifest is not a fault this suite can remove.
    """
    api_version = str(manifest.get("apiVersion", ""))
    if not api_version.startswith(f"{CHAOS_API_GROUP}/"):
        raise InjectionError(
            f"{experiment_id}: chaos.yaml declares apiVersion {api_version!r}; only "
            f"{CHAOS_API_GROUP} objects may be applied, because those are the ones cleanup knows "
            f"how to remove"
        )

    kind = str(manifest.get("kind", ""))
    metadata = dict(manifest.get("metadata") or {})
    name = str(metadata.get("name", ""))
    if not kind or not name:
        raise InjectionError(f"{experiment_id}: chaos.yaml needs a kind and a metadata.name")

    prepared = dict(manifest)
    metadata["name"] = f"{name}-{run_id}" if run_id else name
    metadata["labels"] = {**dict(metadata.get("labels") or {}), **suite_labels(experiment_id)}
    prepared["metadata"] = metadata
    return prepared


def inject(
    cluster: Cluster, experiment: Experiment, *, ledger: CleanupLedger, run_id: str
) -> InjectedFault:
    """Apply ``experiment``'s fault to ``cluster`` and return what was applied.

    Raises:
        InjectionError: the manifest was refused, or the cluster would not take it.
    """
    manifest = prepare_manifest(
        experiment.manifest, experiment_id=experiment.experiment_id, run_id=run_id
    )
    metadata = manifest["metadata"]
    record = ledger.register(
        FaultRecord(
            experiment_id=experiment.experiment_id,
            kind=str(manifest["kind"]),
            name=str(metadata["name"]),
            namespace=str(metadata.get("namespace", "")),
        )
    )

    try:
        resource = cluster.apply(manifest)
    except Exception as failure:  # noqa: BLE001 - re-raised as this layer's error
        raise InjectionError(
            f"{experiment.experiment_id}: the cluster refused the fault ({failure}); it stays "
            f"registered for removal in case it was created anyway"
        ) from failure

    return InjectedFault(experiment_id=experiment.experiment_id, record=record, resource=resource)


__all__ = ["InjectedFault", "InjectionError", "inject", "prepare_manifest"]
