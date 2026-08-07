"""The enterprise chart's structure, checked without a cluster.

A rendered manifest needs Helm; the *declarations* do not, and the declarations
are where the properties that matter live. Whether sandbox pods have an egress
policy, whether the proxy has an off switch, whether a secret can be written as
a value — each is a fact about the chart's source, and each is one a review can
miss on the pull request that introduces it.

The install test that needs a Kind cluster lives in CI and skips cleanly here,
which is the pattern the chaos and end-to-end suites already established.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from config.constants.deployment import ENTERPRISE_GLOBAL_CONCURRENCY
from config.constants.security import (
    SANDBOX_ENVOY_ADMIN_PORT,
    SANDBOX_ENVOY_LISTENER_PORT,
    SANDBOX_PROFILE_KUBERNETES,
    SANDBOX_WARM_POOL_SIZE,
)
from platform.startup.profiles import DeploymentProfile, topology_for
from tests.contract.deployment.conftest import CHART, template_text

pytestmark = pytest.mark.contract


def test_the_chart_declares_what_helm_needs(chart_metadata: dict[str, Any]) -> None:
    assert chart_metadata["apiVersion"] == "v2"
    assert chart_metadata["name"] == "ninjasre"
    assert chart_metadata["version"]
    assert chart_metadata["appVersion"]
    assert chart_metadata["kubeVersion"]


def test_every_workload_the_enterprise_profile_needs_has_a_template() -> None:
    names = {path.name for path in (CHART / "templates").iterdir()}

    assert {
        "_helpers.tpl",
        "app-deployment.yaml",
        "console-deployment.yaml",
        "proxy-deployment.yaml",
        "migration-job.yaml",
        "postgres.yaml",
        "sandbox.yaml",
        "serviceaccount.yaml",
        "NOTES.txt",
    } <= names


def test_the_application_replica_count_is_configurable(chart_values: dict[str, Any]) -> None:
    """FR-004: agent replicas are the enterprise profile's one scaling dial."""
    assert chart_values["app"]["replicas"] >= 1
    assert "{{ .Values.app.replicas }}" in template_text("app-deployment.yaml")


def test_the_credential_proxy_has_no_off_switch(chart_values: dict[str, Any]) -> None:
    """Turning it off would mean putting credentials in the agent's own process."""
    assert "enabled" not in chart_values["proxy"]
    assert "{{- if .Values.proxy.enabled }}" not in template_text("proxy-deployment.yaml")


def test_nothing_reaches_the_proxy_except_the_two_things_that_should() -> None:
    source = template_text("proxy-deployment.yaml")

    assert "kind: NetworkPolicy" in source
    assert "component: app" in source
    assert "component: console" in source


def test_no_secret_can_be_written_as_a_value(chart_values: dict[str, Any]) -> None:
    """A values file with an API key in it is a values file in a Git repository."""
    assert "key" not in chart_values["encryptionKey"]
    assert set(chart_values["encryptionKey"]["secret"]) == {"name", "key"}
    assert "apiKey" not in chart_values["provider"]
    assert set(chart_values["provider"]["credentialSecret"]) == {"name", "key"}
    assert "clientSecret" not in chart_values["sso"]


def test_the_encryption_key_is_never_generated_by_the_chart() -> None:
    """FR-019, in the one place a chart is most tempted to be helpful."""
    for path in (CHART / "templates").glob("*.yaml"):
        source = path.read_text(encoding="utf-8")
        assert "randAlphaNum" not in source, path.name
        assert "derivePassword" not in source, path.name
        assert "genPrivateKey" not in source, path.name


def test_migrations_run_to_completion_before_the_rollout() -> None:
    """FR-007, and a failed migration that reads as a failed job rather than a crash loop."""
    source = template_text("migration-job.yaml")

    assert "kind: Job" in source
    assert "helm.sh/hook: pre-install,pre-upgrade" in source
    assert "--migrate-only" in source
    assert "restartPolicy: Never" in source


def test_the_sandbox_has_both_halves_of_its_egress_control(
    chart_values: dict[str, Any],
) -> None:
    """FR-004: Envoy for the allow-list, a NetworkPolicy so nothing goes round it."""
    source = template_text("sandbox.yaml")

    assert chart_values["sandbox"]["egress"]["enabled"] is True
    assert chart_values["sandbox"]["egress"]["networkPolicy"] is True
    assert "envoy.yaml" in source
    assert "kind: NetworkPolicy" in source
    assert "policyTypes:\n    - Egress" in source


