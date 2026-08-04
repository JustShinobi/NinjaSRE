"""Every rule in the architecture tier table has exactly one contract.

The tier table in the root ``AGENTS.md`` is where the boundaries are stated;
``.importlinter`` is where they are enforced. This module pins the two together
so neither can drift alone:

- each contract declares, verbatim, the line of the tier table it enforces, so
  editing the table without revisiting the contracts fails the build;
- the contract set and the declared rule set must match exactly, so adding a
  contract nobody can trace back to the table — or a table row nobody enforces —
  fails the build too.

The correspondence is declared rather than derived because two cells of the
table are prose ("tiers 1 and 2", "everything") and one row maps to two
contracts. A parser that guessed at those would be the thing most likely to rot.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from contract_config import ARCHITECTURE_DOC, declared_contracts

pytestmark = pytest.mark.architecture

TIER_TABLE_HEADER = "| Tier | Packages | May import | Must never import |"


@dataclass(frozen=True)
class ArchitectureRule:
    """A contract and the line of the tier table it exists to enforce."""

    contract: str
    excerpt: str


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
)


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
    enforced = tuple(rule.contract for rule in ARCHITECTURE_RULES)

    assert len(declared) == len(enforced), (
        f".importlinter declares {len(declared)} contracts but the tier table "
        f"declares {len(enforced)} rules"
    )
    assert set(declared) == set(enforced)
    assert len(set(enforced)) == len(enforced), "a contract is claimed by two rules"


@pytest.mark.parametrize("rule", ARCHITECTURE_RULES, ids=lambda rule: rule.contract)
def test_rule_quotes_the_architecture_document(rule: ArchitectureRule) -> None:
    """The quoted rule still exists, verbatim, where it is documented."""
    assert rule.excerpt in architecture_document(), (
        f"{rule.contract} quotes a rule that is no longer in "
        f"{ARCHITECTURE_DOC.name}: {rule.excerpt!r}"
    )


def test_every_tier_table_row_is_enforced() -> None:
    """A row cannot be added to the tier table without a contract to enforce it."""
    quoted = {rule.excerpt for rule in ARCHITECTURE_RULES}
    unenforced = [row for row in tier_table_rows() if row not in quoted]

    assert not unenforced, f"tier table rows with no import contract: {unenforced}"
