"""A resource's page says what has been written about it.

The join is already in the graph by the time this route runs; what this asserts
is that the page carries it, that it says *why* each document is there, and that
a deployment whose corpus is empty still renders — which is what every estate
looks like before the first sync.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from platform.identity.permissions import Role
from platform.knowledge.base.estate_links import HOST_LABEL_PREFIX, EstateLinker
from platform.knowledge.base.models import Document, DocumentType
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, Deployment, issue_token

pytestmark = pytest.mark.anyio

HOSTNAME = "adguard.example.invalid"

#: The team the seeded document belongs to. A document must carry one — an
#: unscoped document is one every team can retrieve.
TEAM = "team-platform"


async def _headers(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="u-owner", role=Role.OWNER, node_id=None
    )
    return {"authorization": f"Bearer {secret}"}


async def _seed(deployment: Deployment, *, link: bool = True) -> None:
    """Write one resource and, unless told not to, a document that names it."""
    now = datetime.now(UTC)
    scope = TenantScope(org_id=ORG)
    async with deployment.gateway.begin(scope) as uow:
        await uow.estate.upsert(
            Resource(
                resource_id="res-adguard",
                kind="container",
                source="proxmox",
                native_id="lxc/115",
                display_name="adguard",
                labels=(f"{HOST_LABEL_PREFIX}{HOSTNAME}",),
                first_seen_at=now,
                last_seen_at=now,
            )
        )
    if not link:
        return

    await EstateLinker(gateway=deployment.gateway, scope=scope).link(
        (
            Document(
                document_id="corpus:docs/runbooks/adguard-dns-recovery.md",
                org_id=ORG,
                team_node_id=TEAM,
                title="Recovering AdGuard DNS",
                body=f"When {HOSTNAME} stops answering queries.",
                document_type=DocumentType.RUNBOOK,
                source_uri="docs/runbooks/adguard-dns-recovery.md",
                updated_at=now,
            ),
        )
    )


async def test_the_detail_lists_the_documents_that_mention_this_resource(
    deployment: Deployment, client: AsyncClient
) -> None:
    await _seed(deployment)

    response = await client.get(
        "/v1/estate/resources/res-adguard", headers=await _headers(deployment)
    )

    assert response.status_code == 200
    assert response.json()["documents"] == [
        {
            "document_id": "corpus:docs/runbooks/adguard-dns-recovery.md",
            "title": "Recovering AdGuard DNS",
            "location": "docs/runbooks/adguard-dns-recovery.md",
            "document_type": "runbook",
            "matched": HOSTNAME,
            "matched_on": "hostname",
        }
    ]


async def test_the_entry_says_which_name_put_it_there(
    deployment: Deployment, client: AsyncClient
) -> None:
    # An operator who can see *why* a document is attached can dismiss one that
    # is attached wrongly. Without it the panel is a list to be trusted whole.
    await _seed(deployment)

    response = await client.get(
        "/v1/estate/resources/res-adguard", headers=await _headers(deployment)
    )

    entry = response.json()["documents"][0]
    assert entry["matched"] == HOSTNAME
    assert entry["matched_on"] == "hostname"


async def test_a_resource_nobody_has_written_about_renders_with_an_empty_list(
    deployment: Deployment, client: AsyncClient
) -> None:
    await _seed(deployment, link=False)

    response = await client.get(
        "/v1/estate/resources/res-adguard", headers=await _headers(deployment)
    )

    assert response.status_code == 200
    assert response.json()["documents"] == []
