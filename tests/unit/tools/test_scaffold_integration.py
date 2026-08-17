"""FR-017, FR-018, SC-002. The scaffold is the framework's actual interface.

Everything else in feature 024 is machinery a contributor never reads. What they
run is this, once, and what it produces decides whether the next two hours are
spent on the vendor's API or on rediscovering the anatomy — so the properties
worth testing are the ones that decide that.

``all seven``
    The point. A scaffold producing six is a scaffold whose seventh artefact is
    written by whoever remembers, which is the state the parity check exists
    because of.

``no existing file is edited``
    the property that makes a catalogue of any size addable one at
    a time. A scaffold that appended to a registry would work for the first ten
    and produce a merge conflict on every pull request after that.

``the domain selects the template``
    FR-018. The methodology is the highest-value content in the system, and a
    skill started from a blank file is a skill that reinvents it — usually
    worse, and always differently from every other one.

``what it refuses to decide``
    The side-effect level has no default, structurally. A scaffold that guessed
    would be a scaffold that guessed wrong on the one capability where it
    mattered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations._catalogue.entry import IntegrationCategory
from integrations._catalogue.validation import Artefact, parity_of
from tools.scaffold_integration import (
    ScaffoldError,
    remaining_work,
    scaffold_integration,
    template_for,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DOMAIN = "logstore"


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """Return a repository root with the directories the scaffold writes into."""
    (tmp_path / "integrations").mkdir()
    (tmp_path / "capabilities" / "skills" / "_templates" / DOMAIN).mkdir(parents=True)
    (tmp_path / "capabilities" / "skills" / "_templates" / DOMAIN / "SKILL.md").write_text(
        "---\nname: logstore-VENDOR\ndomain: logstore\ndirects_tools:\n  - VENDOR_log_statistics\n"
        "---\n\n# VENDOR\n\n## Order of operations\n\n1. **Count.**\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "synthetic" / "integration_scenarios").mkdir(parents=True)
    return tmp_path


def test_the_scaffold_writes_all_seven_artefacts(checkout: Path) -> None:
    scaffold_integration(checkout, "zenith", domain=DOMAIN)

    report = parity_of(
        "zenith",
        package_root=checkout / "integrations",
        skill_root=checkout / "capabilities" / "skills",
        scenario_root=checkout / "tests" / "synthetic" / "integration_scenarios",
    )

    assert report.missing == (), report.failure_message()
    assert set(report.present) == set(Artefact)


def test_scaffolding_edits_no_existing_file(checkout: Path) -> None:
    """SC-002, asserted by content rather than by inspection."""
    before = {path: path.read_bytes() for path in sorted(checkout.rglob("*")) if path.is_file()}

    scaffold_integration(checkout, "zenith", domain=DOMAIN)

    for path, content in before.items():
        assert path.read_bytes() == content, f"{path} was edited"


def test_a_dry_run_writes_nothing_and_reports_everything(checkout: Path) -> None:
    written = scaffold_integration(checkout, "zenith", domain=DOMAIN, dry_run=True)

    assert len(written) >= 7
    assert not (checkout / "integrations" / "zenith").exists()


def test_the_skill_starts_from_the_domain_template(checkout: Path) -> None:
    """FR-018. The template's methodology arrives; the placeholder does not."""
    scaffold_integration(checkout, "zenith", domain=DOMAIN)
    skill = (checkout / "capabilities" / "skills" / "zenith" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "## Order of operations" in skill
    assert "1. **Count.**" in skill
    assert "VENDOR" not in skill
    assert "zenith_log_statistics" in skill


def test_the_generated_tool_is_the_one_the_skill_directs(checkout: Path) -> None:
    """A scaffold whose skill dangles is a scaffold whose first build fails."""
    scaffold_integration(checkout, "zenith", domain=DOMAIN)
    tool = (checkout / "integrations" / "zenith" / "tools" / "log_statistics.py").read_text(
        encoding="utf-8"
    )

    assert 'TOOL_NAME = "zenith_log_statistics"' in tool
    assert "name=TOOL_NAME," in tool


def test_every_generated_module_carries_a_provenance_header(checkout: Path) -> None:
    """FR-017. Where a file came from, so a reader knows what to expect of it."""
    scaffold_integration(checkout, "zenith", domain=DOMAIN)
    package = checkout / "integrations" / "zenith"

    for module in sorted(package.rglob("*.py")):
        header = module.read_text(encoding="utf-8")[:600]
        assert "scaffold_integration" in header, f"{module.name} has no provenance header"


def test_the_side_effect_level_is_present_and_marked_as_a_decision(checkout: Path) -> None:
    """It has no default, structurally. The scaffold writes it and says so."""
    scaffold_integration(checkout, "zenith", domain=DOMAIN)
    tool = (checkout / "integrations" / "zenith" / "tools" / "log_statistics.py").read_text(
        encoding="utf-8"
    )

    assert "side_effect_level=SideEffectLevel.READ" in tool
    assert "No default exists for this" in tool


def test_the_generated_scenario_is_wired_into_the_harness(checkout: Path) -> None:
    """The seventh artefact has to be collectable, not merely present."""
    scaffold_integration(checkout, "zenith", domain=DOMAIN)
    scenario = (checkout / "tests" / "synthetic" / "integration_scenarios" / "zenith.py").read_text(
        encoding="utf-8"
    )

    assert "SCENARIOS" in scenario
    assert "IntegrationScenario(" in scenario
    assert "zenith_log_statistics" in scenario


def test_the_generated_profile_declares_a_category_and_a_pagination_style(
    checkout: Path,
) -> None:
    """FR-021's row cannot be filled in later by somebody who was not there."""
    scaffold_integration(checkout, "zenith", domain=DOMAIN)
    package = (checkout / "integrations" / "zenith" / "__init__.py").read_text(encoding="utf-8")

    assert "PROFILE" in package
    assert "IntegrationCategory.LOG_STORE" in package
    assert "EndpointPagination" in (
        (checkout / "integrations" / "zenith" / "client.py").read_text(encoding="utf-8")
    )


def test_an_unknown_domain_is_refused_with_the_list_of_the_ones_that_exist(
    checkout: Path,
) -> None:
    with pytest.raises(ScaffoldError) as raised:
        scaffold_integration(checkout, "zenith", domain="lgostore")

    assert DOMAIN in str(raised.value)


def test_an_integration_that_already_exists_is_refused_rather_than_overwritten(
    checkout: Path,
) -> None:
    scaffold_integration(checkout, "zenith", domain=DOMAIN)

    with pytest.raises(ScaffoldError, match="already exists"):
        scaffold_integration(checkout, "zenith", domain=DOMAIN)


def test_a_name_the_model_could_not_emit_is_refused(checkout: Path) -> None:
    """The vendor name becomes a tool-name prefix, which the model emits as a symbol."""
    with pytest.raises(ScaffoldError, match="usable integration name"):
        scaffold_integration(checkout, "Zenith Cloud", domain=DOMAIN)


def test_a_name_beginning_with_an_underscore_is_refused(checkout: Path) -> None:
    """That prefix means "framework package", and discovery skips those."""
    with pytest.raises(ScaffoldError, match="underscore"):
        scaffold_integration(checkout, "_zenith", domain=DOMAIN)


def test_every_domain_a_vendor_can_declare_resolves_to_a_shipped_template() -> None:
    """SC-007's other half: eleven categories, and the scaffold reaches each one."""
    templates = REPO_ROOT / "capabilities" / "skills" / "_templates"

    for category in IntegrationCategory:
        assert (templates / template_for(category.value) / "SKILL.md").is_file()


def test_the_scaffold_prints_what_it_deliberately_cannot_decide() -> None:
    steps = remaining_work("zenith")

    assert steps
    assert any("side-effect level" in step for step in steps)
    assert any("permission" in step for step in steps)
