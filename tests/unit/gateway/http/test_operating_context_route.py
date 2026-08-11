"""The operating context over HTTP: what applies, where it came from, what it becomes.

Three of the four things this route serves cannot be assembled by a client at
all — the ancestors' documents, the deployment's own prompt assembly, and what
its estate has discovered — and the fourth, the token cost, must not be, because
a console counting tokens its own way would show a budget the write path
disagrees with.

The assertion that carries acceptance 6 is the one on ``prompt``: it is the
exact string the next investigation will be sent, not a rendering of the parts.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from config.constants.agents import OPERATING_CONTEXT_TOKEN_BUDGET
from config.prompts.investigation import DEFAULT_RUNTIME_SYSTEM_PROMPT
from config.prompts.operating_context import (
    LXC_METRICS_FACT,
    TEMPLATE_SECTION_NETWORK,
    TEMPLATE_SECTION_PEOPLE,
    TEMPLATE_SECTION_SIGNALS,
    TEMPLATE_SECTION_WHAT_RUNS,
)
from platform.config_service.document import NodeDocument
from platform.estate.kinds import KIND_CONTAINER
from platform.identity.permissions import Role
from platform.persistence.ports.config_repository import ConfigNode
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    Deployment,
    issue_token,
)

pytestmark = pytest.mark.anyio

SEEN = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

MTU = "The vk8s zone runs MTU 1450 over a 1450 underlay, which fragments TLS handshakes."
ORG_SIGNALS = "Container metrics come from the host's own series, keyed by vmid."


async def _owner(deployment: Deployment) -> dict[str, str]:
    """Return the authorisation header of an organisation-wide owner."""
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=None
    )
    return {"authorization": f"Bearer {secret}"}


async def _store(deployment: Deployment, node_id: str, document: NodeDocument) -> None:
    """Put ``document`` on ``node_id``, whatever it held before."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        node = await uow.config.get(node_id)
        assert node is not None
        await uow.config.upsert(
            ConfigNode(
                node_id=node.node_id,
                kind=node.kind,
                name=node.name,
                parent_id=node.parent_id,
                values=document.to_values(),
                version=node.version,
            )
        )


def _context(**sections: str) -> NodeDocument:
    """Return a node document declaring ``sections`` as operating context."""
    return NodeDocument.of({"agents": {"operating_context": {"sections": dict(sections)}}})


async def _sweep(deployment: Deployment) -> None:
    """Put two guests in the estate, so the template has something to derive from."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        for vmid, address in ((100, "10.20.30.4"), (101, "10.20.30.5")):
            await uow.estate.upsert(
                Resource(
                    resource_id=f"prox-ct-{vmid}",
                    kind=KIND_CONTAINER,
                    source="proxmox",
                    native_id=f"lxc/HAL9000/2025-01-01/{vmid}",
                    display_name=f"guest-{vmid}",
                    attributes={"vmid": vmid, "address": address, "zone": "vk8s"},
                    last_seen_at=SEEN,
                )
            )


async def _read(client: AsyncClient, deployment: Deployment, node_id: str = TEAM_PAYMENTS) -> dict:
    """Return the operating-context document for ``node_id``."""
    answer = await client.get(
        f"/v1/config/{node_id}/operating-context", headers=await _owner(deployment)
    )
    assert answer.status_code == 200, answer.text
    body: dict = answer.json()
    return body


# --- What applies, and where each section came from ---------------------------


async def test_a_node_that_has_written_nothing_reports_no_sections(
    client: AsyncClient, deployment: Deployment
) -> None:
    body = await _read(client, deployment)

    assert body["sections"] == []
    assert body["context"] == ""
    assert body["prompt"] == DEFAULT_RUNTIME_SYSTEM_PROMPT


async def test_each_section_names_the_level_that_supplied_it(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Acceptance 2, over HTTP: two levels, and the response distinguishes them."""
    await _store(deployment, ORG, _context(signals=ORG_SIGNALS))
    await _store(deployment, TEAM_PAYMENTS, _context(network=MTU))

    body = await _read(client, deployment)

    provenance = {section["name"]: section["provenance"] for section in body["sections"]}
    assert provenance == {"signals": ORG, "network": TEAM_PAYMENTS}


