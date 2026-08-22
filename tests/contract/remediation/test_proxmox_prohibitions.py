"""The hole in the hypervisor write set, asserted over the whole registry.

In a two-node cluster the system cannot distinguish a dead node from an
unreachable one, and both wrong answers are expensive: fencing a live node kills
guests that are still serving, and starting its guests elsewhere while it still
runs them corrupts shared state. No autonomy level should be able to resolve that
ambiguity, so no capability offers it.

The assertions below are deliberately over the *registry* and over the *client's
whole write surface* rather than over a list of capability names. A list has to
be maintained; a sweep fails the day somebody adds the fourteenth write in a
prohibited category, which is the failure this file exists to produce.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from capabilities.tools.remediation import COMPONENTS
from capabilities.tools.remediation import proxmox as hypervisor
from capabilities.tools.remediation.proxmox import plane, risk
from capabilities.tools.remediation.proxmox.declaration import RegistrationRefused
from integrations.proxmox import writes
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.risk import RiskClass

pytestmark = pytest.mark.contract

#: The four services a Proxmox node reaches the cluster through. Named here
#: exactly as an operator would name them, because the requirement names them.
NODE_SERVICES = ("pveproxy", "pvedaemon", "pve-cluster", "corosync")

#: Every path any hypervisor capability declares it writes, plus every path the
#: write client is able to reach. Both, because a capability could declare one
#: endpoint and a client method could offer another.
DECLARED_PATHS = tuple(
    declaration.endpoint for declaration in hypervisor.DECLARATIONS.values()
) + tuple(path for _, path in writes.WRITE_ENDPOINTS)


@pytest.mark.parametrize("path", DECLARED_PATHS, ids=DECLARED_PATHS)
def test_no_write_this_deployment_can_make_is_a_prohibited_operation(path: str) -> None:
    """One sweep over declarations and client methods together."""
    forbidden = risk.prohibition_for(path)

    assert forbidden is None, f"{path} is a {forbidden.name} operation: {forbidden.why}"


@pytest.mark.parametrize("service", NODE_SERVICES)
def test_no_write_can_restart_a_node_service(service: str) -> None:
    """These are how the system reaches the cluster; restarting one is a proposal."""
    for path in DECLARED_PATHS:
        assert service not in path, f"{path} would restart {service}"


def test_no_write_can_alter_a_nodes_network_configuration() -> None:
    """Interfaces, bridges, bonds and routes are owned by a declarative control plane.

    A second writer here turns drift into an outage, and the reference cluster's
    only total outage needed physical access to recover from.
    """
    for path in DECLARED_PATHS:
        for owned in ("/network", "/hosts", "/dns", "interfaces"):
            assert owned not in path, f"{path} writes network configuration"


def test_no_write_can_extend_a_thin_pool_or_a_zfs_pool() -> None:
    """Spending a node's only spare capacity is a decision with a budget attached."""
    for path in DECLARED_PATHS:
        assert "/disks/" not in path, f"{path} reaches a node's own storage devices"

    assert risk.prohibition_for("/nodes/pve01/disks/lvmthin") is not None
    assert risk.prohibition_for("/nodes/pve01/disks/zfs") is not None


def test_a_capability_in_a_prohibited_category_cannot_be_registered() -> None:
    """The hole cannot be filled in by accident, only by editing the prohibition."""
    from tests.unit.capabilities.remediation.test_proxmox_declaration import declaration

    for path in (
        "/cluster/config/totem",
        "/cluster/config/qdevice",
        "/nodes/{node}/network",
        "/nodes/{node}/services",
        "/nodes/{node}/disks/zfs",
    ):
        with pytest.raises(RegistrationRefused):
            declaration(endpoint=path)


def test_no_registered_capability_is_autonomously_available_in_a_prohibited_category() -> None:
    """At any level, including the most permissive one an operator can configure.

    The property holds because no such capability is registered, and that is the
    assertion: the set of registered capabilities whose endpoint is prohibited is
    empty, so there is nothing for any level to permit.
    """
    for level in AutonomyLevel:
        offered = [
            name
            for name, declared in hypervisor.DECLARATIONS.items()
            if risk.prohibition_for(declared.endpoint) is not None
        ]

        assert offered == [], f"{level.value} would offer {offered}"


