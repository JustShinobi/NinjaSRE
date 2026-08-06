"""Where cuts fall, what overlaps, and what a malformed hierarchy costs.

The chunker's job is to avoid one failure: a passage that changes meaning once
it is separated from what surrounded it. So the assertions here are about
*boundaries* — that a chunk never spans a heading, that a sentence spanning a cut
survives whole somewhere, and that a section is on every chunk so a retrieved
passage can name where it came from.

The tree's job is smaller and its invariant is absolute: every document appears
exactly once, whatever its ``parent_id`` says. A cycle, a missing parent, and a
tree fifteen levels deep each cost the shape. None of them may cost a document,
because a document nobody can see is one nobody can fix.
"""

from __future__ import annotations

import pytest

from config.constants.knowledge import MAX_KNOWLEDGE_TREE_DEPTH
from platform.knowledge.base.chunking import chunk_document, line_at, section_at, sections
from platform.knowledge.base.models import Document, DocumentType
from platform.knowledge.base.tree import KnowledgeTree, build_tree, flatten
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.knowledge.conftest import PAYMENTS_TEAM, PRIMARY_ORG, SEARCH_TEAM

pytestmark = pytest.mark.unit

RUNBOOK = """# Payments recovery

The service is considered down when the readiness probe fails on every replica.

## Diagnosis

Check the deployment's last state before anything else.

## Recovery

If the replica lag is above ten seconds, fail over to the standby.
Otherwise restart the deployment and wait for readiness.
"""


def document(
    document_id: str,
    *,
    title: str = "",
    parent: str = "",
    team: str = PAYMENTS_TEAM,
    body: str = "body",
) -> Document:
    """Return a document in the payments team unless told otherwise."""
    return Document(
        document_id=document_id,
        org_id=PRIMARY_ORG,
        team_node_id=team,
        title=title or document_id,
        body=body,
        parent_id=parent,
        document_type=DocumentType.RUNBOOK,
    )


# --- Chunking -----------------------------------------------------------------


def test_sections_span_the_whole_document_and_carry_a_breadcrumb() -> None:
    found = sections(RUNBOOK)

    assert [section.title for section in found] == [
        "Payments recovery",
        "Diagnosis",
        "Recovery",
    ]
    assert found[-1].path == "Payments recovery > Recovery"
    assert found[-1].end == len(RUNBOOK)


def test_a_document_with_no_headings_is_one_section() -> None:
    # The common case for a page exported from a wiki that keeps its title
    # outside the body.
    found = sections("Just some prose about the payments service.\n")

    assert len(found) == 1
    assert found[0].title == ""


def test_a_chunk_never_spans_a_heading() -> None:
    """A heading is the author's own statement that the subject changed."""
    chunks = chunk_document(RUNBOOK)

    assert {chunk.section for chunk in chunks} == {
        "Payments recovery",
        "Payments recovery > Diagnosis",
        "Payments recovery > Recovery",
    }
    for chunk in chunks:
        assert "##" not in chunk.text


def test_every_chunk_can_be_found_back_in_the_source() -> None:
    # The offsets are what let a rejected document report where its secret was,
    # and what lets a console show a passage in place.
    for chunk in chunk_document(RUNBOOK):
        assert RUNBOOK[chunk.start : chunk.end] == chunk.text


def test_a_sentence_spanning_a_cut_survives_whole_in_one_chunk() -> None:
    """The whole reason overlap exists.

    A condition in one chunk and its consequence in the next is how a
    conditional instruction becomes an unconditional one.
    """
    body = "# Recovery\n\n" + "\n\n".join(f"Step {index}: do the thing." for index in range(40))
    chunks = chunk_document(body, max_chars=200, overlap=60, minimum=40)

    assert len(chunks) > 1
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert later.start < earlier.end, "consecutive chunks must overlap"


def test_a_paragraph_larger_than_the_budget_is_split_rather_than_dropped() -> None:
    body = "# Trace\n\n" + ("x" * 5_000)
    chunks = chunk_document(body, max_chars=500, overlap=50, minimum=100)

    assert len(chunks) >= 10
    assert all(len(chunk.text) <= 500 for chunk in chunks)
    assert all(chunk.section == "Trace" for chunk in chunks)


