"""Splitting a skill into the part that is always in context and the part that is not.

A skill's index entry — its name, description, and the conditions it claims to
apply to — is paid for on every turn, for every skill the team has. Its body,
which is where the methodology actually lives, is paid for only by the turn
that selected it. That ratio is what makes a large catalogue affordable: eighty
entries and one body, rather than eighty bodies.

The failure mode is not a crash. Load a body eagerly and everything still
works; the only symptom is a context bill that grows with the catalogue and
that nobody attributes to this file. So ``DiscoveredSkill`` holds a path, and
reading it is something a caller has to ask for.

This module also owns the lint on skill bodies. A skill directs tools; a skill
that tells the model to run a shell command has routed around the approval
gate, the rollback plan, and the audit record that the tool layer exists to
provide. The rule has to survive eighty-five ported skills without being turned
off, so it fires on instructions to execute and not on prose about commands.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from capabilities.registry.frontmatter import (
    FrontmatterError,
    FrontmatterValue,
    as_list,
    as_mapping,
    as_text,
    parse_frontmatter,
    split_frontmatter,
)
from core.capability.metadata import (
    AppliesWhen,
    Requirements,
    SkillMetadata,
    metadata_text,
)
from core.capability.tokens import TokenCounter, estimate_tokens

#: Every key a manifest may carry. Unknown keys are rejected rather than
#: ignored: a typo in a key name is a declaration that silently did nothing,
#: and the skill then fails to match the incidents it was written for.
_ALLOWED_KEYS = frozenset(
    {
        "name",
        "display_name",
        "description",
        "domain",
        "applies_when",
        "directs_tools",
        "requires",
        "tags",
        "use_cases",
        "anti_examples",
    }
)

_REQUIRED_KEYS = ("name", "description", "domain")

_ALLOWED_APPLIES_WHEN_KEYS = frozenset({"alert_sources", "tags", "domains"})
_ALLOWED_REQUIRES_KEYS = frozenset({"integrations", "sandbox_profiles"})

#: Fenced-block languages that mean "this is a command to run". ``python`` is
#: absent on purpose: an illustrative snippet showing what a tool computes is
#: how a methodology explains itself, and banning it would gut the format.
_EXECUTABLE_FENCE_LANGUAGES = frozenset(
    {"bash", "sh", "shell", "zsh", "console", "powershell", "ps1", "cmd", "bat"}
)

#: The command-line programs a skill must never instruct anyone to run.
_COMMAND_NAMES = (
    "python",
    "python3",
    "bash",
    "sh",
    "zsh",
    "ssh",
    "scp",
    "curl",
    "wget",
    "kubectl",
    "helm",
    "docker",
    "psql",
    "mysql",
    "redis-cli",
    "aws",
    "gcloud",
    "az",
    "terraform",
    "ansible",
    "systemctl",
    "service",
)

#: An imperative aimed at one of those programs. The verb is what separates
#: "run kubectl" from "the kubectl equivalent is", and keeping the verb in the
#: pattern is what stops the rule being disabled by the tenth false positive.
_EXECUTION_INSTRUCTION = re.compile(
    r"\b(?:run|execute|invoke|launch|issue)\b[^.\n]{0,60}?"
    r"[`'\"]?\b(?:" + "|".join(re.escape(name) for name in _COMMAND_NAMES) + r")\b",
    re.IGNORECASE,
)

#: A shell prompt at the start of a line is a transcript to be retyped. Only
#: ``$`` — a root ``#`` prompt is indistinguishable from a Markdown heading, and
#: a rule that rejects every heading in every skill body is a rule that gets
#: switched off within a day.
_SHELL_PROMPT = re.compile(r"^\s*\$\s+\S")

_FENCE = re.compile(r"^\s*```+\s*([A-Za-z0-9_+-]*)")


class SkillManifestError(Exception):
    """A ``SKILL.md`` cannot be read as a skill declaration."""


def _reject_unknown(
    mapping: Mapping[str, FrontmatterValue],
    allowed: frozenset[str],
    *,
    source: str,
    where: str,
) -> None:
    """Raise naming every key that is not part of the format."""
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise SkillManifestError(
            f"{source}: unknown {where} key(s) {', '.join(unknown)} — "
            f"allowed: {', '.join(sorted(allowed))}"
        )


def parse_skill_manifest(text: str, *, source: str) -> tuple[SkillMetadata, str]:
    """Return the metadata and body a ``SKILL.md`` describes."""
    try:
        block, body = split_frontmatter(text, source=source)
        declared = parse_frontmatter(block, source=source)
    except FrontmatterError as error:
        raise SkillManifestError(str(error)) from error

    _reject_unknown(declared, _ALLOWED_KEYS, source=source, where="frontmatter")

    missing = [key for key in _REQUIRED_KEYS if not declared.get(key)]
    if missing:
        raise SkillManifestError(
            f"{source}: frontmatter is missing required field(s): {', '.join(missing)}"
        )

    try:
        applies = as_mapping(declared.get("applies_when"), key="applies_when", source=source)
        requires = as_mapping(declared.get("requires"), key="requires", source=source)
        _reject_unknown(applies, _ALLOWED_APPLIES_WHEN_KEYS, source=source, where="applies_when")
        _reject_unknown(requires, _ALLOWED_REQUIRES_KEYS, source=source, where="requires")

        name = as_text(declared["name"], key="name", source=source)
        metadata = SkillMetadata(
            name=name,
            display_name=as_text(declared.get("display_name"), key="display_name", source=source)
            or name,
            description=as_text(declared["description"], key="description", source=source),
            domain=as_text(declared["domain"], key="domain", source=source),
            tags=as_list(declared.get("tags"), key="tags", source=source),
            use_cases=as_list(declared.get("use_cases"), key="use_cases", source=source),
            anti_examples=as_list(
                declared.get("anti_examples"), key="anti_examples", source=source
            ),
            applies_when=AppliesWhen(
                alert_sources=as_list(
                    applies.get("alert_sources"), key="alert_sources", source=source
                ),
                tags=as_list(applies.get("tags"), key="applies_when.tags", source=source),
                domains=as_list(applies.get("domains"), key="domains", source=source),
            ),
            directs_tools=as_list(
                declared.get("directs_tools"), key="directs_tools", source=source
            ),
            requires=Requirements(
                integrations=as_list(
                    requires.get("integrations"), key="integrations", source=source
                ),
                sandbox_profiles=as_list(
                    requires.get("sandbox_profiles"), key="sandbox_profiles", source=source
                ),
            ),
        )
    except FrontmatterError as error:
        raise SkillManifestError(str(error)) from error
    except ValueError as error:
        raise SkillManifestError(f"{source}: {error}") from error

    return metadata, body


def body_violations(body: str) -> tuple[str, ...]:
    """Return every place ``body`` instructs execution rather than directing a tool.

    Fenced blocks are judged by their language tag and lines by their wording,
    which is what lets a skill say "the ``kubectl`` equivalent of this tool is
    ``kubectl get pods``" — orientation a reader needs — while rejecting "run
    ``kubectl delete pod``".
    """
    violations: list[str] = []
    fence_language: str | None = None

    for number, line in enumerate(body.splitlines(), start=1):
        fence = _FENCE.match(line)
        if fence is not None:
            language = fence.group(1).lower()
            if fence_language is None:
                fence_language = language
                if language in _EXECUTABLE_FENCE_LANGUAGES:
                    violations.append(
                        f"line {number}: a '{language}' code block is a command to run — "
                        "a skill directs tools, which carry approval and rollback"
                    )
            else:
                fence_language = None
            continue

        if fence_language is not None:
            continue

        if _SHELL_PROMPT.match(line):
            violations.append(
                f"line {number}: a shell prompt is a transcript to retype — "
                "reference the tool that does this instead"
            )
        elif _EXECUTION_INSTRUCTION.search(line):
            violations.append(
                f"line {number}: instructs running a command directly — "
                "reference the tool that wraps it instead"
            )

    return tuple(violations)


@dataclass(frozen=True, slots=True)
class DiscoveredSkill:
    """One skill: its index entry now, its body when something asks.

    ``path`` rather than the text itself is the entire design. A field holding
    the body would be read by a repr, a serialisation, or an equality check,
    and the catalogue would quietly cost what loading every skill costs.
    """

    metadata: SkillMetadata
    path: Path
    metadata_tokens: int
    _body: list[str] = field(default_factory=list, compare=False, repr=False)

    @property
    def name(self) -> str:
        """Return the name this skill is selected by."""
        return self.metadata.name

    def body(self) -> str:
        """Return the methodology text, read from disk the first time it is asked for.

        Only the frontmatter is split off, not re-validated. The metadata was
        checked when the catalogue was built; re-checking it here would mean a
        turn that selected a skill could fail on a manifest problem the build
        had already passed, which is the worst possible moment to discover one.
        """
        if not self._body:
            text = self.path.read_text(encoding="utf-8")
            _, body = split_frontmatter(text, source=str(self.path))
            self._body.append(body)
        return self._body[0]


def load_skill(
    path: Path,
    *,
    counter: TokenCounter = estimate_tokens,
) -> DiscoveredSkill:
    """Return the skill declared at ``path``, with its body left on disk.

    The manifest is read once, here, to get the frontmatter — there is no way
    to learn a file's metadata without opening it. What does not happen is the
    body being retained, which is the part that costs.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SkillManifestError(f"{path}: could not be read: {error}") from error

    metadata, _ = parse_skill_manifest(text, source=str(path))

    return DiscoveredSkill(
        metadata=metadata,
        path=path,
        metadata_tokens=counter(metadata_text(metadata)),
    )


__all__ = [
    "DiscoveredSkill",
    "SkillManifestError",
    "body_violations",
    "load_skill",
    "parse_skill_manifest",
]
