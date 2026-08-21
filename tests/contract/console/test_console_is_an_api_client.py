"""The console driven against the real API, over ASGI, with real issued tokens.

Nothing here is a fake standing in for the boundary being proven. The gateway is
the real ``create_app``, the persistence is the same ``PersistenceGateway``
protocol Postgres implements, the tokens are issued by the real ``TokenService``
and checked by the real permission guard — and the console is the real console,
reaching all of it through its own transport.

That is what makes these assertions worth making. A preview that matched a
mocked server would prove nothing about SC-005; a role matrix against a fake
permission table would prove nothing about SC-004.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.config_service.document import NodeDocument
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.transaction import TenantScope
from surfaces.console.app import Console, patch_of
from surfaces.console.client import ConsoleApiError, ConsoleClient, Response
from surfaces.console.pages import catalogue as catalogue_page
from surfaces.console.pages.config import preview_panel
from surfaces.console.pages.shell import PageContext
from surfaces.console.permissions import write_actions_in
from surfaces.console.session import sign_in
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    TEAM_PLATFORM,
    Deployment,
    FakeInvestigationRunner,
    issue_token,
)

pytestmark = pytest.mark.anyio

API_BASE = "https://api.acme.test"


@dataclass(frozen=True, slots=True)
class AsgiTransport:
    """The console's transport, wired straight into the real application."""

    client: AsyncClient

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        answer = await self.client.request(
            method, path, json=dict(body) if body is not None else None, headers=dict(headers or {})
        )
        try:
            document = answer.json()
        except ValueError:
            document = {}
        return Response(
            status=answer.status_code,
            body=document if isinstance(document, dict) else {},
            text=answer.text,
            headers=dict(answer.headers),
        )


@pytest.fixture
async def deployment() -> Deployment:
    """Return a wired gateway with an organisation and two teams."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        for team in (TEAM_PAYMENTS, TEAM_PLATFORM):
            await uow.config.upsert(
                ConfigNode(node_id=team, kind=ConfigNodeKind.TEAM, name=team, parent_id=ORG)
            )
    tokens = TokenService(gateway=gateway)
    runner = FakeInvestigationRunner()
    return Deployment(
        gateway=gateway,
        tokens=tokens,
        state=GatewayState(gateway=gateway, tokens=tokens, investigator=runner),
        runner=runner,
    )


@pytest.fixture
async def api(deployment: Deployment) -> AsyncIterator[AsyncClient]:
    """Return an HTTP client wired directly to the real application, no network."""
    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url=API_BASE) as http:
        yield http


async def _console_for(
    deployment: Deployment, api: AsyncClient, role: Role, *, node_id: str | None = TEAM_PAYMENTS
) -> tuple[Console, Any]:
    """Return a console and a real signed-in session for a principal holding ``role``."""
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id=f"{role.value}-user",
        role=role,
        node_id=node_id,
    )
    console = Console(client=ConsoleClient(transport=AsgiTransport(client=api)), api_base=API_BASE)
    principal = await console.client.with_token(secret).principal()
    return console, sign_in(secret, principal)


# --- The console really is a client of the real API ---------------------------


async def test_the_console_signs_in_with_a_real_token_and_reads_its_own_permissions(
    deployment: Deployment, api: AsyncClient
) -> None:
    console, session = await _console_for(deployment, api, Role.OPERATOR)

    assert session.viewer.principal_id == "operator-user"
    assert session.viewer.team_node_id == TEAM_PAYMENTS
    assert "config.write" in {permission.value for permission in session.viewer.permissions}
    assert console.api_base == API_BASE


async def test_an_unauthenticated_visitor_is_shown_the_sign_in_and_nothing_else(
    api: AsyncClient,
) -> None:
    from surfaces.console.session import Session

    console = Console(client=ConsoleClient(transport=AsgiTransport(client=api)))

    rendered = await console.render("/runs", Session())

    assert rendered.document is not None
    html = rendered.html()
    assert "Sign in" in html
    assert "Runs" not in html
    assert rendered.document.body.find("nav") == ()


async def test_a_revoked_token_ends_the_session_rather_than_failing_page_by_page(
    deployment: Deployment, api: AsyncClient
) -> None:
    from platform.identity.audit.recorder import AuditContext
    from platform.persistence.ports.audit_repository import ActorKind

    console, session = await _console_for(deployment, api, Role.OPERATOR)
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        stored = await uow.identity.list_tokens()

    await deployment.tokens.revoke(
        TenantScope(org_id=ORG),
        AuditContext(actor_kind=ActorKind.USER, actor_id="operator-user"),
        stored[0].token_id,
    )

    rendered = await console.render("/runs", session)

    assert not rendered.session.is_authenticated
    assert "Sign in" in rendered.html()


async def test_every_area_renders_against_the_real_api(
    deployment: Deployment, api: AsyncClient
) -> None:
    console, session = await _console_for(deployment, api, Role.OWNER, node_id=None)

    for path in ("/runs", "/interactions", "/memory", "/knowledge", "/catalogue", "/admin"):
        rendered = await console.render(path, session)
        assert rendered.document is not None, path
        assert rendered.html().startswith("<!doctype html>"), path


# --- SC-005: the preview is the server's answer, not the console's ------------


#: Three real configuration paths, one per property being proven. All three
#: validate against the shipped schema, because a preview of a field the server
#: would reject is not a preview of anything.
LOCKED_PATH = "policies.masking.level"
GATED_PATH = "policies.masking.enabled"
FREE_PATH = "capabilities.disabled"


async def _seed_locked_and_gated(deployment: Deployment) -> None:
    """Give the organisation a locked field and an approval-gated one."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        root = await uow.config.get(ORG)
        assert root is not None
        await uow.config.upsert(
            ConfigNode(
                node_id=ORG,
                kind=root.kind,
                name=root.name,
                parent_id=None,
                values=NodeDocument.of(
                    {"policies": {"masking": {"level": "standard", "enabled": True}}},
                    locked=(LOCKED_PATH,),
                    approval_gated=(GATED_PATH,),
                ).to_values(),
                version=root.version,
            )
        )


