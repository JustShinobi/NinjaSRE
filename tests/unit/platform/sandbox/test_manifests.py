"""The artefacts the two heavy profiles hand to a runtime they cannot test here.

The contract suite proves the three profiles behave identically against
simulated runtimes. What it cannot prove is that the argument vectors and
manifests those profiles produce are the right ones — a simulated Docker will
happily accept a ``create`` line missing ``--read-only``.

So this file asserts on the artefacts themselves, field by field, for the fields
whose absence would silently remove a control. Each assertion below corresponds
to something that has to be true of a real cluster or daemon for the isolation to
hold, and a change that drops one fails here rather than in production.
"""

from __future__ import annotations

import json

import pytest

from config.constants.security import (
    SANDBOX_CONTAINER_NAME,
    SANDBOX_EGRESS_SIDECAR_NAME,
    SANDBOX_ENVOY_ADMIN_PORT,
    SANDBOX_ENVOY_LISTENER_PORT,
    SANDBOX_EXPIRES_AT_ANNOTATION,
    SANDBOX_INVESTIGATION_LABEL,
)
from platform.sandbox import ContentBundle, EgressPolicy, ResourceLimits, SandboxSpec
from platform.sandbox.profiles.container.image import container_spec
from platform.sandbox.profiles.container.network import network_for
from platform.sandbox.profiles.kubernetes import envoy, pod_spec, ttl

pytestmark = pytest.mark.unit

PROXY = "https://proxy.internal:8443"


def _spec(**overrides: object) -> SandboxSpec:
    """Return a spec with one allow-listed vendor and a small skill bundle."""
    defaults: dict[str, object] = {
        "org_id": "acme",
        "team_id": "platform",
        "investigation_id": "inv-1",
        "egress": EgressPolicy(proxy_url=PROXY, hosts=("api.datadoghq.com",)),
        "content": ContentBundle.from_mapping({"skills/triage.md": "# triage"}),
        "limits": ResourceLimits(memory_bytes=256 * 1024 * 1024, scratch_bytes=64 * 1024 * 1024),
        "image": "ninjasre/sandbox:1.0",
    }
    defaults.update(overrides)
    return SandboxSpec(**defaults)  # type: ignore[arg-type]


# --- container -------------------------------------------------------------


def test_the_container_bridge_has_no_route_off_it() -> None:
    network = network_for("sbx-1", _spec().egress)
    assert network.internal
    assert "--internal" in network.create_arguments()
    assert network.permits("proxy.internal")
    assert not network.permits("attacker.example")


def test_the_container_is_created_read_only_with_a_sized_tmpfs_and_no_capabilities() -> None:
    spec = _spec()
    arguments = container_spec(
        "sbx-1",
        spec,
        network="ninjasre-sbx-1",
        scratch_source="/host/scratch",
        content_source="/host/content",
        environment={"HTTPS_PROXY": PROXY},
    ).create_arguments()

    assert "--read-only" in arguments
    assert "--cap-drop" in arguments and "ALL" in arguments
    assert "no-new-privileges" in arguments
    assert "--pids-limit" in arguments
    assert str(spec.limits.max_processes) in arguments
    assert str(spec.limits.memory_bytes) in arguments

    tmpfs = arguments[arguments.index("--tmpfs") + 1]
    assert tmpfs.startswith(spec.scratch_path)
    assert f"size={spec.limits.scratch_bytes}" in tmpfs

    # The content mount is read-only and the scratch mount is not, which is the
    # whole of the read-only root and the immutable content mount, at the
    # runtime's own level.
    mounts = [arguments[index + 1] for index, value in enumerate(arguments) if value == "--mount"]
    content = next(mount for mount in mounts if spec.content_path in mount)
    scratch = next(mount for mount in mounts if f"target={spec.scratch_path}" in mount)
    assert content.endswith(",readonly")
    assert not scratch.endswith(",readonly")

    # Nothing else is mounted. A sandbox with the runtime's own socket in it is
    # not a sandbox.
    assert len(mounts) == 2
    assert not any("docker.sock" in mount for mount in mounts)


def test_the_container_carries_the_labels_the_reaper_reads() -> None:
    arguments = container_spec(
        "sbx-1",
        _spec(),
        network="net",
        scratch_source="/s",
        content_source="/c",
        environment={},
    ).create_arguments()
    labels = [arguments[index + 1] for index, value in enumerate(arguments) if value == "--label"]
    assert "ninjasre.io/investigation=inv-1" in labels
    assert "ninjasre.io/org=acme" in labels


