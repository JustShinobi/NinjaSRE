"""The label rules for the exporters a Proxmox homelab actually runs.

Shipped rather than configured, and that is the difference between a feature an
operator can use on the first afternoon and one they configure for a week. The
label schemes of ``prometheus-pve-exporter`` and ``node_exporter`` are stable
across releases and identical across deployments; everything else about a
metrics system is not, and everything else is therefore configuration.

**What the rules can know and what they cannot.** A Proxmox guest's estate
identity carries the cluster name and the guest's creation time, because those
are what keep VMID 100 distinct from the VMID 100 before it. Neither appears in
a metric label, so both are wildcards here. On a single cluster that resolves
exactly; on two clusters sharing a VMID it is ambiguous and the mapping says so,
which is when an operator declares a rule of their own carrying a ``cluster``
label. That is the correct order — the shipped rules serve the common case and
the ambiguity is visible rather than silently resolved the wrong way.

**A guest's own exporter is claimed before the machine rule.** Both publish
``node_*``; what tells them apart is that an operator scraping inside a guest
labels the target with its VMID. Ordering is the mechanism, and it is declared
here rather than emerging from a dictionary's iteration order.
"""

from __future__ import annotations

from typing import Final

from config.constants.observability_bridge import PROXMOX_ESTATE_SOURCE
from platform.estate.kinds import (
    KIND_CONTAINER,
    KIND_DATASTORE,
    KIND_NODE,
    KIND_VIRTUAL_MACHINE,
)
from platform.observation.bridge.mapping import LabelRule, SeriesView

#: What ``prometheus-pve-exporter`` publishes about the cluster it reads. Every
#: series carries an ``id`` in Proxmox's own ``kind/...`` form, which is what
#: makes one exporter's output splittable into four kinds of resource.
PROXMOX_EXPORTER_RULES: Final[tuple[LabelRule, ...]] = (
    LabelRule(
        rule_id="pve-exporter-node",
        metric_prefixes=("pve_",),
        resource_kind=KIND_NODE,
        integration=PROXMOX_ESTATE_SOURCE,
        native_template="node/*/{id:-1}",
        when_labels={"id": "node/"},
        view=SeriesView.HYPERVISOR,
        description=(
            "prometheus-pve-exporter labels a node's series id=\"node/<name>\"; a node's "
            "estate identity is its cluster and that name"
        ),
    ),
    LabelRule(
        rule_id="pve-exporter-container",
        metric_prefixes=("pve_",),
        resource_kind=KIND_CONTAINER,
        integration=PROXMOX_ESTATE_SOURCE,
        native_template="lxc/*/*/{id:-1}",
        when_labels={"id": "lxc/"},
        view=SeriesView.HYPERVISOR,
        description=(
            'id="lxc/<vmid>". The cluster and the guest\'s creation time are wildcards '
            "because no metric label carries either; a second cluster sharing a VMID "
            "makes the join ambiguous and it is reported rather than guessed"
        ),
    ),
    LabelRule(
        rule_id="pve-exporter-virtual-machine",
        metric_prefixes=("pve_",),
        resource_kind=KIND_VIRTUAL_MACHINE,
        integration=PROXMOX_ESTATE_SOURCE,
        native_template="qemu/*/*/{id:-1}",
        when_labels={"id": "qemu/"},
        view=SeriesView.HYPERVISOR,
        description='id="qemu/<vmid>", the same shape as a container\'s',
    ),
    LabelRule(
        rule_id="pve-exporter-datastore",
        metric_prefixes=("pve_",),
        resource_kind=KIND_DATASTORE,
        integration=PROXMOX_ESTATE_SOURCE,
        native_template="datastore/*/{id:1}/{id:2}",
        when_labels={"id": "storage/"},
        view=SeriesView.HYPERVISOR,
        description=(
            'id="storage/<node>/<name>". The node is part of the identity because a '
            "share visible from two nodes is two resources, and on a real cluster the "
            "two views disagree about whether it is available"
        ),
    ),
)

#: What an exporter running *inside* a guest publishes. Claimed before the
#: machine rule below, because both are ``node_*`` and only the VMID label tells
#: them apart.
GUEST_EXPORTER_RULES: Final[tuple[LabelRule, ...]] = (
    LabelRule(
        rule_id="guest-exporter-container",
        metric_prefixes=("node_",),
        resource_kind=KIND_CONTAINER,
        integration=PROXMOX_ESTATE_SOURCE,
        native_template="lxc/*/*/{vmid}",
        when_labels={"type": "lxc"},
        view=SeriesView.GUEST,
        description=(
            "a container scraping itself, labelled with its own vmid. Kept as a "
            "separate view from the hypervisor's: 12% of a node and 60% of a container "
            "are different denominators, not a disagreement"
        ),
    ),
    LabelRule(
        rule_id="guest-exporter-virtual-machine",
        metric_prefixes=("node_",),
        resource_kind=KIND_VIRTUAL_MACHINE,
        integration=PROXMOX_ESTATE_SOURCE,
        native_template="qemu/*/*/{vmid}",
        when_labels={"type": "qemu"},
        view=SeriesView.GUEST,
        description="a virtual machine scraping itself, labelled with its own vmid",
    ),
)

#: What ``node_exporter`` on a hypervisor publishes, including the readings the
#: textfile collector writes. The scrape target is ``host:port``; the host is
#: the node's own name, which is its estate identity.
NODE_EXPORTER_RULES: Final[tuple[LabelRule, ...]] = (
    LabelRule(
        rule_id="node-exporter-machine",
        metric_prefixes=("node_",),
        resource_kind=KIND_NODE,
        integration=PROXMOX_ESTATE_SOURCE,
        native_template="node/*/{instance:host}",
        view=SeriesView.NODE,
        description=(
            'instance="<node>:9100". This is also how the textfile collector\'s '
            "readings arrive — failed units, bridge state and thin-pool metadata are "
            "node_* series like any other"
        ),
    ),
)

#: Every rule this deployment ships, in the order they are tried. Order is part
#: of the declaration: a guest's own exporter and a hypervisor's node exporter
#: publish the same metric names, and which one claims a series decides which
#: resource the series lands on.
SHIPPED_RULES: Final[tuple[LabelRule, ...]] = (
    *PROXMOX_EXPORTER_RULES,
    *GUEST_EXPORTER_RULES,
    *NODE_EXPORTER_RULES,
)

__all__ = [
    "GUEST_EXPORTER_RULES",
    "NODE_EXPORTER_RULES",
    "PROXMOX_EXPORTER_RULES",
    "SHIPPED_RULES",
]
