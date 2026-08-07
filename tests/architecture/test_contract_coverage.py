"""Every rule in the architecture tier table has exactly one contract.

The tier table in the root ``AGENTS.md`` is where the boundaries are stated;
``.importlinter`` is where they are enforced. This module pins the two together
so neither can drift alone:

- each contract declares, verbatim, the line of the tier table it enforces, so
  editing the table without revisiting the contracts fails the build;
- the contract set and the declared rule set must match exactly, so adding a
  contract nobody can trace back to the table — or a table row nobody enforces —
  fails the build too.

One row is enforced by a guard script rather than by ``import-linter``: the
console is not an importable Python package, so there is nothing for a contract
to name. That row declares the script instead, and this module asserts the
script exists and that the gate runs it — the same standard, by a different
mechanism, rather than a row with nothing behind it.

The correspondence is declared rather than derived because two cells of the
table are prose ("tiers 1 and 2", "everything") and one row maps to two
contracts. A parser that guessed at those would be the thing most likely to rot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from contract_config import ARCHITECTURE_DOC, REPO_ROOT, declared_contracts

pytestmark = pytest.mark.architecture

TIER_TABLE_HEADER = "| Tier | Packages | May import | Must never import |"


@dataclass(frozen=True)
class ArchitectureRule:
    """A rule of the tier table, and what enforces it.

    Exactly one of ``contract`` and ``script`` is set. A rule with neither is a
    row nothing holds, which is the state this module exists to make impossible.
    """

    #: The ``.importlinter`` contract, for a rule about Python packages.
    contract: str = ""
    #: The line of the tier table this rule enforces, verbatim.
    excerpt: str = ""
    #: The guard script under ``tools/``, for a rule ``import-linter`` cannot
    #: express because the thing it is about is not an importable package.
    script: str = ""

    def __post_init__(self) -> None:
        if bool(self.contract) == bool(self.script):
            raise ValueError(
                f"{self.excerpt!r} must be enforced by exactly one of a contract and a script"
            )

    @property
    def name(self) -> str:
        """Return whichever of the two enforces this rule."""
        return self.contract or self.script


#: The Makefile target list the gate runs, read rather than restated: a script
#: that exists and is never run is the same as no script at all.
MAKEFILE = REPO_ROOT / "Makefile"


ARCHITECTURE_RULES = (
    ArchitectureRule(
        "layers",
        "Dependencies point downward only, and CI proves it.",
    ),
    ArchitectureRule(
        "config-is-a-leaf",
        "| 4 | `config` | — | everything |",
    ),
    ArchitectureRule(
        "integrations-below-capabilities",
        "| 2 | `integrations` | `core`, `platform`, `config` | "
        "`capabilities`, `surfaces`, `gateway` |",
    ),
    ArchitectureRule(
        "integrations-below-tier1",
        "| 2 | `integrations` | `core`, `platform`, `config` | "
        "`capabilities`, `surfaces`, `gateway` |",
    ),
    ArchitectureRule(
        "capabilities-below-tier1",
        "| 2 | `capabilities` | `integrations`, `core`, `platform`, `config` | "
        "`surfaces`, `gateway` |",
    ),
    ArchitectureRule(
        "tier1-peers-independent",
        "| 1 | `surfaces`, `gateway` | everything below | each other |",
    ),
    ArchitectureRule(
        "tier3-below-tier2",
        "| 3 | `core`, `platform` | `config`, and each other | tiers 1 and 2 |",
    ),
    ArchitectureRule(
        script="check_console_boundary.py",
        excerpt="| — | `console` | the REST API, over HTTP | every Python package |",
    ),
)

#: The rules ``import-linter`` enforces, which is what ``.importlinter`` must
#: contain exactly.
CONTRACT_RULES = tuple(rule for rule in ARCHITECTURE_RULES if rule.contract)

#: The rules a guard script enforces instead.
SCRIPT_RULES = tuple(rule for rule in ARCHITECTURE_RULES if rule.script)


def architecture_document() -> str:
    """Return the document holding the tier table."""
    return ARCHITECTURE_DOC.read_text(encoding="utf-8")


def tier_table_rows() -> tuple[str, ...]:
    """Return the body rows of the tier table."""
    lines = architecture_document().splitlines()
    header_index = lines.index(TIER_TABLE_HEADER)

    rows: list[str] = []
    # Skip the header and the `|---|` separator beneath it.
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(line.strip())

    return tuple(rows)


def test_contract_count_matches_the_tier_table() -> None:
    """One contract per declared rule, no more and no fewer."""
    declared = declared_contracts()
    enforced = tuple(rule.contract for rule in CONTRACT_RULES)

    assert len(declared) == len(enforced), (
        f".importlinter declares {len(declared)} contracts but the tier table "
        f"declares {len(enforced)} rules"
    )
    assert set(declared) == set(enforced)
    assert len(set(enforced)) == len(enforced), "a contract is claimed by two rules"


@pytest.mark.parametrize("rule", ARCHITECTURE_RULES, ids=lambda rule: rule.name)
def test_rule_quotes_the_architecture_document(rule: ArchitectureRule) -> None:
    """The quoted rule still exists, verbatim, where it is documented."""
    assert rule.excerpt in architecture_document(), (
        f"{rule.name} quotes a rule that is no longer in {ARCHITECTURE_DOC.name}: {rule.excerpt!r}"
    )


@pytest.mark.parametrize("rule", SCRIPT_RULES, ids=lambda rule: rule.script)
def test_a_script_enforced_rule_has_a_script_the_gate_runs(rule: ArchitectureRule) -> None:
    """A row enforced by a script needs the script, and needs `verify` to run it."""
    script: Path = REPO_ROOT / "tools" / rule.script
    assert script.is_file(), f"{rule.excerpt} names {script}, which does not exist"

    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert f"tools/{rule.script}" in makefile, (
        f"{rule.script} is not run by any Makefile target, so the row it enforces is a "
        f"row nothing holds"
    )
    verify = makefile.split("verify:", 1)[1].split("## The single quality gate")[0]
    assert "check-console-boundary" in verify, "`verify` does not run the console boundary check"


def test_every_tier_table_row_is_enforced() -> None:
    """A row cannot be added to the tier table without a contract to enforce it."""
    quoted = {rule.excerpt for rule in ARCHITECTURE_RULES}
    unenforced = [row for row in tier_table_rows() if row not in quoted]

    assert not unenforced, f"tier table rows with no import contract: {unenforced}"
