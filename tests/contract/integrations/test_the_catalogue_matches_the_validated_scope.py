"""The catalogue holds exactly the integrations this deployment's environment
can validate end to end, and nothing else.

A card that cannot be verified against anything is worse than an absent card:
it is chosen on the strength of its presence and fails during an incident. The
fifteen names below are the only literal list this module authorises, because
the list itself is the decision under test — everywhere else, the catalogue is
read, never restated.
"""

from __future__ import annotations

import pytest

from integrations._catalogue.discovery import entry, vendor_packages

#: Every integration an environment exists to validate end to end today: a
#: credential stored, the connection verified, and at least one real read
#: exercised.
VALIDATED_SCOPE: tuple[str, ...] = (
    "alertmanager",
    "argocd",
    "github",
    "google_gemini",
    "grafana",
    "hermes",
    "kubernetes",
    "loki",
    "openobserve",
    "prometheus",
    "proxmox",
    "pushover",
    "redis",
    "signoz",
    "telegram",
)

#: A representative sample of names that no longer address an installed
#: package. Not exhaustive — the architecture sweep owns that — just enough to
#: prove the catalogue answers "absent", not "present and broken".
SOME_NAMES_OUTSIDE_THE_SCOPE: tuple[str, ...] = ("datadog", "slack", "aws", "jira")


def test_the_catalogue_holds_exactly_the_validated_scope() -> None:
    installed = vendor_packages()

    assert set(installed) == set(VALIDATED_SCOPE), (
        f"installed: {sorted(installed)}\nexpected: {sorted(VALIDATED_SCOPE)}"
    )
    assert len(installed) == len(VALIDATED_SCOPE), "a duplicate package name would hide here"


@pytest.mark.parametrize("name", SOME_NAMES_OUTSIDE_THE_SCOPE)
def test_a_name_outside_the_scope_is_a_named_absence_not_a_degraded_entry(name: str) -> None:
    """A vendor this environment cannot validate is not in the catalogue at
    all — asking for it by name fails the lookup, rather than returning an
    entry that reports itself broken."""
    with pytest.raises(LookupError, match=name):
        entry(name)
