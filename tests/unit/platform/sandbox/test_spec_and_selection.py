"""What a sandbox is asked for, and what the deployment says it will get.

The assertions here are mostly about refusals: a limit that cannot be widened, a
policy that cannot omit the proxy, a profile name that cannot be a typo. Those
are the cases where a permissive default would be invisible until it mattered.
"""

from __future__ import annotations

import pytest

from config.constants.security import (
    NINJASRE_SANDBOX_PROFILE_ENV,
    SANDBOX_CPU_SECONDS_LIMIT,
    SANDBOX_MEMORY_BYTES_LIMIT,
)
from platform.sandbox import (
    ContentBundle,
    EgressPolicy,
    LimitKind,
    ResourceLimits,
    SandboxProfile,
    SandboxSpec,
    UnknownSandboxProfile,
)
from platform.sandbox.selection import (
    GuaranteeStrength,
    guarantees_for,
    resolve_profile,
    startup_report,
)

pytestmark = pytest.mark.unit

PROXY = "http://127.0.0.1:8081"


def test_the_default_limits_are_the_constants_tier_and_not_a_literal() -> None:
    limits = ResourceLimits.defaults()
    assert limits.cpu_seconds == SANDBOX_CPU_SECONDS_LIMIT
    assert limits.memory_bytes == SANDBOX_MEMORY_BYTES_LIMIT


def test_every_bound_has_a_value_and_a_readable_unit() -> None:
    limits = ResourceLimits.defaults()
    for limit in LimitKind:
        assert limits.value_of(limit) > 0
        rendered = limit.render(limits.value_of(limit))
        assert rendered and limit.description


def test_narrowing_only_ever_tightens() -> None:
    """A capability does not get to raise the ceiling the operator agreed to."""
    ceiling = ResourceLimits(cpu_seconds=30, memory_bytes=100, max_processes=8)
    greedy = ResourceLimits(cpu_seconds=600, memory_bytes=10_000, max_processes=1_024)

    narrowed = ceiling.narrowed_to(greedy)
    assert narrowed.cpu_seconds == 30
    assert narrowed.memory_bytes == 100
    assert narrowed.max_processes == 8

    modest = ResourceLimits(cpu_seconds=5, memory_bytes=50, max_processes=2)
    assert ceiling.narrowed_to(modest).cpu_seconds == 5


@pytest.mark.parametrize("field", ["cpu_seconds", "memory_bytes", "max_processes"])
def test_a_non_positive_bound_is_refused_rather_than_read_as_unbounded(field: str) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        ResourceLimits(**{field: 0})


def test_an_egress_policy_without_a_proxy_is_refused() -> None:
    """A sandbox that cannot reach the proxy cannot authenticate at all."""
    with pytest.raises(ValueError, match="no proxy to route through"):
        EgressPolicy(proxy_url="not-a-url")


def test_the_proxy_is_always_reachable_and_an_unlisted_host_never_is() -> None:
    policy = EgressPolicy(proxy_url=PROXY, hosts=("API.DataDogHQ.com",))
    assert policy.permits("127.0.0.1")
    assert policy.permits("api.datadoghq.com")
    assert not policy.permits("attacker.example")
    assert policy.reachable()[0] == "127.0.0.1"
    assert policy.proxy_port == 8081
    assert policy.proxy_is_loopback


def test_a_remote_proxy_is_not_loopback_and_defaults_its_port_from_the_scheme() -> None:
    policy = EgressPolicy(proxy_url="https://proxy.internal")
    assert not policy.proxy_is_loopback
    assert policy.proxy_port == 443


def test_a_spec_needs_a_tenant_and_a_lifetime() -> None:
    egress = EgressPolicy(proxy_url=PROXY)
    with pytest.raises(ValueError, match="needs an org_id"):
        SandboxSpec(org_id="", team_id="t", investigation_id="i", egress=egress)
    with pytest.raises(ValueError, match="ttl_seconds must be positive"):
        SandboxSpec(org_id="o", team_id="t", investigation_id="i", egress=egress, ttl_seconds=0)


def test_a_specs_expiry_follows_its_ttl() -> None:
    from datetime import UTC, datetime

    spec = SandboxSpec(
        org_id="o",
        team_id="t",
        investigation_id="i",
        egress=EgressPolicy(proxy_url=PROXY),
        ttl_seconds=60,
    )
    now = datetime(2026, 8, 6, tzinfo=UTC)
    assert (spec.expires_at(now=now) - now).total_seconds() == 60


def test_with_limits_narrows_and_with_content_replaces() -> None:
    spec = SandboxSpec(
        org_id="o", team_id="t", investigation_id="i", egress=EgressPolicy(proxy_url=PROXY)
    )
    narrowed = spec.with_limits(ResourceLimits(cpu_seconds=1))
    assert narrowed.limits.cpu_seconds == 1

    bundle = ContentBundle.from_mapping({"a.md": "x"})
    assert spec.with_content(bundle).content.digest == bundle.digest


def test_the_profile_comes_from_deployment_configuration() -> None:
    assert resolve_profile({}) is SandboxProfile.PROCESS
    assert (
        resolve_profile({NINJASRE_SANDBOX_PROFILE_ENV: " Kubernetes "}) is SandboxProfile.KUBERNETES
    )


def test_a_misspelled_profile_fails_rather_than_falling_back() -> None:
    """A typo in production configuration must not quietly start the light profile."""
    with pytest.raises(UnknownSandboxProfile, match="kubernets"):
        resolve_profile({NINJASRE_SANDBOX_PROFILE_ENV: "kubernets"})


def test_windows_reports_the_cpu_limit_it_cannot_enforce() -> None:
    """The gap is named at start, not discovered from a document nobody has."""
    report = guarantees_for(SandboxProfile.PROCESS, system="win32")
    assert report.limits[LimitKind.CPU_SECONDS] is GuaranteeStrength.UNAVAILABLE
    assert LimitKind.CPU_SECONDS in report.weakened
    assert report.development_only
    assert "cpu_seconds unavailable" in report.summary()


@pytest.mark.parametrize("system", ["linux", "darwin", "win32"])
def test_the_process_profile_works_on_all_three_operating_systems(system: str) -> None:
    """It runs everywhere, and says what it does not enforce where."""
    report = guarantees_for(SandboxProfile.PROCESS, system=system)
    assert report.system == system
    assert report.development_only
    assert set(report.limits) == set(LimitKind)
    assert report.to_record()["weakened"]


def test_a_loopback_proxy_and_a_usable_namespace_reach_enforced_egress() -> None:
    weak = guarantees_for(SandboxProfile.PROCESS, system="linux")
    strong = guarantees_for(
        SandboxProfile.PROCESS, system="linux", network_namespace_available=True
    )
    assert weak.egress_strength is GuaranteeStrength.BEST_EFFORT
    assert strong.egress_strength is GuaranteeStrength.ENFORCED
    assert "network namespace" in strong.egress_mechanism


def test_the_heavier_profiles_declare_no_gaps() -> None:
    for profile in (SandboxProfile.CONTAINER, SandboxProfile.KUBERNETES):
        report = guarantees_for(profile, system="linux")
        assert report.weakened == ()
        assert not report.development_only
        assert report.summary().endswith("all resource limits enforced")


def test_the_startup_report_is_produced_and_serialisable() -> None:
    report = startup_report(SandboxProfile.KUBERNETES, system="linux")
    record = report.to_record()
    assert record["profile"] == "kubernetes"
    assert record["development_only"] is False
    assert record["isolation_strength"] == "enforced"
