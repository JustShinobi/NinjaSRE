"""A resource's page says what changed underneath it, and how strongly.

The fourth quarter of a resource's detail — its signals, the documents that name
it, the investigations that touched it, and this. It is served from the same
correlation the agent's own capability uses rather than from a second rule,
because two rules would disagree the day somebody changed one, and the console
would then be showing a link the report does not make.

What is asserted here is the part a route can get wrong: that the strength
travels with each entry, that a change nothing connects to the resource is
labelled rather than hidden, and that a deployment with no change source says so
instead of rendering an empty panel that reads as "nothing has changed".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from config.constants.changes import MAX_CHANGES_PER_WINDOW
from platform.changes.models import Change, ChangeWindow
from platform.identity.permissions import Role
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, Deployment, issue_token

pytestmark = pytest.mark.anyio

CORRELATION_KEY = "hal9000/lxc/115"


@dataclass(slots=True)
class RecordedSource:
    """The apply record of a cluster, without the cluster."""

    name: str = "infra_apply"
    answers: tuple[Change, ...] = ()
    managed: dict[str, tuple[str, ...]] = field(default_factory=dict)

    async def changes_in(
        self,
        window: ChangeWindow,
        *,
        limit: int = MAX_CHANGES_PER_WINDOW,
    ) -> Sequence[Change]:
        """Return the recorded changes inside ``window``."""
        return tuple(change for change in self.answers if window.contains(change.instant))[:limit]

    def components(self) -> dict[str, tuple[str, ...]]:
        """Return what each component manages."""
        return self.managed


def _change(change_id: str, *, component: str, path: str, minutes: int) -> Change:
    now = datetime.now(UTC)
    return Change(
        change_id=change_id,
        occurred_at=now - timedelta(minutes=minutes + 6),
        author="erik",
        message=f"feat({component}): something",
        paths=(path,),
        source="infra_apply",
        component=component,
        applied_at=now - timedelta(minutes=minutes),
    )


async def _headers(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="u-owner", role=Role.OWNER, node_id=None
    )
    return {"authorization": f"Bearer {secret}"}


async def _seed(deployment: Deployment, *, sources: Sequence[object]) -> None:
    """Write the container, and point the deployment at ``sources``."""
    now = datetime.now(UTC)
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.estate.upsert(
            Resource(
                resource_id="res-mon",
                kind="container",
                source="proxmox",
                native_id="lxc/115",
                display_name="mon-prometheus",
                correlation_key=CORRELATION_KEY,
                attributes={"zone": "infra-zone"},
                first_seen_at=now,
                last_seen_at=now,
            )
        )
    deployment.state.change_sources = list(sources)


async def test_the_detail_lists_what_changed_under_this_resource(
    deployment: Deployment, client: AsyncClient
) -> None:
    await _seed(
        deployment,
        sources=[
            RecordedSource(
                answers=(
                    _change(
                        "9f2c1ab",
                        component="monitoring",
                        path="services/monitoring/stack/values.yaml",
                        minutes=13,
                    ),
                ),
                managed={"monitoring": (CORRELATION_KEY,)},
            )
        ],
    )

    response = await client.get("/v1/estate/resources/res-mon", headers=await _headers(deployment))

    assert response.status_code == 200
    assert response.json()["changes"]["entries"] == [
        {
            "change_id": "9f2c1ab",
            "author": "erik",
            "message": "feat(monitoring): something",
            "component": "monitoring",
            "applied": True,
            "instant": response.json()["changes"]["entries"][0]["instant"],
            "strength": "manages_resource",
            "temporal_only": False,
            "why": response.json()["changes"]["entries"][0]["why"],
            "paths": ["services/monitoring/stack/values.yaml"],
            "source": "infra_apply",
        }
    ]


async def test_a_change_that_only_shares_a_window_is_labelled_rather_than_hidden(
    deployment: Deployment, client: AsyncClient
) -> None:
    # Hidden, it cannot be ruled out by anybody reading the page. Unlabelled, it
    # is read as a cause. Labelled, it is what it is.
    await _seed(
        deployment,
        sources=[
            RecordedSource(
                answers=(
                    _change(
                        "b0c99fe",
                        component="storage",
                        path="services/storage/datastore/main.tf",
                        minutes=4,
                    ),
                ),
                managed={"monitoring": (CORRELATION_KEY,), "storage": ("hal9000/lxc/120",)},
            )
        ],
    )

    response = await client.get("/v1/estate/resources/res-mon", headers=await _headers(deployment))

    entry = response.json()["changes"]["entries"][0]
    assert entry["strength"] == "window_only"
    assert entry["temporal_only"] is True


async def test_the_panel_carries_the_sentence_a_quiet_resource_earns(
    deployment: Deployment, client: AsyncClient
) -> None:
    await _seed(deployment, sources=[RecordedSource(managed={"monitoring": ("hal9000/lxc/999",)})])

    response = await client.get("/v1/estate/resources/res-mon", headers=await _headers(deployment))

    changes = response.json()["changes"]
    assert changes["entries"] == []
    assert "No change of any kind" in changes["statement"]
    assert changes["sources"] == ["infra_apply"]
    assert changes["answered"] is True


async def test_a_deployment_with_no_change_source_says_so_rather_than_showing_an_empty_panel(
    deployment: Deployment, client: AsyncClient
) -> None:
    # An empty panel reads as "nothing has changed". A deployment nobody pointed
    # at a repository has not established that and must not appear to have.
    await _seed(deployment, sources=[])

    response = await client.get("/v1/estate/resources/res-mon", headers=await _headers(deployment))

    changes = response.json()["changes"]
    assert changes["answered"] is False
    assert "No change source is configured" in changes["statement"]


async def test_the_window_the_panel_covers_is_reported_with_it(
    deployment: Deployment, client: AsyncClient
) -> None:
    await _seed(deployment, sources=[RecordedSource()])

    response = await client.get("/v1/estate/resources/res-mon", headers=await _headers(deployment))

    assert response.json()["changes"]["window_hours"] == 24.0
