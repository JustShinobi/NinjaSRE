"""Create a capability package that is complete on the first commit (FR-019).

A capability's declaration has fourteen fields, and the four that matter most —
the side-effect level, the approval reason, the anti-examples, the rollback
plan — are the four a hurried author leaves out. Three of those fail the build,
which is the design working. The fourth, ``anti_examples``, does not fail
anything; it just quietly makes selection worse for as long as nobody notices.

So the scaffold writes all of them, with the awkward ones present and marked,
because a template with an empty field somebody has to fill in gets filled in,
and a field that was never mentioned does not.

It writes three files and edits none: the tool module, the ``SKILL.md``, and
the contract test. That is the whole of registration — discovery walks the
package — and it is what makes "adding a capability edits zero existing files"
a property rather than an aspiration.

Usage::

    python tools/scaffold_capability.py <name> --domain <domain> [--vendor <vendor>]
                                        [--skill-only] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
DOMAIN_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class ScaffoldError(Exception):
    """The capability cannot be created as asked."""


@dataclass(frozen=True)
class Plan:
    """Where a scaffolded capability's three files go."""

    tool_module: Path
    skill_manifest: Path
    contract_test: Path

    def paths(self) -> tuple[Path, ...]:
        """Return every path this plan writes, in the order it writes them."""
        return (self.tool_module, self.skill_manifest, self.contract_test)


TOOL_TEMPLATE = '''"""TODO: one line on what this tool reads, and what it is for.

TODO: a paragraph on why this tool exists in the shape it does — what the
alternative was, and why it reads the way it reads rather than the obvious way.

Source of truth: TODO — the vendor endpoint or subsystem this reflects, so a
future reader can check the mapping when the upstream changes.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel

_USE_CASES = (
    "TODO: a situation where this is the right call",
    "TODO: a second one, phrased the way an alert would be",
)

# Anti-examples suppress this capability when they describe the incident. They
# are the highest-value field here and the one most often left empty: without
# them the tool competes for a slot on every incident that shares a tag.
_ANTI_EXAMPLES = (
    "TODO: a situation where this looks relevant and is not",
)


@tool(
    name="{tool_name}",
    display_name="{display_name}",
    description=(
        "TODO: what it returns and when to reach for it, in two sentences. This is "
        "what the model reads when choosing, so write it for that reader."
    ),
    domain="{domain}",
    evidence_source="{evidence_source}",
    evidence_type=EvidenceType.LOG,
    # No default exists for this. Choose deliberately: read, read_sensitive,
    # write_reversible, write_irreversible, destructive. Anything above
    # read_sensitive also needs requires_approval, approval_reason, a rollback
    # plan or planner, and a risk_class — the build will say so.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=({requires!r},)),
    tags=("{domain}",),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def {tool_name}(query: str) -> dict[str, Any]:
    """TODO: what this returns, not how it works."""
    raise NotImplementedError("TODO: call the integration client")
'''

SKILL_TEMPLATE = """---
name: {skill_name}
display_name: {display_name} investigation
description: TODO — one sentence. This is in context on every turn, so make it earn its tokens.
domain: {domain}
applies_when:
  alert_sources: [{evidence_source}]
  tags: [{domain}]
directs_tools:
  - {tool_name}
requires:
  integrations: [{requires}]
---

# TODO: the methodology

Say what to do first and what ends the phase. A skill body is read only when
the skill is selected, so there is room here for the reasoning that does not
fit in a tool description.

Direct the tools by name. Do not instruct anyone to run a command — the build
rejects that, because a command routes around the approval, rollback plan, and
audit record the tool layer exists to provide.

## Order of operations

1. TODO: the first call, and why it is first.
2. TODO: what its result decides.

## What this is not for

TODO: the situation this domain's tools look relevant in and are not. The same
content as the anti-examples, at more length.
"""

TEST_TEMPLATE = '''"""The contract {tool_name} has to keep, independent of the vendor being up.

A capability test that needs the real API is a test that runs nowhere. What is
worth asserting without one: that the declaration is complete, that the schema
is the shape the model will be given, and that a failure comes back classified
rather than raised.
"""

from __future__ import annotations

import pytest

from core.capability.metadata import SideEffectLevel
from core.capability.registered import capability_marker

from {import_path} import {tool_name}

pytestmark = pytest.mark.contract


def test_the_declaration_is_complete() -> None:
    registered = capability_marker({tool_name})

    assert registered is not None
    assert registered.metadata.description.strip()
    assert registered.metadata.use_cases
    assert registered.metadata.anti_examples


def test_the_side_effect_level_matches_what_the_tool_does() -> None:
    registered = capability_marker({tool_name})
    assert registered is not None

    level = registered.metadata.side_effect_level
    if level.needs_approval:
        assert registered.metadata.requires_approval
        assert registered.metadata.approval_reason.strip()
        assert registered.metadata.rollback_plan or registered.metadata.rollback_planner


def test_the_input_schema_is_the_shape_the_model_is_given() -> None:
    registered = capability_marker({tool_name})
    assert registered is not None

    assert registered.input_schema["type"] == "object"
    assert registered.input_schema["properties"]


async def test_a_failure_comes_back_classified_rather_than_raised() -> None:
    registered = capability_marker({tool_name})
    assert registered is not None

    result = await registered.invoke({{}})

    assert not result.succeeded
    assert result.error is not None
'''


def _titled(name: str) -> str:
    """Return ``name`` as a human-readable display name."""
    return name.replace("_", " ").replace("-", " ").capitalize()


