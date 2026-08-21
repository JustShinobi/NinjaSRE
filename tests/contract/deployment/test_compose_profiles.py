"""SC-002 and the properties of the two Compose profiles that are worth pinning.

The container count is the headline, and it is here rather than in a review
comment because a fifth service arrives one useful pull request at a time. Every
additional stateful service is a backup strategy, an upgrade path, and a failure
mode the operator inherits without having asked for one, so this test is the
place that conversation has to happen.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from config.constants.deployment import (
    DEPLOYMENT_PROFILE_DEV,
    DEPLOYMENT_PROFILE_STANDARD,
    DEV_PROFILE_CONTAINER_COUNT,
    DEV_PROFILE_SERVICES,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
    STANDARD_PROFILE_CONTAINER_COUNT,
    STANDARD_PROFILE_SERVICES,
)
from config.constants.llm import NINJASRE_LLM_PROVIDER_ENV
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from config.constants.security import NINJASRE_CREDENTIAL_PROXY_URL_ENV
from platform.startup.profiles import DeploymentProfile, topology_for

pytestmark = pytest.mark.contract


def test_the_standard_profile_is_four_containers(standard_compose: dict[str, Any]) -> None:
    """SC-002. The number is pinned in both places and this is where they meet."""
    services = standard_compose["services"]

    assert len(services) == STANDARD_PROFILE_CONTAINER_COUNT == 4
    assert set(services) == set(STANDARD_PROFILE_SERVICES)


def test_the_standard_profile_matches_the_topology_the_code_reports(
    standard_compose: dict[str, Any],
) -> None:
    """The compose file and ``topology_for`` are one fact in two places."""
    topology = topology_for(DeploymentProfile.STANDARD)

    assert set(standard_compose["services"]) == set(topology.services)
    assert len(standard_compose["services"]) == topology.container_count


def test_the_dev_profile_is_the_application_and_its_database(dev_compose: dict[str, Any]) -> None:
    """FR-002: the proxy runs in-process, so it is not a container here."""
    services = dev_compose["services"]

    assert len(services) == DEV_PROFILE_CONTAINER_COUNT == 2
    assert set(services) == set(DEV_PROFILE_SERVICES)
    assert "proxy" not in services
    assert "console" not in services


def test_each_compose_file_declares_its_own_profile(
    standard_compose: dict[str, Any],
    dev_compose: dict[str, Any],
) -> None:
    standard = standard_compose["services"]["app"]["environment"]
    dev = dev_compose["services"]["app"]["environment"]

    assert DEPLOYMENT_PROFILE_STANDARD in standard[NINJASRE_DEPLOYMENT_PROFILE_ENV]
    assert DEPLOYMENT_PROFILE_DEV in dev[NINJASRE_DEPLOYMENT_PROFILE_ENV]


def test_the_dev_profile_configures_no_credential_proxy_url(dev_compose: dict[str, Any]) -> None:
    """An in-process proxy has no address, and validation agrees it needs none."""
    assert NINJASRE_CREDENTIAL_PROXY_URL_ENV not in dev_compose["services"]["app"]["environment"]


def test_the_standard_profile_points_every_service_at_the_one_database(
    standard_compose: dict[str, Any],
) -> None:
    """Article XI: one Postgres per deployment, so one URL everywhere."""
    urls = {
        name: service["environment"][NINJASRE_DATABASE_URL_ENV]
        for name, service in standard_compose["services"].items()
        if NINJASRE_DATABASE_URL_ENV in service.get("environment", {})
    }

    assert len(urls) == 3, "app, console, and proxy all reach the same store"
    assert len(set(urls.values())) == 1, f"they disagree: {urls}"


def test_the_console_service_gets_every_setting_the_app_service_needs_to_boot(
    standard_compose: dict[str, Any],
) -> None:
    """The console container runs the same entry point ``app`` does, at a
    different port — not a thin front end — so whatever ``app`` needs to pass
    startup validation, console needs too. Static rather than a real boot:
    this is a property of the file's own declarations, and the two service
    blocks disagreeing is exactly what let the console container crash-loop
    on every real start while every static assertion about the file still
    held.
    """
    app_settings = set(standard_compose["services"]["app"]["environment"])
    console_settings = set(standard_compose["services"]["console"]["environment"])

    missing = app_settings - console_settings
    assert not missing, f"console never receives: {missing}"


def test_the_console_service_is_given_a_model_provider_setting(
    standard_compose: dict[str, Any],
) -> None:
    """The specific regression: a console container with no provider setting
    refuses to start with the same failure a deployment with none configured
    anywhere would, even though an operator who set one for ``app`` has no
    reason to expect it stops there.
    """
    assert NINJASRE_LLM_PROVIDER_ENV in standard_compose["services"]["console"]["environment"]


def test_nothing_is_published_beyond_loopback_by_default(
    standard_compose: dict[str, Any],
    dev_compose: dict[str, Any],
) -> None:
    """Binding to every interface is a decision, not a default that ships open."""
    for document in (standard_compose, dev_compose):
        for name, service in document["services"].items():
            for published in service.get("ports", []):
                assert str(published).startswith("127.0.0.1:"), (
                    f"{name} publishes {published} on every interface"
                )


def test_the_database_has_no_route_off_the_host(standard_compose: dict[str, Any]) -> None:
    """Article X, as a property of the network topology rather than a claim."""
    networks = standard_compose["networks"]
    postgres = standard_compose["services"]["postgres"]

    assert networks["internal"]["internal"] is True
    assert postgres["networks"] == ["internal"]


def test_only_the_two_services_that_need_egress_have_it(
    standard_compose: dict[str, Any],
) -> None:
    """The proxy reaches vendors and the app reaches the provider. Nothing else."""
    with_egress = {
        name
        for name, service in standard_compose["services"].items()
        if "egress" in service.get("networks", [])
    }

    assert with_egress == {"app", "proxy"}


def test_every_service_waits_for_the_database_to_be_healthy(
    standard_compose: dict[str, Any],
) -> None:
    """A server accepting connections before initdb has run is one that fails to migrate."""
    for name in ("app", "proxy"):
        depends = standard_compose["services"][name]["depends_on"]
        assert depends["postgres"]["condition"] == "service_healthy", name


def test_the_database_health_check_asks_about_the_database_not_the_port(
    standard_compose: dict[str, Any],
) -> None:
    check = standard_compose["services"]["postgres"]["healthcheck"]["test"]

    assert "pg_isready" in " ".join(check)
    assert "-d" in " ".join(check), "naming the database, so initdb has finished"


def test_the_state_that_matters_is_on_a_named_volume(
    standard_compose: dict[str, Any],
) -> None:
    """A deployment whose database lived in the container layer loses it on upgrade."""
    assert "postgres-data" in standard_compose["volumes"]
    assert any(
        "postgres-data" in mount
        for mount in standard_compose["services"]["postgres"].get("volumes", [])
    )


#: ``BASE_POSTGRES`` is never resolved by ``yaml.safe_load`` — it stays the raw
#: ``${VAR:-postgres:MAJOR.rest}`` expression — so the pinned major version is
#: read out of the default rather than out of an environment nothing sets here.
_PINNED_POSTGRES_IMAGE = re.compile(r"^\$\{BASE_POSTGRES:-postgres:(?P<major>\d+)\.[^}]*\}$")


def _pinned_postgres_major(compose: dict[str, Any]) -> int:
    """Return the PostgreSQL major version this compose file's postgres service pins."""
    expression = compose["services"]["postgres"]["build"]["args"]["BASE_POSTGRES"]
    match = _PINNED_POSTGRES_IMAGE.match(expression)
    assert match, f"{expression!r} does not pin a ${{BASE_POSTGRES:-postgres:<major>.<rest>}}"
    return int(match.group("major"))


