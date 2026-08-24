"""The guided first run, driven over HTTP against a deployment somewhere else.

This is the test the whole feature exists for. ``OnboardingFlow`` was always
transport-agnostic — it holds a ``PlatformClient`` and never branches on which
one — but five of the methods it needs were refused by the remote client because
the API had no route for them. Four steps and a verification, and it stopped at
the second.

So the assertion is the flow finishing, not the routes existing: the refusals had
to go as a set, and a test per route would have passed on the day four of five
worked. Nothing here stands in for the boundary being proven. The application is
the real ``create_app``, the guard is the real permission table, the vault is the
real vault, and the client opens what it would open over a socket.

The one thing composed rather than run is the model verification, which is the
single operation that leaves the host and spends money — the seam
``GatewayState.model_verifier`` exists to be.

The second half of the file is the sweep. A secret entered at the prompt must
reach the vault and nothing else, so everything the run produced — every response
body, every log line, every audit detail — is searched for it.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.first_run import (
    SETUP_READINESS_ABSENT,
    SETUP_READINESS_CONFIGURED,
    SETUP_READINESS_VERIFIED,
)
from config.constants.llm import DEFAULT_MODEL_ID, SUPPORTED_PROVIDERS
from core.llm.verification import ModelVerdict
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from gateway.http.verifications import recorded_checks
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.transaction import TenantScope
from platform.persistence.ports.verification_ledger import VerificationSubject
from platform.startup.checklist import build_checklist
from surfaces.cli.client import Endpoint, RemoteClient
from surfaces.cli.wizard.flow import onboard
from surfaces.cli.wizard.prompts import ScriptedPrompter
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    FakeInvestigationRunner,
    issue_token,
)

pytestmark = pytest.mark.contract

ENDPOINT_URL = "https://ninjasre.internal"

#: What an operator types at the prompt. The sweep looks for this exact string
#: rather than for a shape: a test asserting "no forty-character hex" would pass
#: against a log line carrying the key with a dash in it, and that is not the
#: property Article IV describes.
SECRET = "sk-ant-0f1e2d3c4b5a69788796a5b4c3d2e1f0"


class _Answer(io.BytesIO):
    """What ``urlopen`` returns, as much of it as this client reads."""

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@dataclass(slots=True)
class _Deployment:
    """A running application, reachable through a urllib-shaped opener."""

    loop: asyncio.AbstractEventLoop
    thread: threading.Thread
    http: AsyncClient
    gateway: FakePersistence
    token: str
    #: Every response body this run produced, kept for the sweep.
    answered: list[str]

    def run(self, coroutine: Any) -> Any:
        """Run ``coroutine`` on the application's own loop and return its result."""
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=30)

    def open(self, request: urllib.request.Request, timeout: float = 0) -> _Answer:
        """Answer one request from the real application, recording what came back."""
        answer = self.run(
            self.http.request(
                request.get_method(),
                request.full_url,
                content=request.data,
                headers=dict(request.header_items()),
            )
        )
        self.answered.append(answer.text)
        if answer.status_code >= 400:
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=answer.status_code,
                msg=answer.text,
                hdrs=None,  # type: ignore[arg-type]
                fp=_Answer(answer.content),
            )
        return _Answer(answer.content)

    def close(self) -> None:
        """Stop the application's loop and join its thread."""
        self.run(self.http.aclose())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=10)


async def _verifier(provider_id: str, model_id: str | None = None) -> ModelVerdict:
    """Stand in for the one call that would leave the host.

    ``model_id`` is what the deployment is configured to run, and ``None`` when
    the configuration names none — in which case the verifier's own default
    stands. Taking it is not optional for a double: a verifier of one argument
    is a verifier the application cannot call, and the deployment answered every
    verification with a 500 for exactly as long as this signature disagreed.
    """
    model = model_id or DEFAULT_MODEL_ID
    return ModelVerdict(
        provider_id=provider_id,
        model_id=model,
        satisfied=True,
        summary_line=f"{model} on {provider_id} calls tools and returns structure",
    )


async def _seed(gateway: FakePersistence) -> None:
    """Create the organisation and the team the operator is acting at."""
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS,
                kind=ConfigNodeKind.TEAM,
                name=TEAM_PAYMENTS,
                parent_id=ORG,
            )
        )


@pytest.fixture
def deployment() -> Iterator[_Deployment]:
    """Return the real application on its own loop, with a real operator token."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    def on_loop(coroutine: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result(timeout=30)

    gateway = FakePersistence()
    on_loop(_seed(gateway))
    tokens = TokenService(gateway=gateway)
    token = on_loop(
        issue_token(gateway, tokens, user_id="ada", role=Role.OWNER, node_id=TEAM_PAYMENTS)
    )
    state = GatewayState(
        gateway=gateway,
        tokens=tokens,
        investigator=FakeInvestigationRunner(),
        model_verifier=_verifier,
    )
    http = AsyncClient(transport=ASGITransport(app=create_app(state)), base_url=ENDPOINT_URL)

    running = _Deployment(
        loop=loop, thread=thread, http=http, gateway=gateway, token=token, answered=[]
    )
    try:
        yield running
    finally:
        running.close()


@pytest.fixture
def remote(deployment: _Deployment) -> RemoteClient:
    """Return the CLI's remote client, pointed at the running application."""
    return RemoteClient(
        endpoint=Endpoint(url=ENDPOINT_URL, token=deployment.token), opener=deployment.open
    )


def _prompter() -> ScriptedPrompter:
    """Return the operator's side of the conversation: a key, a model, no integrations."""
    return ScriptedPrompter(answers=[SECRET, DEFAULT_MODEL_ID, ""])


