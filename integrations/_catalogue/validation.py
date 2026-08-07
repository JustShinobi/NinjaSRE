"""The seven artefacts, checked at build time because the alternative is 03:00.

"Full parity" is either a property the build enforces or a word in a plan. This
module is the difference. It walks a vendor's package and the two directories
outside it that hold the rest, and reports which of the seven are there.

Each artefact prevents one specific failure, and the failure is in the message
because a contributor who is told "missing verifier.py" writes an empty file and
a contributor who is told what an absent verifier costs writes a verifier:

| Artefact | What its absence produces |
|---|---|
| `schema.py` | An operator guessing which fields the credential has |
| `verifier.py` | Discovering a wrong token during an incident |
| `client.py` | Ad-hoc HTTP with its own retry, its own errors, and its own bugs |
| `tools/` | An integration the agent cannot call |
| `SKILL.md` | An agent that knows the API and not the method |
| `docs.md` | Setup as tribal knowledge |
| scenario | An integration that rots, noticed by the investigation that needed it |

**Five of the seven live in the vendor's package and two do not.** The skill is
in ``capabilities/skills/`` and the scenario is in the synthetic harness, and
those two are exactly the ones a contributor forgets — which is the argument for
checking all seven in one place rather than letting each home directory check
its own.

The roots are parameters. A default computed from the repository layout would
work in this checkout and silently check nothing in another, and a parity check
that silently checks nothing is worse than no parity check: it reports success.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Artefact(StrEnum):
    """One of the seven things every integration ships (FR-001)."""

    SCHEMA = "schema.py"
    VERIFIER = "verifier.py"
    CLIENT = "client.py"
    TOOLS = "tools/"
    SKILL = "SKILL.md"
    DOCS = "docs.md"
    SCENARIO = "synthetic scenario"


class ParityStatus(StrEnum):
    """Whether an integration ships everything it is required to."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


#: What each absence costs, written into the failure so the message says why the
#: file is wanted rather than only that it is missing.
_COSTS: dict[Artefact, str] = {
    Artefact.SCHEMA: (
        "nothing declares what this vendor's credential is made of, so an operator "
        "configuring it is guessing at field names"
    ),
    Artefact.VERIFIER: (
        "nothing can check the credential before it is needed, so a wrong token is "
        "discovered during an incident"
    ),
    Artefact.CLIENT: (
        "there is no client on the shared base, so any call this integration makes has "
        "its own retry, its own error handling, and its own way past the proxy"
    ),
    Artefact.TOOLS: (
        "the integration declares no capability, so the agent cannot call it and nothing "
        "in an investigation can reach this vendor"
    ),
    Artefact.SKILL: (
        "there is no methodology, so the agent knows this vendor's API and not how to "
        "investigate with it"
    ),
    Artefact.DOCS: (
        "setup is tribal knowledge, and the third team to configure this integration will "
        "configure it wrongly"
    ),
    Artefact.SCENARIO: (
        "nothing exercises this integration end to end, so it rots quietly and the first "
        "to notice is the investigation that needed it"
    ),
}

#: A directory holding only these is not a tools package. A scaffolded
#: ``__init__`` is a placeholder, and counting it as an artefact would let an
#: integration reach parity while declaring nothing the agent can call.
_TOOLS_PLACEHOLDERS: frozenset[str] = frozenset({"__init__.py", "__pycache__"})


@dataclass(frozen=True, slots=True)
class ParityReport:
    """Which of the seven artefacts one integration has, and where they are."""

    integration: str
    present: tuple[Artefact, ...]
    missing: tuple[Artefact, ...]
    docs_path: Path | None = None
    skill_path: Path | None = None
    scenario_path: Path | None = None

    @property
    def status(self) -> ParityStatus:
        """Return whether this integration ships everything it is required to."""
        return ParityStatus.INCOMPLETE if self.missing else ParityStatus.COMPLETE

    def failure_message(self) -> str:
        """Return the build failure, naming the integration and each artefact (FR-002)."""
        if not self.missing:
            return ""
        lines = [f"{self.integration} is not at parity — {len(self.missing)} artefact(s) missing:"]
        lines.extend(
            f"  {artefact.value}: without it, {_COSTS[artefact]}" for artefact in self.missing
        )
        return "\n".join(lines)


class ParityError(Exception):
    """One or more integrations are incomplete, with every omission attached.

    Collected rather than raised one at a time. Fixing six omissions over six
    build runs is how a contributor learns to dread the gate; seeing all six at
    once is how they fix them in one pass.
    """

    def __init__(self, reports: Sequence[ParityReport]) -> None:
        self.reports = tuple(reports)
        super().__init__(
            f"{len(self.reports)} integration(s) are not at full parity:\n"
            + "\n".join(report.failure_message() for report in self.reports)
        )


def parity_of(
    integration: str,
    *,
    package_root: Path,
    skill_root: Path,
    scenario_root: Path,
) -> ParityReport:
    """Return which of the seven artefacts ``integration`` ships.

    ``package_root`` is the directory holding the vendor packages,
    ``skill_root`` the directory holding the methodology skills, and
    ``scenario_root`` the directory holding the synthetic scenarios. All three
    are required rather than defaulted; see the module docstring.
    """
    package = package_root / integration
    docs = package / Artefact.DOCS.value
    skill = skill_root / integration / Artefact.SKILL.value
    scenario = scenario_root / f"{integration}.py"

    found: dict[Artefact, bool] = {
        Artefact.SCHEMA: (package / Artefact.SCHEMA.value).is_file(),
        Artefact.VERIFIER: (package / Artefact.VERIFIER.value).is_file(),
        Artefact.CLIENT: (package / Artefact.CLIENT.value).is_file(),
        Artefact.TOOLS: _declares_tools(package / "tools"),
        Artefact.SKILL: skill.is_file(),
        Artefact.DOCS: docs.is_file(),
        Artefact.SCENARIO: scenario.is_file(),
    }

    return ParityReport(
        integration=integration,
        present=tuple(artefact for artefact in Artefact if found[artefact]),
        missing=tuple(artefact for artefact in Artefact if not found[artefact]),
        docs_path=docs if found[Artefact.DOCS] else None,
        skill_path=skill if found[Artefact.SKILL] else None,
        scenario_path=scenario if found[Artefact.SCENARIO] else None,
    )


def validate_parity(reports: Iterable[ParityReport]) -> None:
    """Raise ``ParityError`` naming every integration and artefact that is missing."""
    incomplete = [report for report in reports if report.missing]
    if incomplete:
        raise ParityError(incomplete)


def artefacts() -> tuple[Artefact, ...]:
    """Return the seven, in the order a contributor writes them."""
    return tuple(Artefact)


def cost_of(artefact: Artefact) -> str:
    """Return what this artefact's absence produces, for a message or a document."""
    return _COSTS[artefact]


def _declares_tools(directory: Path) -> bool:
    """Return whether ``directory`` is a tools package with something in it."""
    if not directory.is_dir():
        return False
    return any(
        entry.name not in _TOOLS_PLACEHOLDERS and entry.suffix == ".py"
        for entry in directory.iterdir()
    )


__all__ = [
    "Artefact",
    "ParityError",
    "ParityReport",
    "ParityStatus",
    "artefacts",
    "cost_of",
    "parity_of",
    "validate_parity",
]