# --- kubernetes ------------------------------------------------------------


def test_the_pod_drops_every_privilege_it_can_and_mounts_its_token_nowhere() -> None:
    manifest = pod_spec.sandbox_pod(
        "sbx-1",
        _spec(),
        namespace="ninjasre",
        envoy_config_map="ninjasre-egress-sbx-1",
        expires_at=ttl.render(ttl.expiry_of(900)),
    )
    spec = manifest["spec"]

    assert spec["automountServiceAccountToken"] is False
    assert spec["securityContext"]["runAsNonRoot"] is True
    assert spec["securityContext"]["runAsUser"] == pod_spec.SANDBOX_RUN_AS_USER
    assert spec["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    assert spec["restartPolicy"] == "Never"

    sandbox = next(c for c in spec["containers"] if c["name"] == SANDBOX_CONTAINER_NAME)
    assert sandbox["securityContext"]["readOnlyRootFilesystem"] is True
    assert sandbox["securityContext"]["allowPrivilegeEscalation"] is False
    assert sandbox["securityContext"]["capabilities"]["drop"] == ["ALL"]


def test_the_pods_scratch_is_in_memory_and_sized_and_its_content_is_read_only() -> None:
    spec = _spec()
    manifest = pod_spec.sandbox_pod(
        "sbx-1",
        spec,
        namespace="ninjasre",
        envoy_config_map="cm",
        expires_at="2026-01-01T00:00:00+00:00",
    )
    volumes = {volume["name"]: volume for volume in manifest["spec"]["volumes"]}

    assert volumes["scratch"]["emptyDir"]["medium"] == "Memory"
    assert volumes["scratch"]["emptyDir"]["sizeLimit"] == str(spec.limits.scratch_bytes)
    assert volumes["content"]["configMap"]["defaultMode"] == 0o444

    sandbox = next(c for c in manifest["spec"]["containers"] if c["name"] == SANDBOX_CONTAINER_NAME)
    mounts = {mount["name"]: mount for mount in sandbox["volumeMounts"]}
    assert mounts["content"]["readOnly"] is True
    assert "readOnly" not in mounts["scratch"]


def test_the_pod_carries_its_expiry_where_any_replica_can_read_it() -> None:
    expires = ttl.expiry_of(900)
    manifest = pod_spec.sandbox_pod(
        "sbx-1",
        _spec(),
        namespace="ninjasre",
        envoy_config_map="cm",
        expires_at=ttl.render(expires),
    )
    metadata = manifest["metadata"]
    assert metadata["annotations"][SANDBOX_EXPIRES_AT_ANNOTATION] == ttl.render(expires)
    assert ttl.expires_at_of(metadata) == expires
    assert not ttl.is_expired(metadata)


def test_a_pod_with_an_unreadable_expiry_is_treated_as_expired() -> None:
    """The safe reading of "I cannot tell when this expires" is "now"."""
    assert ttl.is_expired({"annotations": {SANDBOX_EXPIRES_AT_ANNOTATION: "yesterday"}})
    assert ttl.is_expired({})
    assert ttl.parse("yesterday") is None


def test_the_ttl_is_refreshed_before_it_lapses_and_not_on_every_turn() -> None:
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 8, 6, tzinfo=UTC)
    assert not ttl.due_for_refresh(now + timedelta(seconds=900), now=now)
    assert ttl.due_for_refresh(now + timedelta(seconds=10), now=now)


def test_the_content_config_map_round_trips_the_bundle_it_delivers() -> None:
    bundle = ContentBundle.from_mapping({"skills/triage.md": "# triage", "tools/a.py": "x = 1"})
    manifest = pod_spec.content_config_map("sbx-1", _spec(content=bundle), namespace="ninjasre")

    # Keys may not contain a slash, so nesting is flattened and the volume's
    # ``items`` mapping puts it back.
    assert set(manifest["binaryData"]) == {"skills__triage.md", "tools__a.py"}
    assert pod_spec.bundle_from_config_map(manifest).digest == bundle.digest


