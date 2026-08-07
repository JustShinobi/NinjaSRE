"""One setting decides three things, and the encryption key is never invented.

FR-005 and FR-019, which have nothing to do with each other except that both are
places where a convenient default would be a defect: a profile that silently
fell back to the development shape, and a key that appeared on its own.
"""

from __future__ import annotations

import base64

import pytest

from config.constants.deployment import (
    DEPLOYMENT_PROFILE_ENTERPRISE,
    DEPLOYMENT_PROFILE_STANDARD,
    NINJASRE_DEPLOYMENT_PROFILE_ENV,
    PROXY_DEPLOYMENT_IN_PROCESS,
    SCHEDULER_LEADER_CLAIMED,
    STANDARD_PROFILE_CONTAINER_COUNT,
)
from config.constants.persistence import NINJASRE_DATABASE_ENCRYPTION_KEY_ENV
from platform.sandbox.spec import SandboxProfile
from platform.startup.errors import (
    EncryptionKeyInvalid,
    EncryptionKeyMissing,
    UnknownDeploymentProfile,
)
from platform.startup.keys import (
    ENCRYPTION_KEY_BYTES,
    configured_key,
    decode_encryption_key,
    key_fingerprint,
    require_encryption_key,
)
from platform.startup.profiles import (
    DeploymentProfile,
    resolve_profile,
    resolve_topology,
    topology_for,
)

pytestmark = pytest.mark.unit

VALID_KEY = base64.b64encode(bytes(range(ENCRYPTION_KEY_BYTES))).decode("ascii")


# -- profiles -----------------------------------------------------------------


def test_an_unset_profile_is_the_development_one() -> None:
    assert resolve_profile({}) is DeploymentProfile.DEV


def test_a_profile_is_read_case_insensitively_and_with_whitespace_trimmed() -> None:
    environ = {NINJASRE_DEPLOYMENT_PROFILE_ENV: "  Standard "}

    assert resolve_profile(environ) is DeploymentProfile.STANDARD


def test_an_unknown_profile_is_refused_rather_than_defaulted() -> None:
    """A typo in production must not start the development shape quietly."""
    with pytest.raises(UnknownDeploymentProfile) as caught:
        resolve_profile({NINJASRE_DEPLOYMENT_PROFILE_ENV: "produciton"})

    assert "produciton" in str(caught.value)
    assert DEPLOYMENT_PROFILE_STANDARD in str(caught.value)


def test_the_dev_profile_runs_the_proxy_in_process_and_the_process_sandbox() -> None:
    """FR-002."""
    topology = topology_for(DeploymentProfile.DEV)

    assert topology.runs_proxy_in_process
    assert topology.proxy_deployment == PROXY_DEPLOYMENT_IN_PROCESS
    assert topology.sandbox_profile is SandboxProfile.PROCESS
    assert topology.container_count == 2


def test_the_standard_profile_is_four_containers() -> None:
    """SC-002. Every additional stateful service is one the operator inherits."""
    topology = topology_for(DeploymentProfile.STANDARD)

    assert topology.container_count == STANDARD_PROFILE_CONTAINER_COUNT == 4
    assert len(topology.services) == 4
    assert topology.sandbox_profile is SandboxProfile.CONTAINER
    assert not topology.runs_proxy_in_process


def test_the_enterprise_profile_has_no_fixed_container_count() -> None:
    """A Helm release's pod count is a function of its replicas, not a constant."""
    topology = topology_for(DeploymentProfile.ENTERPRISE)

    assert not topology.container_count_is_fixed
    assert topology.sandbox_profile is SandboxProfile.KUBERNETES
    assert topology.scheduler == SCHEDULER_LEADER_CLAIMED


def test_concurrency_rises_with_the_profile_and_is_never_unbounded() -> None:
    """Article II: the ceiling exists where it matters most, which is the largest one."""
    ceilings = [topology_for(profile).global_concurrency for profile in DeploymentProfile]

    assert ceilings == sorted(ceilings)
    assert all(ceiling > 0 for ceiling in ceilings)


def test_one_setting_decides_sandbox_proxy_and_concurrency_together() -> None:
    """FR-005: no way to be half one profile and half another."""
    topology = resolve_topology({NINJASRE_DEPLOYMENT_PROFILE_ENV: DEPLOYMENT_PROFILE_ENTERPRISE})

    assert topology.sandbox_profile is SandboxProfile.KUBERNETES
    assert not topology.runs_proxy_in_process
    assert (
        topology.global_concurrency == topology_for(DeploymentProfile.ENTERPRISE).global_concurrency
    )


def test_the_summary_names_the_two_things_operators_get_wrong() -> None:
    summary = topology_for(DeploymentProfile.STANDARD).summary()

    assert "credential proxy" in summary
    assert "sandbox" in summary


def test_every_profile_has_a_topology() -> None:
    for profile in DeploymentProfile:
        assert topology_for(profile).profile is profile


# -- keys ---------------------------------------------------------------------


def test_a_valid_key_decodes_to_thirty_two_bytes() -> None:
    assert len(decode_encryption_key(VALID_KEY)) == ENCRYPTION_KEY_BYTES == 32


def test_a_key_that_is_not_base64_says_so_rather_than_being_invalid() -> None:
    with pytest.raises(EncryptionKeyInvalid) as caught:
        decode_encryption_key("not base64!!")

    assert "base64" in str(caught.value)
    assert NINJASRE_DATABASE_ENCRYPTION_KEY_ENV in str(caught.value)


def test_a_short_key_is_refused_rather_than_stretched() -> None:
    with pytest.raises(EncryptionKeyInvalid) as caught:
        decode_encryption_key(base64.b64encode(b"short").decode("ascii"))

    assert "5 bytes" in str(caught.value)
    assert "32" in str(caught.value)


def test_no_key_configured_is_not_an_error_on_its_own() -> None:
    """A deployment that stores no credentials should not fail over a key it never uses."""
    assert configured_key({}) is None


def test_the_credential_path_refuses_rather_than_generating_a_key() -> None:
    """FR-019: a silently-generated key is discovered missing during a restore."""
    with pytest.raises(EncryptionKeyMissing) as caught:
        require_encryption_key({})

    message = str(caught.value)
    assert NINJASRE_DATABASE_ENCRYPTION_KEY_ENV in message
    assert "does not generate" in message
    assert "openssl rand" in message, "the message has to say how to make one"


def test_a_configured_key_is_returned_to_the_credential_path() -> None:
    key = require_encryption_key({NINJASRE_DATABASE_ENCRYPTION_KEY_ENV: VALID_KEY})

    assert len(key) == ENCRYPTION_KEY_BYTES


def test_a_fingerprint_identifies_a_key_without_revealing_it() -> None:
    key = decode_encryption_key(VALID_KEY)
    other = bytes(ENCRYPTION_KEY_BYTES)

    fingerprint = key_fingerprint(key)

    assert fingerprint == key_fingerprint(key)
    assert fingerprint != key_fingerprint(other)
    assert len(fingerprint) == 12
    assert base64.b64encode(key).decode("ascii") not in fingerprint
