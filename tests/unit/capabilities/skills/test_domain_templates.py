"""SC-007. Eleven templates, and each one produces a skill the build accepts.

A methodology template is the highest-value content in the system and the
easiest to ship broken, because nothing loads it. Templates are skipped by
discovery on purpose — an incomplete manifest in the catalogue is an entry the
model can select and learn nothing from — and the cost of that exemption is that
a template with a typo in its frontmatter, or one directing a tool whose name
does not match what the scaffold generates, fails for the first contributor to
use it rather than in the build that introduced it.

So this suite does what the scaffold does: substitutes a vendor into each
template, declares the tools the template says it directs, and runs the real
capability validator over the result. A template that would produce an
unacceptable skill fails here.

The second thing asserted is coverage. FR-019 names eleven domains, and the
catalogue's category enum has eleven members for the same reason — a vendor's
category is how the scaffold chooses its template. A category with no template
would be an integration the scaffold cannot start, so the two sets are checked
against each other rather than each against a list somebody typed twice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from capabilities.registry.discovery import DiscoveredCatalogue, discover_skills
from capabilities.registry.validation import failures
from config.constants.capabilities import SKILL_TEMPLATE_DIRECTORY
from core.capability.metadata import (
    EvidenceType,
    Requirements,
    SideEffectLevel,
    ToolMetadata,
)
from core.capability.registered import RegisteredTool
from core.capability.result import CapabilityResult
from integrations._catalogue.entry import IntegrationCategory

REPO_ROOT = Path(__file__).resolve().parents[4]
TEMPLATE_ROOT = REPO_ROOT / "capabilities" / "skills" / SKILL_TEMPLATE_DIRECTORY

#: The vendor a template is instantiated for here. Not a real one: the point is
#: that the substitution is mechanical, and a template that only works for a
#: vendor somebody had in mind is a template that does not work.
VENDOR = "zenith"

#: What the scaffold replaces. One token, uppercase, so a partial substitution
#: is visible in the output rather than plausible.
PLACEHOLDER = "VENDOR"


def template_names() -> tuple[str, ...]:
    """Return every template directory, in name order."""
    return tuple(sorted(path.parent.name for path in TEMPLATE_ROOT.rglob("SKILL.md")))


TEMPLATES = template_names()


def instantiate(template: str, root: Path) -> Path:
    """Write ``template`` into ``root`` with the vendor substituted in."""
    source = (TEMPLATE_ROOT / template / "SKILL.md").read_text(encoding="utf-8")
    destination = root / f"{template}-{VENDOR}"
    destination.mkdir(parents=True)
    manifest = destination / "SKILL.md"
    manifest.write_text(source.replace(PLACEHOLDER, VENDOR), encoding="utf-8", newline="\n")
    return manifest


def declared(name: str) -> RegisteredTool:
    """Return a registration standing in for the tool a template directs."""

    async def call(**arguments: object) -> CapabilityResult:
        return CapabilityResult.ok(name, value=arguments)

    return RegisteredTool(
        metadata=ToolMetadata(
            name=name,
            display_name=name.replace("_", " ").title(),
            description=f"Read {VENDOR} for the incident window.",
            domain="observability",
            tags=(VENDOR,),
            use_cases=("investigate an elevated error rate",),
            anti_examples=("a billing question",),
            requires=Requirements(integrations=(VENDOR,)),
            evidence_source=VENDOR,
            evidence_type=EvidenceType.LOG,
            side_effect_level=SideEffectLevel.READ,
            parallel_safe=True,
        ),
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        output_schema={"type": "object"},
        call=call,
        source_module=f"integrations.{VENDOR}.tools.{name}",
        source_qualname=name,
    )


def test_there_is_a_template_for_every_domain_an_integration_can_declare() -> None:
    """FR-019, checked against the enum rather than against a second list."""
    assert set(TEMPLATES) == {category.value for category in IntegrationCategory}


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_template_produces_a_skill_that_passes_the_build(template: str, tmp_path: Path) -> None:
    """SC-007, run through the real validator rather than a re-implementation."""
    instantiate(template, tmp_path)
    skills = discover_skills([tmp_path])
    assert len(skills) == 1, f"{template}: did not parse into exactly one skill"

    tools = tuple(declared(name) for name in skills[0].metadata.directs_tools)
    found = failures(DiscoveredCatalogue(tools=tools, skills=tuple(skills)))

    assert not found, "\n".join(str(failure) for failure in found)


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_template_directs_tools_named_for_the_vendor_the_scaffold_substitutes(
    template: str, tmp_path: Path
) -> None:
    """A template directing an unsubstituted name is one that dangles the day it
    is used, and the validator above cannot see it because the test declares
    whatever the template asked for."""
    instantiate(template, tmp_path)
    skill = discover_skills([tmp_path])[0]

    assert skill.metadata.directs_tools
    for directed in skill.metadata.directs_tools:
        assert directed.startswith(f"{VENDOR}_"), (
            f"{template}: directs {directed!r}, which the vendor substitution did not reach"
        )


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_template_carries_the_ordering_that_is_its_whole_point(
    template: str, tmp_path: Path
) -> None:
    """A template is methodology or it is a file layout. The numbered order of
    operations is the methodology, and one that lost it in an edit still parses."""
    body = instantiate(template, tmp_path).read_text(encoding="utf-8")

    assert "## Order of operations" in body
    assert "1. **" in body and "2. **" in body
    assert "## What this is not for" in body


@pytest.mark.parametrize("template", TEMPLATES)
def test_no_placeholder_survives_substitution(template: str, tmp_path: Path) -> None:
    body = instantiate(template, tmp_path).read_text(encoding="utf-8")

    assert PLACEHOLDER not in body


def test_templates_stay_out_of_the_catalogue() -> None:
    """A deliberately incomplete manifest the model could select is worse than
    no manifest at all."""
    real = discover_skills([REPO_ROOT / "capabilities" / "skills"])

    assert not [skill for skill in real if SKILL_TEMPLATE_DIRECTORY in skill.path.parts]
