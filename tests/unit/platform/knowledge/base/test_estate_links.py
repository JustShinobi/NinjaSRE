"""A runbook about AdGuard and the container called ``adguard``, joined up.

They are the same thing seen from two sides, and until something writes the
join down an investigation of the resource has to know to go and search for the
document. The join is by fully-qualified name — the hostname a workload's tags
already carry, and the domain the enrichment already declares — because those
are the two things that appear in a document and identify exactly one resource.

**Not by display name.** Half the estate is called something like ``backup``,
and a document mentioning the word would attach itself to a resource it is not
about. A wrong edge is worse than a missing one: the missing one costs a search
and the wrong one costs an investigation reading the wrong runbook.

**The graph is where it lives.** "What touches what" is the topology's question
and the estate has no column for it. It is written as an edge from the resource
to the document, which is the direction the one edge-reading method on the port
walks — and it is excluded from every dependency traversal, because a document
in a blast radius is not a thing that can break.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform.knowledge.base.estate_links import (
    DOCUMENT_NODE_PREFIX,
    HOST_LABEL_PREFIX,
    EstateLinker,
    LinkedDocument,
    match_keys,
    mentioned_resources,
)
from platform.knowledge.base.models import Document, DocumentType
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.topology_graph import EdgeKind, TopologyNode

pytestmark = pytest.mark.unit

MOMENT = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def resource(
    resource_id: str,
    *,
    domain: str = "",
    labels: tuple[str, ...] = (),
    display_name: str = "",
) -> Resource:
    """Return one estate resource with the attributes enrichment gives it."""
    return Resource(
        resource_id=resource_id,
        kind="container",
        source="hypervisor",
        native_id=resource_id.rsplit(":", 1)[-1],
        display_name=display_name or resource_id.rsplit(":", 1)[-1],
        attributes={"domain": domain} if domain else {},
        labels=labels,
        last_seen_at=MOMENT,
    )


ADGUARD = resource(
    "hypervisor:115",
    domain="adguard.example.invalid",
    labels=(f"{HOST_LABEL_PREFIX}adguard.example.invalid", "zone:infra"),
    display_name="adguard",
)
BACKUP = resource(
    "hypervisor:210",
    labels=(f"{HOST_LABEL_PREFIX}backup.example.invalid",),
    display_name="backup",
)
NAMELESS = resource("hypervisor:900", display_name="scratch")


def document(document_id: str, body: str, scope: TenantScope) -> Document:
    """Return one ingested document."""
    return Document(
        document_id=document_id,
        org_id=scope.org_id,
        team_node_id=scope.team_node_id or "",
        title=document_id,
        body=body,
        document_type=DocumentType.RUNBOOK,
        source_uri=f"docs/runbooks/{document_id}.md",
        updated_at=MOMENT,
    )


class TestWhatCountsAsAMention:
    """Fully-qualified names, and nothing that could belong to two resources."""

    def test_a_resources_keys_are_its_host_labels_and_its_domain(self) -> None:
        both = resource(
            "hypervisor:300",
            domain="site.example.invalid",
            labels=(f"{HOST_LABEL_PREFIX}box.example.invalid",),
        )

        assert match_keys(both) == (
            ("box.example.invalid", "hostname"),
            ("site.example.invalid", "domain"),
        )

    def test_a_name_that_is_both_is_recorded_once_as_the_hostname(self) -> None:
        assert match_keys(ADGUARD) == (("adguard.example.invalid", "hostname"),)

    def test_a_resource_with_neither_has_no_keys(self) -> None:
        assert match_keys(NAMELESS) == ()

    def test_a_zone_label_is_not_a_name(self) -> None:
        assert "infra" not in dict(match_keys(ADGUARD))
        assert "zone:infra" not in dict(match_keys(ADGUARD))

    def test_a_document_naming_the_host_matches_it(self) -> None:
        body = "Resolve a name against host-adguard.example.invalid and wait."

        assert mentioned_resources(body, (ADGUARD, BACKUP)) == ("hypervisor:115",)

    def test_a_document_naming_the_domain_matches_it(self) -> None:
        body = "The site adguard.example.invalid stopped answering."

        assert mentioned_resources(body, (ADGUARD, BACKUP)) == ("hypervisor:115",)

    def test_a_document_naming_the_display_name_alone_matches_nothing(self) -> None:
        body = "Take a backup before the upgrade, then restore the backup."

        assert mentioned_resources(body, (ADGUARD, BACKUP)) == ()

    def test_a_longer_name_that_merely_contains_a_shorter_one_is_not_a_match(self) -> None:
        assert (
            mentioned_resources("The host not-adguard.example.invalid answers.", (ADGUARD,)) == ()
        )
        assert mentioned_resources("See adguard.example.invalid.example.", (ADGUARD,)) == ()

    def test_a_name_at_the_end_of_a_sentence_is_still_a_name(self) -> None:
        # The commonest way a hostname appears in prose, and the one a naive
        # boundary rule silently misses for the whole corpus.
        body = "Restart host-adguard.example.invalid."

        assert mentioned_resources(body, (ADGUARD,)) == ("hypervisor:115",)

    def test_two_hosts_in_one_domain_do_not_match_each_other(self) -> None:
        body = "Only backup.example.invalid is involved."

        assert mentioned_resources(body, (ADGUARD, BACKUP)) == ("hypervisor:210",)

    def test_the_order_is_the_estate_order_so_two_runs_agree(self) -> None:
        body = "Both adguard.example.invalid and backup.example.invalid are involved."

        assert mentioned_resources(body, (ADGUARD, BACKUP)) == ("hypervisor:115", "hypervisor:210")
        assert mentioned_resources(body, (BACKUP, ADGUARD)) == ("hypervisor:210", "hypervisor:115")


class TestWritingTheLinks:
    """One edge per mention, and none for a document that mentions nothing."""

    @pytest.fixture
    async def estate(self, gateway: PersistenceGateway, scope: TenantScope) -> None:
        async with gateway.begin(scope) as uow:
            for entry in (ADGUARD, BACKUP, NAMELESS):
                await uow.estate.upsert(entry)

    async def test_a_document_naming_a_resource_writes_one_edge(
        self, gateway: PersistenceGateway, scope: TenantScope, estate: None
    ) -> None:
        linker = EstateLinker(gateway=gateway, scope=scope)

        report = await linker.link(
            (document("adguard-recovery", "Restart host-adguard.example.invalid.", scope),)
        )

        assert report.linked == 1
        assert report.removed == 0
        found = await linker.documents_for("hypervisor:115")
        assert found == (
            LinkedDocument(
                document_id="adguard-recovery",
                title="adguard-recovery",
                location="docs/runbooks/adguard-recovery.md",
                document_type=DocumentType.RUNBOOK,
                matched="adguard.example.invalid",
                matched_on="hostname",
            ),
        )

    async def test_a_document_naming_nothing_writes_nothing(
        self, gateway: PersistenceGateway, scope: TenantScope, estate: None
    ) -> None:
        linker = EstateLinker(gateway=gateway, scope=scope)

        report = await linker.link((document("general", "Nothing in particular.", scope),))

        assert report.linked == 0
        assert await linker.documents_for("hypervisor:115") == ()
        assert await linker.documents_for("hypervisor:900") == ()

    async def test_running_it_twice_writes_the_same_graph(
        self, gateway: PersistenceGateway, scope: TenantScope, estate: None
    ) -> None:
        linker = EstateLinker(gateway=gateway, scope=scope)
        documents = (document("adguard-recovery", "host-adguard.example.invalid", scope),)

        first = await linker.link(documents)
        second = await linker.link(documents)

        assert (first.linked, first.removed) == (1, 0)
        assert (second.linked, second.removed) == (1, 0)
        assert len(await linker.documents_for("hypervisor:115")) == 1

    async def test_a_document_that_stops_naming_a_resource_loses_its_edge(
        self, gateway: PersistenceGateway, scope: TenantScope, estate: None
    ) -> None:
        linker = EstateLinker(gateway=gateway, scope=scope)
        await linker.link((document("moved", "host-adguard.example.invalid", scope),))

        report = await linker.link((document("moved", "It is about something else now.", scope),))

        assert report.removed == 1
        assert await linker.documents_for("hypervisor:115") == ()

    async def test_an_edge_written_by_a_corpus_this_run_did_not_see_is_left_alone(
        self, gateway: PersistenceGateway, scope: TenantScope, estate: None
    ) -> None:
        linker = EstateLinker(gateway=gateway, scope=scope)
        await linker.link((document("other-corpus", "host-adguard.example.invalid", scope),))

        report = await linker.link(
            (document("this-corpus", "host-adguard.example.invalid", scope),)
        )

        assert report.removed == 0
        assert {entry.document_id for entry in await linker.documents_for("hypervisor:115")} == {
            "other-corpus",
            "this-corpus",
        }


class TestWhatTheGraphHolds:
    """A document node, and an edge no dependency traversal walks."""

    @pytest.fixture
    async def linked(self, gateway: PersistenceGateway, scope: TenantScope) -> None:
        async with gateway.begin(scope) as uow:
            await uow.estate.upsert(ADGUARD)
        await EstateLinker(gateway=gateway, scope=scope).link(
            (document("adguard-recovery", "host-adguard.example.invalid", scope),)
        )

    async def test_the_edge_is_only_returned_when_it_is_asked_for_by_kind(
        self, gateway: PersistenceGateway, scope: TenantScope, linked: None
    ) -> None:
        async with gateway.begin(scope) as uow:
            dependencies = await uow.topology.edges_from("hypervisor:115")
            documents = await uow.topology.edges_from(
                "hypervisor:115", kinds=(EdgeKind.DOCUMENTED_BY,)
            )

        # Reconciliation reads the first of these and must not see a document
        # link, or it would treat one as a dependency somebody had drawn.
        assert dependencies == ()
        assert [edge.kind for edge in documents] == [EdgeKind.DOCUMENTED_BY]
        assert documents[0].to_node_id == f"{DOCUMENT_NODE_PREFIX}adguard-recovery"

    async def test_a_document_is_not_in_a_resources_blast_radius(
        self, gateway: PersistenceGateway, scope: TenantScope, linked: None
    ) -> None:
        # The whole reason this edge kind exists rather than reusing
        # ``depends_on``: a document cannot break, and an operator asking what
        # an outage reaches must not be handed a runbook.
        async with gateway.begin(scope) as uow:
            radius = await uow.topology.blast_radius("hypervisor:115")
            dependencies = await uow.topology.direct_dependencies("hypervisor:115")
            dependents = await uow.topology.direct_dependents(
                f"{DOCUMENT_NODE_PREFIX}adguard-recovery"
            )

        assert radius.reaches == ()
        assert dependencies.nodes == ()
        assert dependents.nodes == ()

    async def test_the_document_node_carries_what_the_document_is(
        self, gateway: PersistenceGateway, scope: TenantScope, linked: None
    ) -> None:
        async with gateway.begin(scope) as uow:
            # An upsert of a bare node merges over the stored one and returns
            # the result, which is how the node's own properties are read back.
            # Its ``kind`` is not: the port's merge takes the *given* kind when
            # it is set, and a bare node's is ``SERVICE``. What
            # ``NodeKind.DOCUMENT`` buys is that no traversal treats a document
            # as infrastructure, which the two assertions above establish.
            node = await uow.topology.upsert_node(
                TopologyNode(node_id=f"{DOCUMENT_NODE_PREFIX}adguard-recovery")
            )

        assert node.name == "adguard-recovery"
        assert node.properties["document_type"] == "runbook"
        assert node.properties["location"] == "docs/runbooks/adguard-recovery.md"