async def test_the_preview_the_console_renders_is_what_the_server_computed(
    deployment: Deployment, api: AsyncClient
) -> None:
    await _seed_locked_and_gated(deployment)
    console, session = await _console_for(deployment, api, Role.OWNER, node_id=None)
    client = console.client.with_token(session.token)

    preview = await client.preview_config(
        TEAM_PAYMENTS, {"policies": {"masking": {"enabled": False}}}
    )
    rendered = preview_panel(PageContext(viewer=session.viewer), preview)

    from surfaces.console.html import text_of

    shown = text_of(rendered)
    assert GATED_PATH in shown
    assert rendered.attribute("data-requires-approval") == "true"


async def test_saving_the_previewed_patch_produces_exactly_the_previewed_values(
    deployment: Deployment, api: AsyncClient
) -> None:
    """SC-005 stated as the property that matters: preview equals outcome."""
    await _seed_locked_and_gated(deployment)
    console, session = await _console_for(deployment, api, Role.OWNER, node_id=None)
    client = console.client.with_token(session.token)
    # A capability this build actually installs. The write validates a reference
    # against the live catalogue, so an invented name is refused before the
    # property this test is about — preview equals outcome — can be observed.
    patch = {"capabilities": {"disabled": ["restart_workload"]}}

    preview = await client.preview_config(TEAM_PAYMENTS, patch)
    await client.write_config(TEAM_PAYMENTS, patch)
    after = await client.effective_config(TEAM_PAYMENTS)

    assert preview["values"] == after["values"]
    assert preview["provenance"] == after["provenance"]


async def test_a_preview_of_a_locked_field_names_the_node_holding_the_lock(
    deployment: Deployment, api: AsyncClient
) -> None:
    await _seed_locked_and_gated(deployment)
    console, session = await _console_for(deployment, api, Role.OWNER, node_id=None)
    client = console.client.with_token(session.token)

    preview = await client.preview_config(
        TEAM_PAYMENTS, {"policies": {"masking": {"level": "off"}}}
    )
    rendered = preview_panel(PageContext(viewer=session.viewer), preview)

    from surfaces.console.html import text_of

    assert preview["locked"] == {"policies.masking.level": ORG}
    assert ORG in text_of(rendered)
    assert [node for node in rendered.walk() if node.has("data-locked")]


async def test_a_gated_change_is_marked_as_queuing_rather_than_applying(
    deployment: Deployment, api: AsyncClient
) -> None:
    await _seed_locked_and_gated(deployment)
    console, session = await _console_for(deployment, api, Role.OWNER, node_id=None)
    client = console.client.with_token(session.token)

    preview = await client.preview_config(
        TEAM_PAYMENTS, {"policies": {"masking": {"enabled": False}}}
    )
    rendered = preview_panel(PageContext(viewer=session.viewer), preview)

    from surfaces.console.html import text_of

    assert [node for node in rendered.walk() if node.has("data-gated")]
    assert "queues it for review" in text_of(rendered)


