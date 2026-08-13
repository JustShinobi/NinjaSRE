"""The fields a node can be edited by, described by the schema that validates them.

An editor needs four things per field — what type it is, what range it accepts,
what it defaults to, and what it is for — and there is exactly one place in this
deployment that already knows all four: the Pydantic sections configuration is
validated against. Deriving the catalogue from them means a field added to the
schema is a control in the console on the same commit, and a control the console
offers is a field the write path will accept.

The alternative is a table of field descriptions written in the client. It
agrees with the schema on the day it is written and never again, and the
disagreement surfaces as a control that renders a number picker for a field the
deployment refuses.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from config.constants.investigation import MAX_INVESTIGATION_LOOPS
from platform.config_service.document import NodeDocument
from platform.config_service.effective import build
from platform.config_service.fields import declared_fields, fields_at
from platform.persistence.ports import ConfigNode, ConfigNodeKind

ORG = "acme"
TEAM = "payments"


def _by_path() -> dict[str, Any]:
    return {declared.path: declared for declared in declared_fields()}


def _chain(
    org: NodeDocument | None = None, team: NodeDocument | None = None
) -> tuple[ConfigNode, ...]:
    """Return a two-node chain carrying the given documents, root-first."""
    return (
        ConfigNode(
            node_id=ORG,
            kind=ConfigNodeKind.ORGANISATION,
            name="Acme",
            parent_id=None,
            values=(org or NodeDocument()).to_values(),
        ),
        ConfigNode(
            node_id=TEAM,
            kind=ConfigNodeKind.TEAM,
            name="Payments",
            parent_id=ORG,
            values=(team or NodeDocument()).to_values(),
        ),
    )


# --- What the schema declares -------------------------------------------------


def test_every_declared_field_is_named_by_the_dotted_path_the_rest_of_the_package_uses() -> None:
    paths = {declared.path for declared in declared_fields()}

    assert "agents.tool_budget" in paths
    assert "policies.masking.level" in paths


def test_a_bounded_integer_carries_its_type_its_range_and_its_default() -> None:
    budget = _by_path()["agents.max_iterations"]

    assert budget.type == "integer"
    assert budget.minimum == 1
    assert budget.maximum == MAX_INVESTIGATION_LOOPS
    assert budget.default == MAX_INVESTIGATION_LOOPS


def test_a_closed_set_of_values_is_reported_as_one() -> None:
    level = _by_path()["policies.guardrails.mode"]

    assert level.allowed_values is not None
    assert "enforcing" in level.allowed_values


def test_a_list_is_a_leaf_because_that_is_what_the_merge_says_it_is() -> None:
    # Lists replace entirely rather than merging, so an editor that offered to
    # edit one entry would be offering an operation the write path does not have.
    capabilities = _by_path()["capabilities.enabled"]

    assert capabilities.type == "array"


def test_a_section_carries_the_summary_the_fields_under_it_are_read_with() -> None:
    budget = _by_path()["agents.tool_budget"]

    assert budget.section == "agents"
    assert budget.section_summary != ""


# -- the text an operator actually reads ---------------------------------------
#
# ``description`` and ``section_summary`` are the schema's own docstrings, and
# they are written for whoever is reviewing the schema: they cite the documents
# a decision came from, name the module that implements it, and run to eight
# lines. That is the right text to have next to the code and the wrong text to
# put under a form control, so the schema declares a second, short one beside
# it. ``help`` and ``section_help`` are what a form shows.


def _all_declared() -> tuple[Any, ...]:
    """Return every field in the catalogue, entry fields included."""
    collected: list[Any] = []
    for declared in declared_fields():
        collected.append(declared)
        collected.extend(declared.item_fields)
    return tuple(collected)


#: What must never reach an operator. Each one has been in the rendered form at
#: least once, arriving from a docstring nobody wrote for a reader outside this
#: repository.
_LEAKS: tuple[tuple[str, str], ...] = (
    (r"FR-\d+", "a requirement identifier"),
    (r"\bArticle\s+[IVX]+\b", "a constitution article"),
    (r"[\w/]+\.py\b", "a source path"),
    (r"``", "unrendered reStructuredText markup"),
)


def test_every_section_carries_help_written_for_the_operator_filling_the_form() -> None:
    missing = sorted(
        {declared.section for declared in declared_fields() if not declared.section_help.strip()}
    )

    assert missing == []


def test_every_entry_section_carries_help_too() -> None:
    # An entry of a list of objects is a form of its own, and it is drawn from
    # the same catalogue: a row of controls with no heading text is the same
    # defect one level down.
    missing = sorted(
        {
            declared.path
            for declared in declared_fields()
            for item in declared.item_fields
            if not item.section_help.strip()
        }
    )

    assert missing == []


@pytest.mark.parametrize(("pattern", "what"), _LEAKS)
def test_no_help_text_carries_what_only_this_repository_can_read(pattern: str, what: str) -> None:
    offenders = [
        f"{declared.path}: {text}"
        for declared in _all_declared()
        for text in (declared.help, declared.section_help)
        if re.search(pattern, text)
    ]

    assert offenders == [], f"help text carrying {what}"


def test_a_field_declares_its_own_help_beside_the_field_it_describes() -> None:
    # Declared in the schema rather than in a table keyed by path: a table is
    # the thing this module is built not to be, and it would drift the day a
    # field is renamed.
    budget = _by_path()["agents.tool_budget"]

    assert budget.help.strip() != ""
    assert budget.help != budget.section_help


def test_the_long_docstring_stays_where_the_code_can_read_it() -> None:
    # The short text is an addition, not a replacement: the rationale is still
    # the section's summary, for whoever is reading the schema.
    budget = _by_path()["agents.tool_budget"]

    assert budget.section_summary != ""
    assert budget.section_summary != budget.section_help


def test_no_field_is_declared_twice() -> None:
    paths = [declared.path for declared in declared_fields()]

    assert len(paths) == len(set(paths))


def test_the_catalogue_is_the_same_on_every_call() -> None:
    # It is derived rather than stored, so "derived once, consistently" is a
    # property worth pinning: a client caches it, and a set that reordered
    # between two requests would reorder the form under somebody's cursor.
    assert declared_fields() == declared_fields()


# --- What the fields stand at, at one node ------------------------------------


def test_a_field_nobody_set_reports_its_default_and_no_provenance() -> None:
    chain = _chain()

    at = {each.field.path: each for each in fields_at(build(TEAM, chain), NodeDocument())}

    assert at["agents.tool_budget"].value is None
    assert at["agents.tool_budget"].provenance == ""
    assert at["agents.tool_budget"].set_here is False


def test_a_field_an_ancestor_set_is_attributed_to_it_and_is_not_set_here() -> None:
    chain = _chain(org=NodeDocument.of({"agents": {"tool_budget": 3}}))

    at = {each.field.path: each for each in fields_at(build(TEAM, chain), NodeDocument())}

    assert at["agents.tool_budget"].value == 3
    assert at["agents.tool_budget"].provenance == ORG
    assert at["agents.tool_budget"].set_here is False


def test_a_field_this_node_set_is_marked_set_here_which_is_what_offers_the_clear() -> None:
    team = NodeDocument.of({"agents": {"tool_budget": 9}})
    chain = _chain(org=NodeDocument.of({"agents": {"tool_budget": 3}}), team=team)

    at = {each.field.path: each for each in fields_at(build(TEAM, chain), team)}

    assert at["agents.tool_budget"].value == 9
    assert at["agents.tool_budget"].provenance == TEAM
    assert at["agents.tool_budget"].set_here is True


def test_a_locked_field_names_the_node_holding_the_lock() -> None:
    chain = _chain(
        org=NodeDocument.of(
            {"policies": {"masking": {"level": "standard"}}},
            locked=("policies.masking.level",),
        )
    )

    at = {each.field.path: each for each in fields_at(build(TEAM, chain), NodeDocument())}

    assert at["policies.masking.level"].locked_by == ORG


def test_an_approval_gated_field_says_so_before_anybody_edits_it() -> None:
    chain = _chain(org=NodeDocument.of({}, approval_gated=("agents.tool_budget",)))

    at = {each.field.path: each for each in fields_at(build(TEAM, chain), NodeDocument())}

    assert at["agents.tool_budget"].approval_gated is True


def test_a_policy_narrowing_a_ceiling_narrows_the_control_rather_than_the_schema() -> None:
    from platform.config_service.field_policy import FieldPolicy

    chain = _chain(
        org=NodeDocument.of({}, policies=(FieldPolicy(path="agents.max_iterations", max_value=4),))
    )

    at = {each.field.path: each for each in fields_at(build(TEAM, chain), NodeDocument())}

    assert at["agents.max_iterations"].maximum == 4


def test_a_policy_cannot_widen_a_ceiling_the_schema_declares() -> None:
    # The schema's bound is the deployment's; a node policy may only tighten it.
    # Widening here would render a control that offers a value the write refuses.
    from platform.config_service.field_policy import FieldPolicy

    chain = _chain(
        org=NodeDocument.of(
            {}, policies=(FieldPolicy(path="agents.max_iterations", max_value=9_000),)
        )
    )

    at = {each.field.path: each for each in fields_at(build(TEAM, chain), NodeDocument())}

    assert at["agents.max_iterations"].maximum == MAX_INVESTIGATION_LOOPS


def test_a_policy_narrowing_the_allowed_values_intersects_rather_than_replaces() -> None:
    from platform.config_service.field_policy import FieldPolicy

    chain = _chain(
        org=NodeDocument.of(
            {},
            policies=(
                FieldPolicy(
                    path="policies.guardrails.mode", allowed_values=("enforcing", "not-a-mode")
                ),
            ),
        )
    )

    at = {each.field.path: each for each in fields_at(build(TEAM, chain), NodeDocument())}

    assert at["policies.guardrails.mode"].allowed_values == ("enforcing",)


def test_a_policy_is_the_closed_set_when_the_schema_declares_none() -> None:
    # A free string field with a policy naming what is acceptable becomes a
    # closed control. Nothing to intersect with, so the policy stands alone.
    from platform.config_service.field_policy import FieldPolicy

    chain = _chain(
        org=NodeDocument.of(
            {},
            policies=(
                FieldPolicy(path="policies.masking.level", allowed_values=("standard", "strict")),
            ),
        )
    )

    at = {each.field.path: each for each in fields_at(build(TEAM, chain), NodeDocument())}

    assert at["policies.masking.level"].allowed_values == ("standard", "strict")


def test_every_declared_field_appears_at_a_node_exactly_once() -> None:
    chain = _chain()

    at = [each.field.path for each in fields_at(build(TEAM, chain), NodeDocument())]

    assert at == [declared.path for declared in declared_fields()]


@pytest.mark.parametrize("path", ["agents.prompts.investigator", "integrations.active"])
def test_the_catalogue_reaches_into_nested_sections(path: str) -> None:
    assert path in _by_path()


# -- an ordered list of objects ------------------------------------------------
#
# A list of *scalars* is a leaf and stays one: it replaces entirely, and there
# is nothing inside an entry to draw. A list of *objects* is different in the
# one way that matters to an editor — each entry has named, typed fields — and
# an editor with no description of them has two choices, both bad: refuse to
# edit the field at all, which is where the console was, or hold its own table
# of what a routing rule looks like, which is the client-side schema this whole
# module exists to avoid.


def test_a_list_of_objects_describes_the_fields_one_entry_has() -> None:
    rules = _by_path()["transit.rules"]

    assert rules.type == "array"
    assert {item.path for item in rules.item_fields} >= {"team", "action", "reason"}


def test_an_entrys_field_carries_its_own_type_and_closed_set() -> None:
    rules = _by_path()["transit.rules"]
    action = next(item for item in rules.item_fields if item.path == "action")

    assert action.type == "string"
    assert action.allowed_values is not None
    assert "investigate" in action.allowed_values


def test_an_entrys_path_is_relative_because_its_index_is_not_known_yet() -> None:
    """A new entry has no index, so an absolute path would name a row nobody added."""
    rules = _by_path()["transit.rules"]

    assert all("." not in item.path for item in rules.item_fields)


def test_a_list_of_scalars_describes_no_entry_fields() -> None:
    """Nothing inside a string to draw; offering an empty row editor would be a lie."""
    capabilities = _by_path()["capabilities.enabled"]

    assert capabilities.item_fields == ()


def test_the_specialists_a_team_declares_are_an_ordered_list_of_objects_too() -> None:
    subagents = _by_path()["agents.subagents"]

    assert subagents.type == "array"
    assert {item.path for item in subagents.item_fields} >= {"name", "system_prompt"}