def plan_for(repo_root: Path, name: str, domain: str, vendor: str) -> Plan:
    """Return where the three files go for this capability."""
    if vendor:
        package = repo_root / "integrations" / vendor / "tools"
        test_root = repo_root / "tests" / "contract" / "integrations" / vendor
        skill_name = f"{domain}-{vendor}"
    else:
        package = repo_root / "capabilities" / "tools" / domain.replace("-", "_")
        test_root = repo_root / "tests" / "contract" / "capabilities"
        skill_name = domain

    return Plan(
        tool_module=package / f"{name}.py",
        skill_manifest=repo_root / "capabilities" / "skills" / skill_name / "SKILL.md",
        contract_test=test_root / f"test_{name}.py",
    )


def validate(repo_root: Path, name: str, domain: str, vendor: str) -> Plan:
    """Return the plan, or explain why the capability cannot be created."""
    if not TOOL_NAME_PATTERN.match(name):
        raise ScaffoldError(
            f"{name!r} is not a usable tool name: lowercase, starting with a letter, "
            "letters, digits, and underscores only — it is emitted by the model as a symbol"
        )
    if not DOMAIN_PATTERN.match(domain):
        raise ScaffoldError(f"{domain!r} is not a usable domain name")
    if vendor and not DOMAIN_PATTERN.match(vendor):
        raise ScaffoldError(f"{vendor!r} is not a usable vendor name")

    plan = plan_for(repo_root, name, domain, vendor)
    for path in plan.paths():
        if path.exists():
            raise ScaffoldError(f"{path.relative_to(repo_root)} already exists")

    return plan


def _write(path: Path, text: str) -> None:
    """Write ``text`` to ``path``, creating the package chain above it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".py":
        for parent in (path.parent, *path.parent.parents):
            if parent.name in {"tests", "capabilities", "integrations"} or parent == REPO_ROOT:
                break
            initialiser = parent / "__init__.py"
            if not initialiser.exists() and "tests" not in parent.parts:
                initialiser.write_text(
                    f'"""TODO: what {parent.name} owns."""\n\nfrom __future__ import annotations\n',
                    encoding="utf-8",
                    newline="\n",
                )
    path.write_text(text, encoding="utf-8", newline="\n")


def scaffold_capability(
    repo_root: Path,
    name: str,
    domain: str,
    *,
    vendor: str = "",
    skill: bool = True,
    dry_run: bool = False,
) -> list[Path]:
    """Create the capability package and return the paths written."""
    plan = validate(repo_root, name, domain, vendor)
    written = list(plan.paths()) if skill else [plan.tool_module, plan.contract_test]

    if dry_run:
        return written

    import_path = (
        f"integrations.{vendor}.tools.{name}"
        if vendor
        else f"capabilities.tools.{domain.replace('-', '_')}.{name}"
    )
    evidence_source = vendor or domain

    _write(
        plan.tool_module,
        TOOL_TEMPLATE.format(
            tool_name=name,
            display_name=_titled(name),
            domain=domain,
            evidence_source=evidence_source,
            requires=evidence_source,
        ),
    )
    _write(
        plan.contract_test,
        TEST_TEMPLATE.format(tool_name=name, import_path=import_path),
    )
    if skill:
        _write(
            plan.skill_manifest,
            SKILL_TEMPLATE.format(
                skill_name=f"{domain}-{vendor}" if vendor else domain,
                display_name=_titled(vendor or domain),
                domain=domain,
                evidence_source=evidence_source,
                tool_name=name,
                requires=evidence_source,
            ),
        )

    return written


def main(argv: Sequence[str] | None = None) -> int:
    """Create a capability and print what still has to be written by hand."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="the tool name, lowercase with underscores")
    parser.add_argument("--domain", required=True, help="the domain this capability serves")
    parser.add_argument(
        "--vendor",
        default="",
        help="the integration this belongs to, if it reaches exactly one vendor",
    )
    parser.add_argument(
        "--no-skill",
        action="store_true",
        help="write no SKILL.md (a utility tool that stands alone)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would be written without writing it"
    )
    arguments = parser.parse_args(argv)

    try:
        written = scaffold_capability(
            REPO_ROOT,
            arguments.name,
            arguments.domain,
            vendor=arguments.vendor,
            skill=not arguments.no_skill,
            dry_run=arguments.dry_run,
        )
    except ScaffoldError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    verb = "would write" if arguments.dry_run else "wrote"
    for path in written:
        print(f"{verb} {path.relative_to(REPO_ROOT)}")

    if arguments.dry_run:
        return 0

    print("\nNo existing file was edited — discovery finds this on the next build.")
    print("Before it is worth shipping:")
    for index, step in enumerate(remaining_work(), 1):
        print(f"  {index}. {step}")

    return 0


def remaining_work() -> list[str]:
    """Return the parts a scaffold deliberately cannot write."""
    return [
        "Choose the side-effect level deliberately. It has no default, and anything "
        "above read_sensitive needs an approval reason and a rollback plan.",
        "Choose the risk class for anything above read_sensitive: trivial, low, "
        "moderate, high, or critical. It answers three questions — can it be undone, "
        "how far does it reach, can it lose data or availability — and the class is "
        "the worst of the three answers. An undeclared one is treated as critical, so "
        "the tool never runs unattended.",
        "Write the anti-examples. Nothing fails without them; selection just gets "
        "worse, on every incident, until somebody notices.",
        "Write the description for the model that reads it when choosing, not for a "
        "contributor reading the source.",
        "Replace the NotImplementedError with a call through the integration client, "
        "which reaches the vendor via the credential proxy.",
        "Run `make verify` — the build checks the declaration, the skill binding, and "
        "the token budgets.",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