async def test_the_console_never_merges_configuration_itself() -> None:
    """The patch builder is shape only — it holds no opinion about any value."""
    assert patch_of("a.b.c", "x") == {"a": {"b": {"c": "x"}}}
    assert patch_of("", "x") == {}


# --- SC-006: credentials never pass through the console -----------------------


async def test_a_credential_form_posts_to_the_api_and_never_to_the_console(
    deployment: Deployment, api: AsyncClient
) -> None:
    console, session = await _console_for(deployment, api, Role.OWNER, node_id=None)
    client = console.client.with_token(session.token)
    schemas = await client.integration_schemas(TEAM_PAYMENTS)
    assert schemas, "no integration is installed at all"

    context = PageContext(viewer=session.viewer)
    rendered = catalogue_page.integration_form(context, schemas[0], api_base=API_BASE)

    forms = rendered.find("form")
    assert forms, "the form was omitted for an owner"
    action = str(forms[0].attribute("action"))
    assert action.startswith(API_BASE)
    assert "/v1/integrations/" in action


async def test_every_secret_field_of_a_generated_form_is_a_password_field(
    deployment: Deployment, api: AsyncClient
) -> None:
    console, session = await _console_for(deployment, api, Role.OWNER, node_id=None)
    schemas = await console.client.with_token(session.token).integration_schemas(TEAM_PAYMENTS)
    context = PageContext(viewer=session.viewer)

    for schema in schemas:
        rendered = catalogue_page.integration_form(context, schema, api_base=API_BASE)
        secret_names = {str(each["name"]) for each in schema["credential_fields"]}
        for control in rendered.find("input"):
            if str(control.attribute("name")) in secret_names:
                assert control.attribute("type") == "password"
                assert control.attribute("autocomplete") == "off"


def test_the_console_client_has_no_method_that_carries_a_credential() -> None:
    """SC-006 as a structural fact rather than a discipline somebody has to keep.

    A secret cannot pass through this process if there is no method that would
    carry one. Asserted over the client's own surface so that adding one is a
    deliberate act that fails here.
    """
    forbidden = {"credential", "secret", "password", "api_key", "vault"}
    named = {name for name in dir(ConsoleClient) if not name.startswith("_")}

    offending = {name for name in named if any(word in name.lower() for word in forbidden)}
    assert offending == set(), f"the console client grew a credential path: {sorted(offending)}"


async def test_no_console_page_renders_a_stored_credential_value(
    deployment: Deployment, api: AsyncClient
) -> None:
    """The schemas describe fields; they never carry values, and neither does a page."""
    console, session = await _console_for(deployment, api, Role.OWNER, node_id=None)
    client = console.client.with_token(session.token)

    for schema in await client.integration_schemas(TEAM_PAYMENTS):
        for spec in (*schema["credential_fields"], *schema["settings_fields"]):
            assert "value" not in spec, f"{schema['name']} returned a credential value"


# --- SC-004 against the real permission table ---------------------------------


async def test_a_real_viewer_token_produces_a_page_with_no_write_control(
    deployment: Deployment, api: AsyncClient
) -> None:
    console, session = await _console_for(deployment, api, Role.VIEWER)

    for path in ("/runs", "/interactions", "/memory", "/knowledge"):
        rendered = await console.render(path, session)
        assert rendered.document is not None
        assert write_actions_in(rendered.document.body) == (), path


async def test_a_team_scoped_console_cannot_reach_another_team_s_configuration(
    deployment: Deployment, api: AsyncClient
) -> None:
    console, session = await _console_for(deployment, api, Role.OPERATOR, node_id=TEAM_PAYMENTS)
    client = console.client.with_token(session.token)

    with pytest.raises(ConsoleApiError) as refusal:
        await client.effective_config(TEAM_PLATFORM)

    assert refusal.value.is_missing


async def test_a_team_scoped_console_sees_only_its_own_subtree_in_the_org_tree(
    deployment: Deployment, api: AsyncClient
) -> None:
    console, session = await _console_for(deployment, api, Role.OPERATOR, node_id=TEAM_PAYMENTS)

    nodes = await console.client.with_token(session.token).config_tree()

    assert {str(node["node_id"]) for node in nodes} == {TEAM_PAYMENTS}


async def test_a_forbidden_call_becomes_a_page_saying_so_rather_than_a_stack_trace(
    deployment: Deployment, api: AsyncClient
) -> None:
    console, session = await _console_for(deployment, api, Role.VIEWER)

    rendered = await console.render("/admin", session)

    assert rendered.document is not None
    assert "permission" in rendered.html()