def test_a_trailing_fragment_is_folded_into_what_precedes_it() -> None:
    # A twelve-character chunk matches everything weakly and nothing well, and
    # it costs a retrieval slot to say so.
    body = "# Notes\n\n" + ("word " * 100) + "\n\nend."
    chunks = chunk_document(body, max_chars=600, overlap=50, minimum=200)

    assert chunks[-1].text.endswith("end.")
    assert len(chunks[-1].text) > 200


def test_an_overlap_as_wide_as_the_budget_is_refused() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_document(RUNBOOK, max_chars=100, overlap=100)


def test_a_location_names_the_nearest_heading_and_the_line() -> None:
    offset = RUNBOOK.index("fail over")

    assert section_at(RUNBOOK, offset).title == "Recovery"
    assert line_at(RUNBOOK, offset) == 11


# --- The tree -----------------------------------------------------------------


def test_a_hierarchy_is_built_from_the_documents_own_parents() -> None:
    forest = build_tree(
        [
            document("root", title="Payments"),
            document("child", title="Recovery", parent="root"),
            document("grandchild", title="Failover", parent="child"),
        ]
    )

    assert [node.document_id for node in forest] == ["root"]
    assert [(doc.document_id, depth) for doc, depth in flatten(forest)] == [
        ("root", 0),
        ("child", 1),
        ("grandchild", 2),
    ]


def test_a_document_whose_parent_is_missing_becomes_a_root_rather_than_vanishing() -> None:
    forest = build_tree([document("orphan", parent="a-document-nobody-holds")])

    assert [node.document_id for node in forest] == ["orphan"]


def test_a_parent_in_another_team_does_not_pull_a_document_out_of_the_listing() -> None:
    forest = build_tree(
        [
            document("ours", parent="theirs"),
            document("theirs", team=SEARCH_TEAM),
        ]
    )

    assert {node.document_id for node in forest} == {"ours", "theirs"}


def test_a_cycle_is_broken_and_every_member_is_still_listed() -> None:
    forest = build_tree(
        [
            document("a", parent="b"),
            document("b", parent="a"),
        ]
    )

    assert {node.document_id for node in forest} == {"a", "b"}


def test_a_tree_deeper_than_the_bound_keeps_every_document() -> None:
    chain = [document("d0")]
    chain.extend(
        document(f"d{index}", parent=f"d{index - 1}")
        for index in range(1, MAX_KNOWLEDGE_TREE_DEPTH + 4)
    )

    forest = build_tree(chain)

    assert len(flatten(forest)) == len(chain)


async def test_the_listing_is_scoped_to_one_team(
    gateway: PersistenceGateway, scope: TenantScope, other_team_scope: TenantScope
) -> None:
    """FR-025: a team's listing shows that team's documents."""
    async with gateway.begin(scope) as uow:
        await uow.knowledge.upsert_document(document("ours").to_stored())
        await uow.knowledge.upsert_document(document("theirs", team=SEARCH_TEAM).to_stored())

    ours = await KnowledgeTree(gateway=gateway, scope=scope).documents()
    theirs = await KnowledgeTree(gateway=gateway, scope=other_team_scope).documents()

    assert [item.document_id for item in ours] == ["ours"]
    assert [item.document_id for item in theirs] == ["theirs"]


async def test_filing_a_document_under_its_own_descendant_is_refused(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A cycle from a sync adapter is survivable; an operator creating one
    # deliberately has made a mistake worth reporting as they make it.
    async with gateway.begin(scope) as uow:
        await uow.knowledge.upsert_document(document("root").to_stored())
        await uow.knowledge.upsert_document(document("child", parent="root").to_stored())

    tree = KnowledgeTree(gateway=gateway, scope=scope)

    with pytest.raises(ValueError, match="own ancestor"):
        await tree.place("root", "child")


async def test_a_document_can_be_moved_in_the_hierarchy(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.knowledge.upsert_document(document("root").to_stored())
        await uow.knowledge.upsert_document(document("loose").to_stored())

    tree = KnowledgeTree(gateway=gateway, scope=scope)
    moved = await tree.place("loose", "root")

    assert moved.parent_id == "root"
    forest = await tree.tree()
    assert [node.document_id for node in forest] == ["root"]
    assert [child.document_id for child in forest[0].children] == ["loose"]
