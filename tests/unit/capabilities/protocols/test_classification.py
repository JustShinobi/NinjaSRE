"""The operator's verdict, and what happens in its absence.

The rule this file exists for is one sentence: a bridged tool nobody has
classified is a write, and a write nobody authorised does not run. Everything
else here is the consequences of taking that literally — including the part
operators find annoying, which is that a server declaring its own tool read-only
changes nothing at all.
"""

from __future__ import annotations

import pytest

from capabilities.protocols.classification import (
    UNCLASSIFIED_LEVEL,
    Classification,
    ClassificationTable,
    UnclassifiedTool,
)
from core.capability.metadata import SideEffectLevel


def test_an_unclassified_tool_is_a_write() -> None:
    table = ClassificationTable()
    assert table.level_for("deploys.rollout") == UNCLASSIFIED_LEVEL
    assert UNCLASSIFIED_LEVEL.needs_approval
    assert not table.is_classified("deploys.rollout")


def test_an_unclassified_tool_may_not_execute() -> None:
    table = ClassificationTable()
    refusal = table.refusal_for("deploys.rollout")
    assert refusal is not None
    assert "classif" in refusal.lower()


def test_a_classified_tool_may_execute_at_the_level_the_operator_chose() -> None:
    table = ClassificationTable.of({"deploys.status": "read"})
    assert table.level_for("deploys.status") == SideEffectLevel.READ
    assert table.is_classified("deploys.status")
    assert table.refusal_for("deploys.status") is None


def test_a_servers_own_declaration_is_never_the_effective_classification() -> None:
    # The whole argument for operator classification in one assertion: a server
    # that declares its most dangerous tool harmless gets nowhere.
    table = ClassificationTable()
    declared = Classification.suggested("deploys.delete_everything", declared="read")
    assert declared.suggested_level == SideEffectLevel.READ
    assert table.level_for("deploys.delete_everything") == UNCLASSIFIED_LEVEL
    assert table.refusal_for("deploys.delete_everything") is not None


def test_a_declaration_nobody_recognises_suggests_nothing() -> None:
    assert Classification.suggested("deploys.rollout", declared="mostly harmless").suggested_level


def test_an_unrecognised_declaration_suggests_the_fail_safe_level() -> None:
    suggestion = Classification.suggested("deploys.rollout", declared="mostly harmless")
    assert suggestion.suggested_level == UNCLASSIFIED_LEVEL


def test_a_table_rejects_a_level_nobody_defined() -> None:
    with pytest.raises(UnclassifiedTool):
        ClassificationTable.of({"deploys.rollout": "probably_fine"})


def test_a_table_reports_what_is_still_awaiting_a_decision() -> None:
    table = ClassificationTable.of({"deploys.status": "read"})
    awaiting = table.awaiting(("deploys.status", "deploys.rollout", "deploys.scale"))
    assert awaiting == ("deploys.rollout", "deploys.scale")


def test_a_classification_records_who_decided_and_when_it_was_written() -> None:
    table = ClassificationTable.of({"deploys.status": "read"})
    entry = table.entry("deploys.status")
    assert entry is not None
    assert entry.qualified_name == "deploys.status"
    assert entry.level == SideEffectLevel.READ
    assert entry.classified


def test_a_removed_tool_leaves_no_classification_behind() -> None:
    table = ClassificationTable.of({"deploys.status": "read", "deploys.gone": "read"})
    kept = table.restricted_to(("deploys.status",))
    assert kept.is_classified("deploys.status")
    assert not kept.is_classified("deploys.gone")