def _postgres_volume_target(compose: dict[str, Any]) -> str:
    """Return the container-side path the postgres service's data volume mounts at."""
    mounts = [
        mount
        for mount in compose["services"]["postgres"].get("volumes", [])
        if "/var/lib/postgresql" in mount
    ]
    assert len(mounts) == 1, f"expected exactly one postgres data mount, found {mounts}"
    _name, target, *_mode = mounts[0].split(":")
    return target


def test_the_postgres_volume_mounts_where_the_pinned_major_version_expects(
    standard_compose: dict[str, Any],
    homelab_compose: dict[str, Any],
    dev_compose: dict[str, Any],
) -> None:
    """Postgres 18 made the data directory major-version-specific.

    A named volume mounted directly at the pre-18 path
    (``/var/lib/postgresql/data``) makes the 18+ image's own entrypoint treat a
    *fresh, empty* volume as leftover data from an unmanaged upgrade —
    ``docker_setup_env`` in the official image's entrypoint checks whether that
    path is a mountpoint at all, not whether anything lives under it — and
    ``docker_error_old_databases`` exits 1 before the server ever starts, on
    every start, from a volume that has never held a byte. The image's own
    error message recommends the fix this test pins: a single mount at
    ``/var/lib/postgresql``, letting the entrypoint lay out the
    major-versioned subdirectory itself.

    Static on purpose: this needs no container runtime and runs on every
    machine, so a future major-version bump that reintroduces the same mount
    is caught here rather than by a stack that silently never becomes
    healthy. ``test_compose_up.py`` is the sibling that actually starts the
    container and reads its health.
    """
    for profile, compose in (
        ("standard", standard_compose),
        ("homelab", homelab_compose),
        ("dev", dev_compose),
    ):
        major = _pinned_postgres_major(compose)
        target = _postgres_volume_target(compose)
        if major >= 18:
            assert target == "/var/lib/postgresql", (
                f"{profile} profile: postgres {major} needs a single mount at "
                f"/var/lib/postgresql, not {target!r}"
            )
