"""A host nobody declared is refused, in every profile.

The assertion is deliberately made against each profile's *enforcement artefact*
rather than against a connection that happened to fail. A test that opened a
socket to an undeclared host and asserted it did not connect would pass on a
machine with no network at all, which is the machine CI runs on — it would prove
nothing and would keep proving nothing after somebody deleted the allow-list.

So each row reads back what the profile will actually enforce: the ``process``
profile's egress plan, the ``container`` profile's bridge, and the ``kubernetes``
profile's generated Envoy configuration plus its NetworkPolicy. Three
mechanisms, one question — is this host reachable — and the same answer in all
three.

The one thing every profile must permit is the credential proxy. A sandbox that
cannot reach the proxy cannot make an authenticated call at all, and an
allow-list that got that wrong would look like working isolation right up until
the first vendor call.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from conftest import ALLOWED_HOST, PROXY_URL, UNLISTED_HOST

from platform.credentials.proxy.injection import HeaderInjection, InjectionRule
from platform.sandbox import EgressPolicy, Sandbox, SandboxProfile, SandboxSpec
from platform.sandbox.profiles.kubernetes import envoy

pytestmark = [pytest.mark.contract, pytest.mark.security]


async def test_an_unlisted_host_is_not_reachable_in_any_profile(
    sandbox: Sandbox, spec: SandboxSpec
) -> None:
    instance = await sandbox.provision(spec)
    try:
        reachable = _reachable_hosts(sandbox, instance)
    finally:
        await sandbox.release(instance)

    assert UNLISTED_HOST not in reachable
    assert ALLOWED_HOST in reachable


async def test_the_credential_proxy_is_reachable_in_any_profile(
    sandbox: Sandbox, spec: SandboxSpec
) -> None:
    """Without the proxy there is no authenticated call to be made."""
    instance = await sandbox.provision(spec)
    try:
        assert spec.egress.proxy_host in _reachable_hosts(sandbox, instance)
    finally:
        await sandbox.release(instance)


async def test_the_sandbox_environment_routes_every_scheme_through_the_proxy(
    sandbox: Sandbox, spec: SandboxSpec
) -> None:
    """Whatever the mechanism, the sandbox is also *told* where the proxy is."""
    import probes

    instance = await sandbox.provision(spec)
    try:
        result = await sandbox.execute(
            instance,
            _read_environment(probes),
        )
    finally:
        await sandbox.release(instance)

    values = dict(line.split("=", 1) for line in result.stdout.decode().splitlines() if "=" in line)
    assert values.get("HTTP_PROXY")
    assert values.get("HTTPS_PROXY")
    assert UNLISTED_HOST not in values.get("NO_PROXY", "")


def _read_environment(probes: object):  # type: ignore[no-untyped-def]
    """Return the request that prints the sandbox's proxy variables."""
    from platform.sandbox import ExecutionRequest

    source = (
        "import os, sys\n"
        "for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY'):\n"
        "    sys.stdout.write(f'{name}={os.environ.get(name, \"\")}\\n')\n"
    )
    return ExecutionRequest(command=probes.python(source))  # type: ignore[attr-defined]


def _reachable_hosts(sandbox: Sandbox, instance: object) -> tuple[str, ...]:
    """Return what one profile will actually let this sandbox address.

    Each profile answers from its own artefact, which is the point: the question
    is whether three different mechanisms agree, and asking them all the same
    way would only prove that one shared function agrees with itself.
    """
    if sandbox.profile is SandboxProfile.PROCESS:
        return sandbox.egress_plan(instance).allowed_hosts  # type: ignore[attr-defined]
    if sandbox.profile is SandboxProfile.CONTAINER:
        network = sandbox.network_of(instance)  # type: ignore[attr-defined]
        assert network.internal, "a bridge with a default route is not an allow-list"
        return (network.proxy_host, *network.allowed_hosts)
    return envoy.permitted_hosts(sandbox.egress_config(instance))  # type: ignore[attr-defined]


async def test_the_kubernetes_sidecar_blackholes_everything_it_did_not_name(
    make_spec: Callable[..., SandboxSpec], profile: SandboxProfile, sandbox: Sandbox
) -> None:
    """The sidecar's default route is a refusal, not a pass-through."""
    if profile is not SandboxProfile.KUBERNETES:
        pytest.skip("the Envoy sidecar exists only in the kubernetes profile")

    instance = await sandbox.provision(make_spec())
    try:
        config = sandbox.egress_config(instance)  # type: ignore[attr-defined]
    finally:
        await sandbox.release(instance)

    manager = config["static_resources"]["listeners"][0]["filter_chains"][0]["filters"][0][
        "typed_config"
    ]
    virtual_hosts = manager["route_config"]["virtual_hosts"]
    catch_all = virtual_hosts[-1]
    assert catch_all["name"] == envoy.BLACKHOLE_ROUTE_NAME
    assert catch_all["domains"] == ["*"]
    response = catch_all["routes"][0]["direct_response"]
    assert response["status"] == envoy.BLOCKED_EGRESS_STATUS
    assert "allow-list" in response["body"]["inline_string"]

    # The admin interface is on loopback. The two containers share a network
    # namespace, so an admin listener on 0.0.0.0 would be one the sandbox could
    # reach — and reconfigure.
    assert config["admin"]["address"]["socket_address"]["address"] == "127.0.0.1"


async def test_the_allow_list_is_the_integrations_own_declared_hosts() -> None:
    """One source of truth: the tuple the credential proxy enforces is the one enforced here."""
    rules = (
        InjectionRule(
            integration="datadog",
            hosts=("api.datadoghq.com", "api.datadoghq.eu"),
            injections=(HeaderInjection(header="DD-API-KEY", field="api_key"),),
        ),
        InjectionRule(
            integration="pagerduty",
            hosts=("api.pagerduty.com",),
            injections=(HeaderInjection(header="Authorization", field="token"),),
        ),
    )
    policy = EgressPolicy.from_injection_rules(rules, proxy_url=PROXY_URL)

    assert policy.hosts == ("api.datadoghq.com", "api.datadoghq.eu", "api.pagerduty.com")
    assert policy.permits("api.pagerduty.com")
    assert not policy.permits(UNLISTED_HOST)
    # No wildcards, for the same reason the proxy has none: one acquisition away
    # from permitting a host the operator never approved.
    assert not policy.permits("evil.api.datadoghq.com")
