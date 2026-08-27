"""SC-003. The direct-credential check, and the violation that proves it fires.

FR-017 asks CI to fail an integration module that reads a credential from the
environment. A check nobody has watched fail is a check that might be scanning
an empty list of roots, and the repository would look exactly as clean either
way — so the fixture below is a module doing the forbidden thing in each of the
ways it can be done, and the first test asserts every one of them is caught.

The second rule is the quieter one. ``CredentialStore.reveal`` is the single
method in the platform that returns plaintext, and the whole of Article IV rests
on the credential proxy being its only caller. That is a one-line grep today;
this makes it a build failure tomorrow.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.check_direct_credentials import (
    CREDENTIAL_ENV_NAME_RULE,
    CREDENTIAL_REVEAL_RULE,
    ENV_LOOKUP_RULE,
    Violation,
    find_violations,
    is_credential_name,
    may_read_environment,
    may_reveal_secrets,
)

pytestmark = pytest.mark.unit

#: The fixture SC-003 asks for: an integration client that helps itself to a
#: credential, in each of the ways a contributor in a hurry would reach for.
VIOLATION_FIXTURE = '''
"""A vendor client that read the key itself. Every line here is a defect."""

from __future__ import annotations

import os

DATADOG_API_KEY_ENV = "DATADOG_API_KEY"


def headers() -> dict[str, str]:
    """Build the auth headers the short way."""
    return {
        "DD-API-KEY": os.environ["DATADOG_API_KEY"],
        "DD-APPLICATION-KEY": os.getenv("DATADOG_APP_KEY", ""),
    }


async def token(store: object) -> str:
    """Ask the vault directly, from a tier that may not."""
    secret = await store.reveal("datadog/payments")
    return secret.reveal()
'''

#: The same file, written the way the boundary requires. Nothing in it needs a
#: comment explaining why it is allowed, which is the point.
CLEAN_FIXTURE = '''
"""A vendor client that carries a handle and no secret."""

from __future__ import annotations

from integrations._base.client import IntegrationClient


class DatadogClient(IntegrationClient):
    """Datadog over the credential proxy."""

    async def search(self, query: str) -> object:
        """Return the log events matching ``query``."""
        return await self.get("/api/v2/logs/events", params={"query": query})
'''


def _write(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_the_check_fails_on_a_deliberate_violation(tmp_path: Path) -> None:
    _write(tmp_path, "integrations/datadog/client.py", VIOLATION_FIXTURE)

    found = find_violations([tmp_path])

    rules = {violation.rule for violation in found}
    assert ENV_LOOKUP_RULE in rules
    assert CREDENTIAL_ENV_NAME_RULE in rules
    assert CREDENTIAL_REVEAL_RULE in rules


def test_the_failure_names_the_module(tmp_path: Path) -> None:
    """An operator reading CI output needs the file, not a count."""
    offender = _write(tmp_path, "integrations/datadog/client.py", VIOLATION_FIXTURE)

    found = find_violations([tmp_path])

    assert found
    assert all(violation.path == offender for violation in found)
    assert "client.py" in str(found[0])


def test_a_client_on_the_base_class_is_clean(tmp_path: Path) -> None:
    _write(tmp_path, "integrations/datadog/client.py", CLEAN_FIXTURE)

    assert find_violations([tmp_path]) == []


def test_the_proxy_may_reveal_secrets_and_nothing_else_may() -> None:
    """The exemption is a path, so moving the code moves the permission."""
    assert may_reveal_secrets(Path("platform/credentials/proxy/resolution.py"))
    assert not may_reveal_secrets(Path("platform/credentials/vault.py"))
    assert not may_reveal_secrets(Path("integrations/datadog/client.py"))
    assert not may_reveal_secrets(Path("capabilities/tools/observability/datadog.py"))


def test_the_constants_tier_may_name_environment_variables() -> None:
    """``config/constants/`` is where an env-var name is supposed to be written."""
    assert may_read_environment(Path("config/constants/security.py"))
    assert not may_read_environment(Path("integrations/datadog/config.py"))


@pytest.mark.parametrize(
    "name",
    [
        "DATADOG_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "PAGERDUTY_TOKEN",
        "GITHUB_APP_PRIVATE_KEY",
        "SLACK_SIGNING_SECRET",
        "GRAFANA_PASSWORD",
        "NEW_RELIC_LICENSE_KEY",
    ],
)
def test_credential_shaped_names_are_recognised(name: str) -> None:
    assert is_credential_name(name)


@pytest.mark.parametrize(
    "name",
    ["AWS_REGION", "DATADOG_SITE", "KUBERNETES_NAMESPACE", "LOG_LEVEL", "HTTP_PROXY"],
)
def test_ordinary_configuration_names_are_not_credentials(name: str) -> None:
    """A capability legitimately needs a region. Flagging it would train people to ignore the check."""
    assert not is_credential_name(name)


@pytest.mark.sweep
def test_the_repository_itself_is_clean() -> None:
    """The rule holds for the code that ships, not only for fixtures."""
    found = find_violations()

    assert found == [], "\n".join(str(violation) for violation in found)


def test_a_violation_renders_with_file_line_and_rule() -> None:
    rendered = str(
        Violation(
            path=Path("integrations/datadog/client.py"),
            line=17,
            name="DATADOG_API_KEY",
            rule=ENV_LOOKUP_RULE,
        )
    )

    assert "integrations/datadog/client.py:17" in rendered
    assert ENV_LOOKUP_RULE in rendered
    assert "DATADOG_API_KEY" in rendered
