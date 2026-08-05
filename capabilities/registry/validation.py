"""The gate a catalogue passes before anything is allowed to use it.

Every check here answers the same question: would this go wrong at runtime, and
if so, could it have been known at build time? Each one that could is one that
must be, because the runtime in question is an incident.

A dangling skill-to-tool reference is the clearest case. The skill is selected
during an investigation, the model is told to use a tool that does not exist,
and the loop spends iterations discovering that — while an engineer waits. The
same reference is a two-line check against a dictionary at build time.

Failures are collected, not raised one at a time. Fixing six manifests over six
build runs is how a contributor learns to dread the gate; seeing all six at
once is how they fix them in one pass. Each failure carries a distinct rule
name, so the message says which rule fired rather than that "validation
failed".
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from capabilities.registry.disclosure import DiscoveredSkill, body_violations
from capabilities.registry.discovery import DiscoveredCatalogue
from config.constants.capabilities import (
    MAX_CATALOGUE_METADATA_TOKENS,
    MAX_SKILL_METADATA_TOKENS,
    MAX_TOOL_DESCRIPTION_TOKENS,
)
from core.capability.registered import RegisteredTool
from core.capability.tokens import TokenCounter, estimate_tokens

DUPLICATE_TOOL_NAME = "duplicate-tool-name"
DUPLICATE_SKILL_NAME = "duplicate-skill-name"
NAME_USED_BY_BOTH_KINDS = "name-used-by-both-kinds"
DANGLING_DIRECTED_TOOL = "dangling-directed-tool"
SKILL_REQUIRES_NOT_COVERED = "skill-requires-not-covered"
SKILL_METADATA_OVER_BUDGET = "skill-metadata-over-budget"
CATALOGUE_METADATA_OVER_BUDGET = "catalogue-metadata-over-budget"
TOOL_DESCRIPTION_OVER_BUDGET = "tool-description-over-budget"
SKILL_BODY_INSTRUCTS_SHELL = "skill-body-instructs-shell"


@dataclass(frozen=True, order=True)
class ValidationFailure:
    """One reason the catalogue must not be built."""

    rule: str
    subject: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.subject}: {self.message}"


class ValidationError(Exception):
    """The catalogue is not usable, with every reason attached."""

    def __init__(self, failures: Sequence[ValidationFailure]) -> None:
        self.failures = tuple(sorted(failures))
        rules = sorted({failure.rule for failure in self.failures})
        super().__init__(
            f"{len(self.failures)} capability declaration problem(s) "
            f"[{', '.join(rules)}]:\n" + "\n".join(f"  {failure}" for failure in self.failures)
        )


def _duplicate_tool_failures(tools: Sequence[RegisteredTool]) -> list[ValidationFailure]:
    """Return a failure for each name declared by more than one tool."""
    by_name: defaultdict[str, list[RegisteredTool]] = defaultdict(list)
    for found in tools:
        by_name[found.name].append(found)

    return [
        ValidationFailure(
            rule=DUPLICATE_TOOL_NAME,
            subject=name,
            message=(
                "declared in "
                + " and ".join(sorted(found.source for found in declared))
                + " — the model would call one of them and the trace could not say which"
            ),
        )
        for name, declared in by_name.items()
        if len(declared) > 1
    ]


def _duplicate_skill_failures(skills: Sequence[DiscoveredSkill]) -> list[ValidationFailure]:
    """Return a failure for each name declared by more than one skill."""
    by_name: defaultdict[str, list[DiscoveredSkill]] = defaultdict(list)
    for skill in skills:
        by_name[skill.name].append(skill)

    return [
        ValidationFailure(
            rule=DUPLICATE_SKILL_NAME,
            subject=name,
            message="declared in " + " and ".join(sorted(str(s.path) for s in declared)),
        )
        for name, declared in by_name.items()
        if len(declared) > 1
    ]


def _cross_kind_failures(
    tools: Sequence[RegisteredTool], skills: Sequence[DiscoveredSkill]
) -> list[ValidationFailure]:
    """Return a failure for each name claimed by both a tool and a skill."""
    tool_names = {found.name for found in tools}

    return [
        ValidationFailure(
            rule=NAME_USED_BY_BOTH_KINDS,
            subject=skill.name,
            message=(
                f"is both a skill ({skill.path}) and a tool — selection scores one "
                "catalogue, so a shared name makes the rationale unreadable"
            ),
        )
        for skill in skills
        if skill.name in tool_names
    ]


def _binding_failures(
    tools: Sequence[RegisteredTool], skills: Sequence[DiscoveredSkill]
) -> list[ValidationFailure]:
    """Return a failure for each skill-to-tool reference that does not resolve."""
    by_name = {found.name: found for found in tools}
    failures: list[ValidationFailure] = []

    for skill in skills:
        for directed in skill.metadata.directs_tools:
            if directed not in by_name:
                failures.append(
                    ValidationFailure(
                        rule=DANGLING_DIRECTED_TOOL,
                        subject=skill.name,
                        message=(
                            f"directs {directed!r}, which no package declares — the model "
                            "would be told to use a tool that is not there"
                        ),
                    )
                )

    return failures


def _requirement_failures(
    tools: Sequence[RegisteredTool], skills: Sequence[DiscoveredSkill]
) -> list[ValidationFailure]:
    """Return a failure for each skill requiring more than its tools do.

    A skill that requires an integration none of its tools touch is excluded
    from teams that could have used it, and nothing reports the exclusion as
    anything other than "not configured".
    """
    by_name = {found.name: found for found in tools}
    failures: list[ValidationFailure] = []

    for skill in skills:
        directed = [by_name[name] for name in skill.metadata.directs_tools if name in by_name]
        covered = {
            requirement for found in directed for requirement in found.metadata.requires.names()
        }
        excess = sorted(set(skill.metadata.requires.names()) - covered)
        if excess and directed:
            failures.append(
                ValidationFailure(
                    rule=SKILL_REQUIRES_NOT_COVERED,
                    subject=skill.name,
                    message=(
                        f"requires {', '.join(excess)}, which none of the tools it directs "
                        "needs — the skill would be hidden from teams that could use it"
                    ),
                )
            )

    return failures


def _budget_failures(
    tools: Sequence[RegisteredTool],
    skills: Sequence[DiscoveredSkill],
    *,
    counter: TokenCounter,
) -> list[ValidationFailure]:
    """Return a failure for each entry, and for the skill index, over budget.

    The catalogue total counts skills only. A skill's index entry is in context
    on every turn whether or not it is used, so it scales with the size of the
    catalogue; a tool's description is in context only when the tool is
    selected, and the number selected is capped per turn. Adding tool prose to
    the standing total would measure a cost nobody pays, and would make the
    ceiling fire on a catalogue that fits comfortably.
    """
    failures: list[ValidationFailure] = []
    total = 0

    for skill in skills:
        total += skill.metadata_tokens
        if skill.metadata_tokens > MAX_SKILL_METADATA_TOKENS:
            failures.append(
                ValidationFailure(
                    rule=SKILL_METADATA_OVER_BUDGET,
                    subject=skill.name,
                    message=(
                        f"index entry costs {skill.metadata_tokens} tokens, over the "
                        f"{MAX_SKILL_METADATA_TOKENS} ceiling — this is paid on every "
                        "turn whether or not the skill is used"
                    ),
                )
            )

    for found in tools:
        cost = counter(found.metadata.description)
        if cost > MAX_TOOL_DESCRIPTION_TOKENS:
            failures.append(
                ValidationFailure(
                    rule=TOOL_DESCRIPTION_OVER_BUDGET,
                    subject=found.name,
                    message=(
                        f"description costs {cost} tokens, over the "
                        f"{MAX_TOOL_DESCRIPTION_TOKENS} ceiling — prose this long "
                        "belongs in the skill that directs this tool"
                    ),
                )
            )

    if total > MAX_CATALOGUE_METADATA_TOKENS:
        failures.append(
            ValidationFailure(
                rule=CATALOGUE_METADATA_OVER_BUDGET,
                subject="catalogue",
                message=(
                    f"the skill index costs {total} tokens, over the "
                    f"{MAX_CATALOGUE_METADATA_TOKENS} ceiling — this is paid on every "
                    "turn before anything is chosen. Raise the constant deliberately, "
                    "with a reason, or shorten what is already there"
                ),
            )
        )

    return failures


def _body_failures(skills: Sequence[DiscoveredSkill]) -> list[ValidationFailure]:
    """Return a failure for each skill body that instructs shell execution."""
    return [
        ValidationFailure(
            rule=SKILL_BODY_INSTRUCTS_SHELL,
            subject=skill.name,
            message=violation,
        )
        for skill in skills
        for violation in body_violations(skill.body())
    ]


def failures(
    catalogue: DiscoveredCatalogue,
    *,
    counter: TokenCounter = estimate_tokens,
    check_bodies: bool = True,
) -> tuple[ValidationFailure, ...]:
    """Return every reason ``catalogue`` must not be built, in rule order.

    ``check_bodies`` reads every skill from disk, which is the one expensive
    check here. It is on by default because the build is where that cost
    belongs, and off for callers rebuilding a catalogue whose bodies have not
    changed.
    """
    collected: list[ValidationFailure] = []
    collected.extend(_duplicate_tool_failures(catalogue.tools))
    collected.extend(_duplicate_skill_failures(catalogue.skills))
    collected.extend(_cross_kind_failures(catalogue.tools, catalogue.skills))
    collected.extend(_binding_failures(catalogue.tools, catalogue.skills))
    collected.extend(_requirement_failures(catalogue.tools, catalogue.skills))
    collected.extend(_budget_failures(catalogue.tools, catalogue.skills, counter=counter))
    if check_bodies:
        collected.extend(_body_failures(catalogue.skills))

    return tuple(sorted(collected))


def validate(
    catalogue: DiscoveredCatalogue,
    *,
    counter: TokenCounter = estimate_tokens,
    check_bodies: bool = True,
) -> DiscoveredCatalogue:
    """Return ``catalogue`` unchanged, or raise with every problem in it.

    Returning the catalogue rather than ``None`` is so the only way to obtain a
    validated one is to have validated it. A function that returns nothing
    invites a caller who forgets to call it.
    """
    found = failures(catalogue, counter=counter, check_bodies=check_bodies)
    if found:
        raise ValidationError(found)
    return catalogue


def rules() -> tuple[str, ...]:
    """Return every rule name, for a test that asserts each one is covered."""
    return (
        CATALOGUE_METADATA_OVER_BUDGET,
        DANGLING_DIRECTED_TOOL,
        DUPLICATE_SKILL_NAME,
        DUPLICATE_TOOL_NAME,
        NAME_USED_BY_BOTH_KINDS,
        SKILL_BODY_INSTRUCTS_SHELL,
        SKILL_METADATA_OVER_BUDGET,
        SKILL_REQUIRES_NOT_COVERED,
        TOOL_DESCRIPTION_OVER_BUDGET,
    )


__all__ = [
    "CATALOGUE_METADATA_OVER_BUDGET",
    "DANGLING_DIRECTED_TOOL",
    "DUPLICATE_SKILL_NAME",
    "DUPLICATE_TOOL_NAME",
    "NAME_USED_BY_BOTH_KINDS",
    "SKILL_BODY_INSTRUCTS_SHELL",
    "SKILL_METADATA_OVER_BUDGET",
    "SKILL_REQUIRES_NOT_COVERED",
    "TOOL_DESCRIPTION_OVER_BUDGET",
    "ValidationError",
    "ValidationFailure",
    "failures",
    "rules",
    "validate",
]