def test_the_network_policy_denies_ingress_and_all_egress_but_dns_and_the_proxy() -> None:
    """Without this the sidecar is a suggestion rather than a control."""
    spec = _spec()
    policy = pod_spec.network_policy(
        "sbx-1",
        spec,
        namespace="ninjasre",
        proxy_selector={"app.kubernetes.io/name": "ninjasre-credential-proxy"},
    )
    body = policy["spec"]

    assert body["policyTypes"] == ["Ingress", "Egress"]
    assert body["ingress"] == []
    assert body["podSelector"]["matchLabels"][SANDBOX_INVESTIGATION_LABEL] == "inv-1"

    ports = [port for rule in body["egress"] for port in rule["ports"]]
    assert {"protocol": "TCP", "port": spec.egress.proxy_port} in ports
    assert {"protocol": "UDP", "port": 53} in ports
    assert {"protocol": "TCP", "port": SANDBOX_ENVOY_LISTENER_PORT} in ports
    # No rule permits arbitrary egress: every rule names a destination.
    assert all(rule.get("to") for rule in body["egress"])


def test_the_sidecar_permits_only_declared_hosts_and_the_proxy() -> None:
    policy = EgressPolicy(proxy_url=PROXY, hosts=("api.datadoghq.com", "api.pagerduty.com"))
    bootstrap = envoy.bootstrap(policy, sandbox_id="sbx-1")

    assert envoy.permitted_hosts(bootstrap) == (
        "proxy.internal",
        "api.datadoghq.com",
        "api.pagerduty.com",
    )
    clusters = {cluster["name"] for cluster in bootstrap["static_resources"]["clusters"]}
    assert clusters == {envoy.cluster_name(host) for host in policy.reachable()}


def test_the_proxys_own_cluster_uses_the_port_the_policy_names() -> None:
    policy = EgressPolicy(proxy_url=PROXY, hosts=("api.datadoghq.com",))
    bootstrap = envoy.bootstrap(policy, sandbox_id="sbx-1")
    proxy_cluster = next(
        cluster
        for cluster in bootstrap["static_resources"]["clusters"]
        if cluster["name"] == envoy.cluster_name("proxy.internal")
    )
    endpoint = proxy_cluster["load_assignment"]["endpoints"][0]["lb_endpoints"][0]
    assert endpoint["endpoint"]["address"]["socket_address"]["port_value"] == 8443


def test_the_sidecar_logs_every_refusal_with_the_host_it_refused() -> None:
    """The sidecar is the only component that sees a refused attempt at all."""
    bootstrap = envoy.bootstrap(EgressPolicy(proxy_url=PROXY), sandbox_id="sbx-1")
    manager = bootstrap["static_resources"]["listeners"][0]["filter_chains"][0]["filters"][0][
        "typed_config"
    ]
    log_format = manager["access_log"][0]["typed_config"]["log_format"]["json_format"]
    assert log_format["sandbox"] == "sbx-1"
    assert log_format["host"] == "%REQ(:AUTHORITY)%"
    assert log_format["route"] == "%ROUTE_NAME%"


def test_the_sidecars_admin_interface_is_not_reachable_from_the_sandbox() -> None:
    bootstrap = envoy.bootstrap(EgressPolicy(proxy_url=PROXY), sandbox_id="sbx-1")
    admin = bootstrap["admin"]["address"]["socket_address"]
    assert admin["address"] == "127.0.0.1"
    assert admin["port_value"] == SANDBOX_ENVOY_ADMIN_PORT


def test_the_envoy_config_map_holds_parsable_configuration() -> None:
    manifest = envoy.config_map(
        EgressPolicy(proxy_url=PROXY, hosts=("api.datadoghq.com",)),
        sandbox_id="sbx-1",
        namespace="ninjasre",
    )
    parsed = json.loads(manifest["data"]["envoy.yaml"])
    assert envoy.permitted_hosts(parsed) == ("proxy.internal", "api.datadoghq.com")


def test_the_sidecar_is_in_the_pod_and_listens_where_the_policy_permits() -> None:
    manifest = pod_spec.sandbox_pod(
        "sbx-1",
        _spec(),
        namespace="ninjasre",
        envoy_config_map="cm",
        expires_at="2026-01-01T00:00:00+00:00",
    )
    sidecar = next(
        c for c in manifest["spec"]["containers"] if c["name"] == SANDBOX_EGRESS_SIDECAR_NAME
    )
    ports = {port["containerPort"] for port in sidecar["ports"]}
    assert ports == {SANDBOX_ENVOY_LISTENER_PORT, SANDBOX_ENVOY_ADMIN_PORT}
    assert sidecar["securityContext"]["readOnlyRootFilesystem"] is True
    assert next(m for m in sidecar["volumeMounts"] if m["name"] == "envoy-config")["readOnly"]