async def test_a_section_a_team_overrode_reports_the_team(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _store(deployment, ORG, _context(network="The estate is flat."))
    await _store(deployment, TEAM_PAYMENTS, _context(network=MTU))

    body = await _read(client, deployment)

    section = next(entry for entry in body["sections"] if entry["name"] == "network")
    assert section["provenance"] == TEAM_PAYMENTS
    assert section["body"] == MTU


# --- Acceptance 6: the text the model will receive ----------------------------


async def test_the_prompt_is_the_whole_string_the_next_run_will_be_sent(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _store(deployment, TEAM_PAYMENTS, _context(network=MTU))

    body = await _read(client, deployment)

    assert body["prompt"].startswith(DEFAULT_RUNTIME_SYSTEM_PROMPT)
    assert MTU in body["prompt"]
    assert body["context"] in body["prompt"]


async def test_an_override_and_the_context_both_appear_in_the_preview(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _store(
        deployment,
        TEAM_PAYMENTS,
        NodeDocument.of(
            {
                "agents": {
                    "prompts": {"investigator": "Be terse."},
                    "operating_context": {"sections": {"network": MTU}},
                }
            }
        ),
    )

    body = await _read(client, deployment)

    assert body["prompt"].startswith("Be terse.")
    assert body["prompt"].index("Be terse.") < body["prompt"].index(MTU)


async def test_the_budget_and_what_it_has_spent_come_from_the_deployment(
    client: AsyncClient, deployment: Deployment
) -> None:
    """A console counting its own tokens would show a budget the write disagrees with."""
    await _store(deployment, TEAM_PAYMENTS, _context(network=MTU))

    body = await _read(client, deployment)

    assert body["token_budget"] == OPERATING_CONTEXT_TOKEN_BUDGET
    assert 0 < body["tokens_used"] <= OPERATING_CONTEXT_TOKEN_BUDGET


async def test_the_roles_the_context_reaches_are_served_rather_than_assumed(
    client: AsyncClient, deployment: Deployment
) -> None:
    body = await _read(client, deployment)

    assert body["roles"] == ["investigator", "subagent"]


# --- Acceptance 5: the derived template ---------------------------------------


async def test_a_node_with_nothing_written_is_offered_the_derived_template(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _sweep(deployment)

    body = await _read(client, deployment)

    template = {section["name"]: section["body"] for section in body["template"]}
    assert TEMPLATE_SECTION_WHAT_RUNS in template
    assert TEMPLATE_SECTION_PEOPLE in template


async def test_the_template_carries_the_zones_and_networks_the_estate_discovered(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _sweep(deployment)

    body = await _read(client, deployment)

    network = next(
        entry["body"] for entry in body["template"] if entry["name"] == TEMPLATE_SECTION_NETWORK
    )
    assert "vk8s — 10.20.30.0/24" in network


async def test_the_template_carries_the_signal_sources_and_the_container_fact(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _sweep(deployment)

    body = await _read(client, deployment)

    signals = next(
        entry["body"] for entry in body["template"] if entry["name"] == TEMPLATE_SECTION_SIGNALS
    )
    assert LXC_METRICS_FACT in signals


async def test_the_template_degrades_to_the_questions_when_nothing_was_swept(
    client: AsyncClient, deployment: Deployment
) -> None:
    """No estate is not no template: the questions are the half worth shipping."""
    body = await _read(client, deployment)

    names = [entry["name"] for entry in body["template"]]
    assert TEMPLATE_SECTION_WHAT_RUNS in names
    assert TEMPLATE_SECTION_PEOPLE in names


async def test_the_template_is_not_offered_once_anything_has_been_written(
    client: AsyncClient, deployment: Deployment
) -> None:
    """A suggestion that kept reappearing over somebody's own text is one they stop reading."""
    await _sweep(deployment)
    await _store(deployment, TEAM_PAYMENTS, _context(network=MTU))

    body = await _read(client, deployment)

    assert body["template"] == []


# --- Scope --------------------------------------------------------------------


async def test_a_team_scoped_caller_cannot_read_another_teams_context(
    client: AsyncClient, deployment: Deployment
) -> None:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="grace",
        role=Role.OWNER,
        node_id=TEAM_PAYMENTS,
    )

    answer = await client.get(
        "/v1/config/platform/operating-context",
        headers={"authorization": f"Bearer {secret}"},
    )

    assert answer.status_code == 404
