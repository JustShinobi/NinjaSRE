"""FR-002, FR-003, FR-016, FR-021 — the catalogue as a property rather than a list.

Parity is checked against a directory tree, so these tests build one. That is
deliberate: a parity check tested only against the real repository passes for as
long as the repository happens to be complete, and the failure it exists to
produce — an integration that shipped without its verifier — is the case that
never gets exercised.

The message matters as much as the failure. FR-002 says the build fails *naming
both* the integration and the artefact, because "parity check failed" across
every package is a message whose next step is a directory listing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations._catalogue.entry import HealthStatus, IntegrationCategory, ParityStatus
from integrations._catalogue.health import HealthLedger
from integrations._catalogue.validation import Artefact, ParityError, parity_of, validate_parity


def complete(root: Path, vendor: str, *, skills: Path, scenarios: Path) -> None:
    """Write all seven artefacts for ``vendor`` under ``root``."""
    package = root / vendor
    (package / "tools").mkdir(parents=True)
    (package / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (package / "tools" / "read_logs.py").write_text("", encoding="utf-8")
    for module in ("__init__.py", "schema.py", "verifier.py", "client.py"):
        (package / module).write_text("", encoding="utf-8")
    (package / "docs.md").write_text("# setup\n", encoding="utf-8")
    (skills / vendor).mkdir(parents=True)
    (skills / vendor / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    scenarios.mkdir(parents=True, exist_ok=True)
    (scenarios / f"{vendor}.py").write_text("SCENARIOS = ()\n", encoding="utf-8")


@pytest.fixture
def tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Return a package root, a skill root, and a scenario root."""
    return tmp_path / "integrations", tmp_path / "skills", tmp_path / "scenarios"


def test_an_integration_with_all_seven_artefacts_is_at_parity(
    tree: tuple[Path, Path, Path],
) -> None:
    package_root, skill_root, scenario_root = tree
    complete(package_root, "acme", skills=skill_root, scenarios=scenario_root)

    report = parity_of(
        "acme", package_root=package_root, skill_root=skill_root, scenario_root=scenario_root
    )

    assert report.status is ParityStatus.COMPLETE
    assert set(report.present) == set(Artefact)
    assert report.missing == ()


@pytest.mark.parametrize(
    ("removed", "artefact"),
    [
        ("schema.py", Artefact.SCHEMA),
        ("verifier.py", Artefact.VERIFIER),
        ("client.py", Artefact.CLIENT),
        ("docs.md", Artefact.DOCS),
    ],
)
def test_a_missing_module_is_reported_as_the_artefact_it_is(
    tree: tuple[Path, Path, Path], removed: str, artefact: Artefact
) -> None:
    package_root, skill_root, scenario_root = tree
    complete(package_root, "acme", skills=skill_root, scenarios=scenario_root)
    (package_root / "acme" / removed).unlink()

    report = parity_of(
        "acme", package_root=package_root, skill_root=skill_root, scenario_root=scenario_root
    )

    assert report.missing == (artefact,)
    assert report.status is ParityStatus.INCOMPLETE


def test_a_missing_skill_is_found_even_though_it_lives_in_another_package(
    tree: tuple[Path, Path, Path],
) -> None:
    """Five of the seven are in the vendor package. Two are not, and those are
    the two a contributor forgets."""
    package_root, skill_root, scenario_root = tree
    complete(package_root, "acme", skills=skill_root, scenarios=scenario_root)
    (skill_root / "acme" / "SKILL.md").unlink()

    report = parity_of(
        "acme", package_root=package_root, skill_root=skill_root, scenario_root=scenario_root
    )

    assert report.missing == (Artefact.SKILL,)


def test_a_missing_scenario_is_the_seventh_artefact(tree: tuple[Path, Path, Path]) -> None:
    package_root, skill_root, scenario_root = tree
    complete(package_root, "acme", skills=skill_root, scenarios=scenario_root)
    (scenario_root / "acme.py").unlink()

    report = parity_of(
        "acme", package_root=package_root, skill_root=skill_root, scenario_root=scenario_root
    )

    assert report.missing == (Artefact.SCENARIO,)