def test_the_writer_map_and_the_registry_name_the_same_capabilities() -> None:
    """Except the storage deletions, which are performed by the volume loop.

    A capability registered with no writer would refuse at the point of the
    write, which is late; a writer with no capability is a path nothing gates.
    """
    written = set(plane._WRITERS)  # noqa: SLF001 — the map is the subject of the assertion
    storage = {
        name
        for name, declared in hypervisor.DECLARATIONS.items()
        if declared.category.value == "storage"
    }

    assert written | storage == set(hypervisor.DECLARATIONS)
    assert not written & storage


# --- No action holds a credential ---------------------------------------------

#: Every module this feature adds, as source. Read from disk rather than
#: imported and introspected, because what is being asserted is that a lookup is
#: not written anywhere — including in a branch nothing takes.
SOURCES = tuple(sorted(Path("capabilities/tools/remediation/proxmox").glob("*.py"))) + (
    Path("integrations/proxmox/writes.py"),
)


@pytest.mark.parametrize("source", SOURCES, ids=[path.name for path in SOURCES])
def test_no_module_reads_the_process_environment(source: Path) -> None:
    """Configuration comes from the hierarchy and credentials come from the proxy."""
    text = source.read_text(encoding="utf-8")

    for lookup in ("os.environ", "getenv", "environ["):
        assert lookup not in text, f"{source}: reads the environment with {lookup}"


def test_the_write_client_has_no_way_to_be_given_a_credential() -> None:
    """Structural. There is no parameter to pass one to and no attribute to hold it.

    ``base_url`` is where the cluster is, not how to authenticate to it: an
    address is public configuration, it is what an operator types into the
    catalogue, and the proxy still decides whether the host it names may be
    reached. Pinning the whole set rather than only the absences is what makes a
    parameter added later a decision somebody takes deliberately.
    """
    parameters = set(inspect.signature(writes.ProxmoxWriteClient.__init__).parameters)

    assert parameters == {
        "self",
        "transport",
        "context",
        "endpoints",
        "trust",
        "base_url",
        "retry",
    }


@pytest.mark.parametrize(
    "method",
    sorted(
        name
        for name, value in vars(writes.ProxmoxWriteClient).items()
        if not name.startswith("_") and callable(value)
    ),
)
def test_no_write_method_takes_anything_that_could_be_a_credential(method: str) -> None:
    """A parameter that could carry one is a parameter something eventually will."""
    signature = inspect.signature(getattr(writes.ProxmoxWriteClient, method))

    for name in signature.parameters:
        assert not any(
            word in name.lower()
            for word in ("token", "secret", "password", "credential", "api_key", "ticket")
        ), f"{method}({name})"


def test_the_control_plane_carries_a_client_rather_than_a_secret() -> None:
    """The whole of NFR-001, structurally: there is nowhere for one to live."""
    fields = set(plane.ProxmoxControlPlane.__dataclass_fields__)

    assert fields == {"client", "declarations", "rate_limit_mbps", "evidence"}


def test_every_hypervisor_write_is_registered_as_a_gated_remediation() -> None:
    """A write outside the registry is a write outside the gate."""
    gated = {bundle.capability for bundle in COMPONENTS}

    assert set(hypervisor.DECLARATIONS) <= gated


def test_every_privilege_a_write_needs_is_one_verification_asks_about() -> None:
    """A privilege nobody would have been asked for fails the build, not an evening.

    Verification reports read and write sufficiency separately, so an operator
    is told once whether the token they pasted would also support remediation.
    That answer is only true if the list it is computed from covers every write
    that shipped.
    """
    from integrations.proxmox.privileges import WRITE_PRIVILEGES

    declared = {(found.privilege, found.path) for found in WRITE_PRIVILEGES}
    needed = {
        (privilege.privilege, privilege.path)
        for declaration in hypervisor.DECLARATIONS.values()
        for privilege in declaration.privileges
    }

    assert needed <= declared, f"never asked for: {sorted(needed - declared)}"


def test_every_data_losing_write_is_classified_at_the_top_of_the_scale() -> None:
    """Asserted over the registry rather than over the table, so both have to agree."""
    for name, declared in hypervisor.DECLARATIONS.items():
        if not declared.row.loses_data:
            continue
        assert declared.risk_class is RiskClass.CRITICAL, name