def test_the_envoy_admin_interface_is_not_reachable_from_the_sandbox() -> None:
    """An admin port the sandboxed process could reach is an allow-list it can rewrite."""
    envoy = template_text("sandbox.yaml")
    admin = envoy.index("admin:")
    listener = envoy.index("name: egress")

    assert "address: 127.0.0.1" in envoy[admin:listener]
    assert "address: 0.0.0.0" in envoy[listener:]


def test_the_sandbox_ports_are_the_ones_the_platform_uses(
    chart_values: dict[str, Any],
) -> None:
    egress = chart_values["sandbox"]["egress"]

    assert egress["listenerPort"] == SANDBOX_ENVOY_LISTENER_PORT
    assert egress["adminPort"] == SANDBOX_ENVOY_ADMIN_PORT
    assert chart_values["sandbox"]["warmPoolSize"] == SANDBOX_WARM_POOL_SIZE


def test_the_chart_is_the_enterprise_profile_and_cannot_say_otherwise() -> None:
    """A values file that could change the profile could change the sandbox with it."""
    helpers = template_text("_helpers.tpl")

    assert "NINJASRE_DEPLOYMENT_PROFILE\n  value: enterprise" in helpers
    assert topology_for(DeploymentProfile.ENTERPRISE).global_concurrency == (
        ENTERPRISE_GLOBAL_CONCURRENCY
    )


def test_the_sandbox_profile_matches_the_deployment_profile(
    chart_values: dict[str, Any],
) -> None:
    """A disagreement here would be refused at startup, so the chart must not ship one."""
    assert chart_values["sandbox"]["profile"] == SANDBOX_PROFILE_KUBERNETES


def test_an_external_database_is_the_default(chart_values: dict[str, Any]) -> None:
    """A StatefulSet in this release is a second database with none of the estate's policies."""
    assert chart_values["postgres"]["external"] is True
    assert chart_values["postgres"]["inCluster"]["enabled"] is False


def test_the_in_cluster_database_refuses_to_guess_its_image() -> None:
    """Nothing published carries both extensions, so a default here would fail on first write."""
    assert 'required "postgres.inCluster.image' in template_text("postgres.yaml")


def test_telemetry_leaves_nothing_by_default(chart_values: dict[str, Any]) -> None:
    """Article X: an export somebody did not configure is one that should not happen."""
    assert chart_values["otel"]["enabled"] is False
    assert chart_values["otel"]["endpoint"] == ""


def test_every_workload_runs_as_a_non_root_user_with_a_read_only_root(
    chart_values: dict[str, Any],
) -> None:
    assert chart_values["podSecurityContext"]["runAsNonRoot"] is True
    assert chart_values["podSecurityContext"]["runAsUser"] == 10001
    assert chart_values["containerSecurityContext"]["readOnlyRootFilesystem"] is True
    assert chart_values["containerSecurityContext"]["allowPrivilegeEscalation"] is False
    assert chart_values["containerSecurityContext"]["capabilities"]["drop"] == ["ALL"]

    for name in ("app-deployment.yaml", "console-deployment.yaml", "proxy-deployment.yaml"):
        source = template_text(name)
        assert "podSecurityContext" in source, name
        assert "containerSecurityContext" in source, name


def test_every_workload_declares_resource_limits(chart_values: dict[str, Any]) -> None:
    """An unset limit is not "unlimited by choice", it is an eviction at the worst moment."""
    for component in ("app", "console", "proxy", "migrations"):
        resources = chart_values[component]["resources"]
        assert resources["requests"]["cpu"], component
        assert resources["limits"]["memory"], component


def test_readiness_and_liveness_are_different_endpoints() -> None:
    """One endpoint for both would restart a pod whose database was still coming up."""
    source = template_text("app-deployment.yaml")

    assert "path: /health/ready" in source
    assert "path: /health/live" in source


def test_the_values_file_is_valid_yaml_and_the_templates_are_at_least_readable() -> None:
    yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    for path in (CHART / "templates").glob("*.yaml"):
        source = path.read_text(encoding="utf-8")
        assert source.count("{{") == source.count("}}"), f"{path.name} has unbalanced braces"
