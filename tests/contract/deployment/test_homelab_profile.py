"""The deployment an individual actually runs, asserted against its own declaration.

The homelab profile is the assembly this wave exists to produce: one host, one
command, a declared footprint it stays inside, and nothing a multi-team
deployment would need. Every property here is a property of the files rather
than of a running stack, for the reason the rest of this suite gives — a check
that needed a Docker daemon is a check that runs once a week.

The footprint is the load-bearing one. It is declared in
``config.constants.deployment`` and written into the compose file as per-service
limits, and this is where the two are made to agree: a profile that claimed four
gibibytes and shipped a file with no limits in it would be making a promise
nothing keeps.
"""

from __future__ import annotations

from typing import Any

import pytest

from config.constants.deployment import (
    DEPLOYMENT_PROFILE_HOMELAB,
    HOMELAB_CPU_LIMITS,
    HOMELAB_MEMORY_LIMITS_MIB,
    HOMELAB_PROFILE_CONTAINER_COUNT,
    HOMELAB_PROFILE_SERVICES,
    HOMELAB_TOTAL_CPUS,
    HOMELAB_TOTAL_MEMORY_MIB,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
)
from config.constants.llm import (
    OLLAMA_BASE_URL_ENV,
    VLLM_BASE_URL_ENV,
)
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from platform.startup.profiles import DeploymentProfile, topology_for

pytestmark = pytest.mark.contract


def test_the_homelab_profile_is_the_four_components_it_promises(
    homelab_compose: dict[str, Any],
) -> None:
    """FR-003: database, gateway, console and credential proxy, and nothing else."""
    services = homelab_compose["services"]

    assert set(services) == set(HOMELAB_PROFILE_SERVICES)
    assert len(services) == HOMELAB_PROFILE_CONTAINER_COUNT


def test_the_compose_file_and_the_topology_the_code_reports_agree(
    homelab_compose: dict[str, Any],
) -> None:
    topology = topology_for(DeploymentProfile.HOMELAB)

    assert set(homelab_compose["services"]) == set(topology.services)
    assert len(homelab_compose["services"]) == topology.container_count


def test_the_profile_declares_itself_so_the_running_process_knows_which_it_is(
    homelab_compose: dict[str, Any],
) -> None:
    environment = homelab_compose["services"]["app"]["environment"]

    assert DEPLOYMENT_PROFILE_HOMELAB in environment[NINJASRE_DEPLOYMENT_PROFILE_ENV]


def test_every_service_carries_the_memory_and_cpu_limit_the_footprint_declares(
    homelab_compose: dict[str, Any],
) -> None:
    """FR-002. A declared footprint nothing enforces is an aspiration."""
    for name, service in homelab_compose["services"].items():
        limits = service["deploy"]["resources"]["limits"]

        assert limits["memory"] == f"{HOMELAB_MEMORY_LIMITS_MIB[name]}M", name
        assert str(limits["cpus"]) == f"{HOMELAB_CPU_LIMITS[name]}", name


def test_the_per_service_limits_sum_to_the_declared_footprint() -> None:
    """The number an operator is told, and the numbers the runtime enforces."""
    assert sum(HOMELAB_MEMORY_LIMITS_MIB.values()) == HOMELAB_TOTAL_MEMORY_MIB
    assert sum(HOMELAB_CPU_LIMITS.values()) == pytest.approx(HOMELAB_TOTAL_CPUS)


def test_a_local_model_endpoint_is_first_class_rather_than_an_afterthought(
    homelab_compose: dict[str, Any],
) -> None:
    """FR-004: the homelab case is a model on the operator's own hardware."""
    environment = homelab_compose["services"]["app"]["environment"]

    assert OLLAMA_BASE_URL_ENV in environment
    assert VLLM_BASE_URL_ENV in environment


def test_the_console_service_gets_every_setting_the_app_service_needs_to_boot(
    homelab_compose: dict[str, Any],
) -> None:
    """The same regression ``test_compose_profiles.py`` pins for the standard
    profile, in the file where it recurs. The console container runs the same
    entry point ``app`` does, at a different port — not a thin front end — so
    whatever ``app`` needs to pass startup validation, console needs too. This
    profile has its own defaults (``ollama`` rather than ``anthropic``, no
    local-account settings), so it is checked against its own ``app`` block
    rather than against the standard profile's.
    """
    app_settings = set(homelab_compose["services"]["app"]["environment"])
    console_settings = set(homelab_compose["services"]["console"]["environment"])

    missing = app_settings - console_settings
    assert not missing, f"console never receives: {missing}"


def test_nothing_is_published_beyond_loopback(homelab_compose: dict[str, Any]) -> None:
    """NFR-003: the profile works with no inbound connectivity from the internet."""
    for name, service in homelab_compose["services"].items():
        for published in service.get("ports", []):
            assert str(published).startswith("127.0.0.1:"), (
                f"{name} publishes {published} on every interface"
            )


def test_the_database_has_no_route_off_the_host(homelab_compose: dict[str, Any]) -> None:
    assert homelab_compose["networks"]["internal"]["internal"] is True
    assert homelab_compose["services"]["postgres"]["networks"] == ["internal"]


def test_one_database_serves_every_service_that_reaches_one(
    homelab_compose: dict[str, Any],
) -> None:
    urls = {
        name: service["environment"][NINJASRE_DATABASE_URL_ENV]
        for name, service in homelab_compose["services"].items()
        if NINJASRE_DATABASE_URL_ENV in service.get("environment", {})
    }

    assert len(set(urls.values())) == 1, f"they disagree: {urls}"


def test_the_state_that_matters_survives_a_recreate(homelab_compose: dict[str, Any]) -> None:
    """FR-006 and FR-007 both rest on this: the database is not in a container layer."""
    assert "postgres-data" in homelab_compose["volumes"]
    assert any(
        "postgres-data" in mount
        for mount in homelab_compose["services"]["postgres"].get("volumes", [])
    )


def test_every_service_comes_back_after_a_host_restart(homelab_compose: dict[str, Any]) -> None:
    """FR-007. ``unless-stopped`` is what makes the boot case work unattended."""
    for name, service in homelab_compose["services"].items():
        assert service["restart"] == "unless-stopped", name
