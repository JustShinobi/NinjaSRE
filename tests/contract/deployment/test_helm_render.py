"""The enterprise chart, rendered for real — not just parsed.

``test_helm_chart.py`` proves the chart's own declarations are internally
consistent, including that its provider-to-credential-name mapping agrees
with the constant the deployment's startup validation reads; it has never
asked Helm to actually expand a template. A ``{{ include }}`` can be spelled
correctly and still not produce the token the source implies — the
whitespace trimming that keeps ``ninjasre.providerCredentialEnvName``'s
output to one clean line is exactly the kind of thing a raw-text assertion
cannot see, and a rendered container's real environment is the only place a
name-and-secret-key pair can be checked as Kubernetes would actually receive
them.

Skips cleanly with a named reason where there is no ``helm`` binary, the
same rule ``test_compose_up.py`` runs under for ``docker``; a machine that
has one turns the skip into a run. ``make verify`` stays runnable with no
``helm`` binary at all — this module is the only place in the deployment
contract suite that needs one.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

import pytest
import yaml

from platform.startup.validation import PROVIDER_CREDENTIAL_ENV
from tests.contract.deployment.conftest import CHART, REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.e2e]

needs_helm = pytest.mark.skipif(
    shutil.which("helm") is None,
    reason=(
        "this test renders the chart with `helm template`; there is no helm binary on this machine"
    ),
)

_RELEASE = "ninjasre-contract"

#: The Secret the credential tests name. The chart references a Secret only
#: when it is given a name — an operator who has not connected a provider yet
#: must get a release that installs — so a test about the credential being
#: rendered has to supply one, and a test about it *not* being rendered has to
#: supply one too, or it passes on the absent name rather than on the rule it
#: is checking.
_CREDENTIAL_SECRET = "ninjasre-contract-provider"

#: Every credential-variable name the chart can possibly emit, across every
#: supported provider. Used to prove a workload receives *none* of them,
#: which a check for one specific absent name would not.
_EVERY_CREDENTIAL_NAME = {names[0] for names in PROVIDER_CREDENTIAL_ENV.values()}


def _helm_template(*args: str) -> str:
    """Render the committed chart and return its stdout.

    Never through a shell pipe, and the exit code is read from the
    ``CompletedProcess`` itself rather than trusted implicitly — this wave
    has already been bitten by a status read off the wrong end of a
    pipeline.
    """
    result = subprocess.run(  # noqa: S603 — fixed argv, no shell, no interpolation
        ["helm", "template", _RELEASE, str(CHART), "--kube-version", "1.28.0", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"`helm template` exited {result.returncode}; stderr:\n{result.stderr}"
    )
    return result.stdout


def _container_env(rendered: str, *, component: str, container: str) -> dict[str, dict[str, Any]]:
    """Return ``{name: entry}`` for one Deployment's named container, out of a rendered manifest."""
    for document in yaml.safe_load_all(rendered):
        if not document or document.get("kind") != "Deployment":
            continue
        if document["metadata"]["labels"].get("app.kubernetes.io/component") != component:
            continue
        containers = document["spec"]["template"]["spec"]["containers"]
        (found,) = [c for c in containers if c["name"] == container]
        return {entry["name"]: entry for entry in found.get("env", [])}
    raise AssertionError(f"no Deployment with component={component!r} in the rendered manifest")


@needs_helm
@pytest.mark.parametrize("provider_id", sorted(PROVIDER_CREDENTIAL_ENV))
def test_the_rendered_application_gets_the_credential_its_own_provider_reads(
    provider_id: str,
) -> None:
    """For every provider the deployment can authenticate to, render the
    chart with it selected and read the application container's real,
    expanded environment back — rather than trusting that ``include``
    expands the way the unrendered source reads.
    """
    expected_name = PROVIDER_CREDENTIAL_ENV[provider_id][0]
    rendered = _helm_template(
        "--set",
        f"provider.id={provider_id}",
        "--set",
        f"provider.credentialSecret.name={_CREDENTIAL_SECRET}",
    )
    env = _container_env(rendered, component="app", container="app")

    assert expected_name in env, f"{provider_id}: rendered app env is {sorted(env)}"
    assert "secretKeyRef" in env[expected_name].get("valueFrom", {}), env[expected_name]
    assert "NINJASRE_PROVIDER_CREDENTIAL" not in env


@needs_helm
@pytest.mark.parametrize("provider_id", sorted(PROVIDER_CREDENTIAL_ENV))
def test_naming_a_provider_alone_references_no_secret(provider_id: str) -> None:
    """Choosing a provider must not oblige the operator to have created a Secret.

    Connecting a model provider is a first-run step: the operator picks one in
    the console and the key goes to the vault. A chart that mounted a
    ``secretKeyRef`` the moment a provider was named would refuse to install
    until somebody created a Secret for a decision the console owns — which is
    a release that will not start for a deployment that is configured
    correctly.

    The other half of the same rule the test above checks: name the Secret too
    and the credential appears.
    """
    rendered = _helm_template("--set", f"provider.id={provider_id}")
    env = _container_env(rendered, component="app", container="app")

    present = set(env) & _EVERY_CREDENTIAL_NAME
    assert not present, f"{provider_id}: named no Secret and still got {sorted(present)}"


@needs_helm
def test_ollama_renders_with_no_credential_secret_reference_at_all() -> None:
    """The one supported provider that needs no vendor key must not still
    demand an operator create a secret nothing reads.

    Rendered *with* a credential Secret named, which is the only way this
    means anything: a local model reads no vendor key, so naming a Secret must
    not be enough to hand it one. Without the name the chart renders no
    credential for any provider, and the test would pass without reaching the
    rule about ollama at all.
    """
    rendered = _helm_template(
        "--set",
        "provider.id=ollama",
        "--set",
        f"provider.credentialSecret.name={_CREDENTIAL_SECRET}",
    )
    env = _container_env(rendered, component="app", container="app")

    present = set(env) & _EVERY_CREDENTIAL_NAME
    assert not present, f"ollama's rendered app env still carries: {present}"
    assert "NINJASRE_PROVIDER_CREDENTIAL" not in env


@needs_helm
def test_the_rendered_proxy_gets_no_provider_credential_at_all() -> None:
    """The credential proxy brokers credentials for other processes and
    never calls a model itself, so its rendered environment must carry
    neither the dead catch-all name nor any real provider's credential name.
    """
    rendered = _helm_template()
    env = _container_env(rendered, component="proxy", container="proxy")

    present = set(env) & _EVERY_CREDENTIAL_NAME
    assert not present, f"the proxy's rendered env still carries: {present}"
    assert "NINJASRE_PROVIDER_CREDENTIAL" not in env