# --- The four steps, over the wire ---------------------------------------------


def test_the_guided_first_run_completes_against_a_remote_deployment(
    remote: RemoteClient,
) -> None:
    """``ninjasre --endpoint <url> --token <t> onboard``, end to end.

    The refusals had to go as a set. A test per route would have passed on the
    day four of the five worked, and the flow would still have stopped at step
    two.
    """
    prompter = _prompter()

    outcome = asyncio.run(onboard(remote, prompter, provider_id="anthropic"))

    assert outcome.provider_id == "anthropic"
    assert outcome.model_id == DEFAULT_MODEL_ID
    assert outcome.verified, outcome.detail
    assert "credential stored in the vault for anthropic" in outcome.steps
    assert "verified" in outcome.steps


def test_the_operator_is_shown_all_nine_providers_before_choosing(
    remote: RemoteClient,
) -> None:
    """Provider neutrality where somebody actually decides, not in the adapter layer."""
    prompter = ScriptedPrompter(answers=["anthropic", SECRET, DEFAULT_MODEL_ID, ""])

    asyncio.run(onboard(remote, prompter))

    offered = "\n".join(prompter.said)
    for provider in SUPPORTED_PROVIDERS:
        assert provider in offered, f"{provider} was not offered"


def test_the_key_is_asked_for_without_echo_and_with_somewhere_to_get_it(
    remote: RemoteClient,
) -> None:
    prompter = _prompter()

    asyncio.run(onboard(remote, prompter, provider_id="anthropic"))

    assert prompter.secrets_asked, "the API key was asked for in the clear"
    assert any("console.anthropic.com" in said for said in prompter.said)


def test_the_deployment_reads_as_ready_once_the_flow_has_run(
    remote: RemoteClient, deployment: _Deployment
) -> None:
    """The checklist a console branches on moves through its three provider states.

    The checklist itself never calls a provider's endpoint -- it reads the last
    recorded verdict, handed to it by a caller who already read the verification
    ledger. The ``verified`` case below reads that ledger the same way the real
    checklist route does, through ``recorded_checks``, against the record
    onboarding's own call to the real verify endpoint actually wrote -- not a
    synthetic verdict standing in for one.
    """
    before = deployment.run(build_checklist(deployment.gateway, organisation_id=ORG))

    asyncio.run(onboard(remote, _prompter(), provider_id="anthropic"))

    after = deployment.run(build_checklist(deployment.gateway, organisation_id=ORG))
    provider_checks = deployment.run(
        recorded_checks(
            deployment.gateway, TenantScope(org_id=ORG), kind=VerificationSubject.MODEL_PROVIDER
        )
    )
    verified = deployment.run(
        build_checklist(deployment.gateway, organisation_id=ORG, provider_checks=provider_checks)
    )

    assert before.provider_readiness == SETUP_READINESS_ABSENT
    assert after.provider_readiness == SETUP_READINESS_CONFIGURED
    assert provider_checks["anthropic"].verified, "onboarding's own verify call did not persist"
    assert verified.provider_readiness == SETUP_READINESS_VERIFIED


def test_doctor_reports_on_the_deployment_the_flow_just_configured(
    remote: RemoteClient,
) -> None:
    """The other half of acceptance: ``doctor`` answers instead of refusing."""
    asyncio.run(onboard(remote, _prompter(), provider_id="anthropic"))

    report = asyncio.run(remote.diagnose())

    assert report.checks
    assert any(check.name == "model-provider" for check in report.checks)


# --- The sweep -------------------------------------------------------------------


def test_the_key_entered_at_the_prompt_is_in_the_vault_and_nowhere_else(
    remote: RemoteClient, deployment: _Deployment, caplog: pytest.LogCaptureFixture
) -> None:
    """Acceptance 2, over everything a whole guided run produced.

    Every response body the deployment sent, every log line either side of the
    wire, and every audit detail written along the way. The value went into one
    request body and stopped.
    """
    with caplog.at_level(logging.NOTSET):
        outcome = asyncio.run(onboard(remote, _prompter(), provider_id="anthropic"))
        report = asyncio.run(remote.diagnose())
        providers = asyncio.run(remote.list_providers())

    swept = "\n".join(
        [
            *deployment.answered,
            caplog.text,
            *(str(record.getMessage()) for record in caplog.records),
            *(repr(getattr(record, "__dict__", {})) for record in caplog.records),
            repr(outcome.to_record()),
            repr(report.to_record()),
            repr([status.to_record() for status in providers]),
            _audit_text(deployment),
        ]
    )

    assert outcome.verified
    assert SECRET not in swept
    # The field name is expected to be there. Asserting it is what stops the
    # sweep passing because nothing was recorded at all.
    assert "ANTHROPIC_API_KEY" in swept


def _audit_text(deployment: _Deployment) -> str:
    """Return every audit event this deployment wrote, as a query renders it."""

    async def read() -> str:
        async with deployment.gateway.begin(
            TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
        ) as uow:
            events = await uow.audit.query()
        return json.dumps(
            [
                {
                    "action": event.action,
                    "actor_id": event.actor_id,
                    "resource_id": event.resource_id,
                    "detail": dict(event.detail),
                }
                for event in events
            ],
            default=str,
        )

    return deployment.run(read())


def test_the_prompt_transcript_carries_no_secret_either(remote: RemoteClient) -> None:
    """The transcript is what an operator pastes into a support thread."""
    prompter = _prompter()

    outcome = asyncio.run(onboard(remote, prompter, provider_id="anthropic"))

    assert SECRET not in "\n".join(prompter.said)
    assert SECRET not in "\n".join(outcome.steps)