def test_an_empty_tools_package_is_not_a_tools_package(tree: tuple[Path, Path, Path]) -> None:
    """A directory with only an ``__init__`` declares nothing the agent can call."""
    package_root, skill_root, scenario_root = tree
    complete(package_root, "acme", skills=skill_root, scenarios=scenario_root)

    assert (
        Artefact.TOOLS
        not in parity_of(
            "acme", package_root=package_root, skill_root=skill_root, scenario_root=scenario_root
        ).missing
    )

    (package_root / "acme" / "tools" / "read_logs.py").unlink()
    stripped = parity_of(
        "acme", package_root=package_root, skill_root=skill_root, scenario_root=scenario_root
    )

    assert stripped.missing == (Artefact.TOOLS,)


def test_the_build_failure_names_the_integration_and_the_artefact(
    tree: tuple[Path, Path, Path],
) -> None:
    """FR-002, stated exactly: both names, because one of them is a directory listing."""
    package_root, skill_root, scenario_root = tree
    complete(package_root, "acme", skills=skill_root, scenarios=scenario_root)
    (package_root / "acme" / "verifier.py").unlink()
    report = parity_of(
        "acme", package_root=package_root, skill_root=skill_root, scenario_root=scenario_root
    )

    with pytest.raises(ParityError) as raised:
        validate_parity([report])

    message = str(raised.value)
    assert "acme" in message
    assert "verifier.py" in message
    assert "wrong token" in message, "the message says what the missing artefact prevents"


def test_a_complete_catalogue_validates_silently(tree: tuple[Path, Path, Path]) -> None:
    package_root, skill_root, scenario_root = tree
    complete(package_root, "acme", skills=skill_root, scenarios=scenario_root)
    complete(package_root, "zenith", skills=skill_root, scenarios=scenario_root)

    validate_parity(
        [
            parity_of(
                name,
                package_root=package_root,
                skill_root=skill_root,
                scenario_root=scenario_root,
            )
            for name in ("acme", "zenith")
        ]
    )


# --- Health (FR-016) ---------------------------------------------------------


def test_an_integration_nobody_has_run_is_unknown_rather_than_healthy() -> None:
    """Claiming health for something never checked is the same failure as
    claiming a truncated answer is complete."""
    ledger = HealthLedger()

    assert ledger.status_of("acme").status is HealthStatus.UNKNOWN


def test_a_live_run_failure_marks_the_integration_degraded_and_says_why() -> None:
    """FR-016. A vendor's breaking change is not the operator's build failure."""
    ledger = HealthLedger()

    record = ledger.record_failure("acme", detail="search_logs now returns 422 for a valid query")

    assert record.status is HealthStatus.DEGRADED
    assert "422" in record.detail
    assert ledger.degraded() == (record,)


def test_a_later_success_clears_the_degradation() -> None:
    ledger = HealthLedger()
    ledger.record_failure("acme", detail="broken")

    ledger.record_success("acme")

    assert ledger.status_of("acme").status is HealthStatus.HEALTHY
    assert ledger.degraded() == ()


def test_degradation_is_per_integration_and_leaves_the_rest_alone() -> None:
    """The whole point of degrading rather than failing: everything else runs."""
    ledger = HealthLedger()
    ledger.record_success("zenith")

    ledger.record_failure("acme", detail="the vendor changed the response shape")

    assert ledger.status_of("zenith").status is HealthStatus.HEALTHY
    assert [record.integration for record in ledger.degraded()] == ["acme"]


def test_the_ledger_serialises_for_the_console() -> None:
    ledger = HealthLedger()
    ledger.record_failure("acme", detail="a vendor API break")

    records = ledger.to_records()

    assert records[0]["integration"] == "acme"
    assert records[0]["status"] == HealthStatus.DEGRADED.value


# --- Categories (FR-019, FR-021) ---------------------------------------------


def test_every_domain_the_templates_cover_is_a_catalogue_category() -> None:
    """FR-019 names eleven domains; a category set that did not cover them would
    leave an integration unable to say what it is."""
    assert {category.value for category in IntegrationCategory} >= {
        "logstore",
        "metrics",
        "tracing",
        "cloud_control_plane",
        "database",
        "vcs",
        "cicd",
        "ticketing",
        "incident",
        "communication",
        "data_platform",
    }
