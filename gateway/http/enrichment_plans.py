"""Reading the operator's declared inventory into the plans a sweep applies.

The ingestion in ``integrations/proxmox/enrichment.py`` reads five YAML
documents from a repository somebody maintains by hand, validates each against a
bundled schema, screens every value for credential shapes, and returns an
``EnrichmentPlan``. It was correct and uncalled: nothing in a running deployment
built a reader, and ``TopologyDiscoveryRunner.plans`` was never passed.

So every estate carried no criticality, no tier, no domain and no owner — the
four annotations the ingestion exists to produce. The zone survived only because
it is derived separately, from an address.

**The path is the integration's own option.** Which repository declares a
cluster is a fact about that cluster, and the integration entry already carries
the vendor's non-secret options. A new top-level setting would be a second place
to say where one cluster's inventory lives.

**Nothing here fails a boot.** A repository that moved, a document that no longer
validates, an inventory larger than the deployment will read — each loses the
annotations and keeps the sweep. An unannotated estate is a thing an operator can
fix at leisure; an empty one is not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from integrations.proxmox.enrichment import DirectoryInventory, ingest
from integrations.proxmox.schema import INTEGRATION as PROXMOX
from platform.estate.enrichment import EnrichmentPlan
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: What the option declaring the inventory repository is called.
INVENTORY_PATH_OPTION = "inventory_path"

#: What the option naming the cluster is called. The correlation key a file and
#: the API both chose begins with it.
CLUSTER_OPTION = "cluster"


def _vendor_settings(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the vendor's own settings on ``entry``, or an empty mapping.

    Spelled ``settings`` because that is what the schema calls the open block a
    vendor defines. Reading it under any other name finds nothing on a
    deployment that configured it correctly, which is the failure that looks
    exactly like not having configured it at all.
    """
    found = entry.get("settings") or {}
    return found if isinstance(found, Mapping) else {}


def inventory_path_of(entry: Mapping[str, Any]) -> str:
    """Return the repository root ``entry`` declares its inventory in, or empty."""
    return str(_vendor_settings(entry).get(INVENTORY_PATH_OPTION, "") or "").strip()


async def compose_enrichment_plans(
    entries: Sequence[Mapping[str, Any]], *, cluster: str
) -> dict[str, EnrichmentPlan]:
    """Return the enrichment plan each configured integration declared, by name.

    An entry that declares no inventory composes no plan rather than an empty
    one: an empty plan applied to a swept estate reports every resource as
    undeclared, which is a finding per resource about a file nobody wrote.
    """
    plans: dict[str, EnrichmentPlan] = {}
    for entry in entries:
        name = str(entry.get("name", ""))
        if name != PROXMOX:
            # The only ingestion there is. A second vendor's inventory would be
            # a second reader, not a branch here.
            continue
        root = inventory_path_of(entry)
        if not root:
            continue
        try:
            plans[name] = ingest(DirectoryInventory(root=Path(root)), cluster=cluster)
        except Exception as unreadable:  # noqa: BLE001 — annotations must not cost the sweep
            logger.warning(
                "estate.inventory_unreadable",
                integration=name,
                path=root,
                error=str(unreadable),
            )

    logger.info("estate.enrichment_plans_composed", integrations=sorted(plans))
    return plans


async def compose_enrichment_plans_for(state: Any, *, org_id: str) -> Mapping[str, EnrichmentPlan]:
    """Put the plans this deployment's configured inventories describe on ``state``.

    Reads the same integration entries the discovery sources are composed from,
    so an operator declares the repository beside the cluster it describes.
    """
    from gateway.http.discovery_sources import _active_integrations

    try:
        entries = await _active_integrations(state, org_id)
    except Exception as unreadable:  # noqa: BLE001 — annotations must not stop a boot
        logger.warning("estate.enrichment_unreadable", error=str(unreadable))
        state.enrichment_plans = {}
        return {}

    plans = await compose_enrichment_plans(entries, cluster=_cluster_of(entries))
    state.enrichment_plans = plans
    return plans


def _cluster_of(entries: Sequence[Mapping[str, Any]]) -> str:
    """Return the cluster name the declared inventory keys its guests by.

    An option rather than a guess: the correlation key a file and the API both
    chose starts with the cluster's own name, and a wrong one annotates nothing
    while looking like an inventory nobody wrote.
    """
    for entry in entries:
        if str(entry.get("name", "")) == PROXMOX:
            return str(_vendor_settings(entry).get(CLUSTER_OPTION, "") or "").strip()
    return ""


__all__ = [
    "CLUSTER_OPTION",
    "INVENTORY_PATH_OPTION",
    "compose_enrichment_plans",
    "compose_enrichment_plans_for",
    "inventory_path_of",
]
