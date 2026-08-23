"""Which capabilities a turn is offered, and the two questions that decide it.

The serving runner ranked the whole declared catalogue against what the alert
said about itself and cut at the schema ceiling. Two things it never asked:
whether this team has the integration a capability needs, and whether this
deployment could carry the capability out at all. Both produce the same visible
defect — a turn spent on a call that can only come back refused — and the schema
budget is small enough that one wasted slot is a reading the investigation did
not do.

The order matters as much as the filters. Cutting at the ceiling before
narrowing spends slots on capabilities that were about to be removed, so the
cut is last, and one of the tests below is written so that cutting first would
drop a capability the team actually has.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from capabilities.registry import build_registry
from capabilities.registry.catalogue import Registry
from capabilities.tools.remediation import control_plane
from capabilities.tools.remediation.control_plane import ControlPlaneState
from core.capability.ports import ConfiguredIntegrations
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    StreamEventKind,
)
from core.llm.usage import TokenCounts, UsageRecord
from gateway.http.remediation import compose_remediation
from gateway.http.services import InvestigationStart
from gateway.http.state import GatewayState
from gateway.runtime import investigator as module
from gateway.runtime.investigator import ReActInvestigationRunner
from platform.guardrails.engine import GuardrailEngine
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.remediation.models import RemediationAction, SubTargetResult
from platform.runs.stream import RunEventBroker

pytestmark = pytest.mark.unit

ORG = "acme"

#: Where a sandbox reaches the credential proxy. Any absolute address: nothing
#: in these tests sends a packet, and the policy type refuses to describe a
#: sandbox with nowhere to authenticate through.
PROXY = "http://127.0.0.1:8787"
TEAM = "acme/payments"

#: One write this deployment has components for, one it has not, and two reads
#: from different vendors. Enough to separate the two filters from each other.
CARRIED_WRITE = "scale_workload"
UNCARRIED_WRITE = "telegram_post_message"
PROMETHEUS_READ = "prometheus_metric_statistics"
LOKI_READ = "loki_sample_logs"


class _Plane:
    """A control plane that answers, so this deployment can carry a write."""

    async def read(self, action: RemediationAction) -> ControlPlaneState | None:
        del action
        return ControlPlaneState(values={"replicas": 2}, sub_targets=("checkout",))

    async def change(self, action: RemediationAction, **_: Any) -> tuple[SubTargetResult, ...]:
        del action
        return ()


@dataclass(slots=True)
class _SilentLLM:
    """Concludes on the first turn, and keeps what it was offered."""

    requests: list[InvokeRequest] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return "scripted"

    @property
    def model_id(self) -> str:
        return "scripted-1"

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text="Nothing further to gather.",
            finish_reason=FinishReason.STOP,
            usage=UsageRecord(
                provider_id=self.provider_id,
                model_id=self.model_id,
                tokens=TokenCounts(input_tokens=10, output_tokens=5),
            ),
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        result = await self.invoke(request)
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=result.text)
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=FinishReason.STOP)


@pytest.fixture
def plane() -> Any:
    previous = control_plane.bind(_Plane())
    yield
    control_plane.restore(previous)


@pytest.fixture
def unbound() -> Any:
    previous = control_plane.bind(None)
    yield
    control_plane.restore(previous)


def _catalogue(*names: str) -> Registry:
    """Return a registry holding the named shipped capabilities and nothing else."""
    shipped = build_registry()
    held = {}
    for name in names:
        found = shipped.tool(name)
        assert found is not None, f"{name} is no longer in the shipped catalogue"
        held[name] = found
    return Registry(tools=held)


def _connected(monkeypatch: pytest.MonkeyPatch, *integrations: str) -> None:
    """Say what this team has connected, without standing up a configuration tree."""

    async def availability(*_: Any, **__: Any) -> ConfiguredIntegrations:
        return ConfiguredIntegrations(integrations=tuple(integrations))

    monkeypatch.setattr(module, "team_availability", availability)


def _start(run_id: str = "run-1") -> InvestigationStart:
    return InvestigationStart(
        run_id=run_id,
        objective="checkout is saturating its replicas",
        team_node_id=TEAM,
        principal_id="ana",
        org_id=ORG,
        alert_source="alertmanager",
    )


async def _offered(
    registry: Registry, *, desk: bool, store: FakePersistence | None = None
) -> tuple[str, ...]:
    """Return the tool names one investigation was actually offered."""
    llm = _SilentLLM()
    held = store if store is not None else FakePersistence()
    runner = ReActInvestigationRunner(llm=llm, registry=registry)  # type: ignore[arg-type]
    runner.attach_recording(gateway=held, guardrails=GuardrailEngine(), broker=RunEventBroker())
    state = GatewayState(gateway=held, tokens=TokenService(gateway=held), investigator=runner)
    if desk:
        composed = await compose_remediation(state, org_id=ORG, proxy_url=PROXY)
        assert composed is not None
    await runner.investigate(_start())
    assert llm.requests, "the loop never called the model, so nothing was offered"
    return tuple(schema.name for schema in llm.requests[0].tools)


async def test_a_write_is_not_offered_to_a_deployment_with_no_desk(
    unbound: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connected(monkeypatch, "prometheus")

    offered = await _offered(_catalogue(CARRIED_WRITE, PROMETHEUS_READ), desk=False)

    assert CARRIED_WRITE not in offered, (
        "a deployment that composed no remediation desk offered a write anyway. The "
        "turn it costs can only end in a refusal."
    )
    assert PROMETHEUS_READ in offered


async def test_a_write_is_offered_when_this_deployment_can_carry_it(
    plane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connected(monkeypatch, "prometheus")

    offered = await _offered(_catalogue(CARRIED_WRITE, PROMETHEUS_READ), desk=True)

    assert CARRIED_WRITE in offered, (
        "a deployment with a composed desk and registered components withheld the write "
        "it can actually carry. Narrowing that removes everything is not narrowing."
    )


async def test_a_write_with_no_registered_components_is_not_offered(
    plane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The desk being composed is not enough: the capability has to be carriable."""
    _connected(monkeypatch, "prometheus", "telegram")

    offered = await _offered(_catalogue(UNCARRIED_WRITE, PROMETHEUS_READ), desk=True)

    assert UNCARRIED_WRITE not in offered, (
        f"{UNCARRIED_WRITE} was offered with a desk composed and no components "
        f"registered for it. There is nothing to read its state with, nothing to "
        f"derive an undo from, and nothing to apply."
    )


async def test_a_capability_needing_an_unconnected_integration_is_not_offered(
    plane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connected(monkeypatch, "prometheus")

    offered = await _offered(_catalogue(PROMETHEUS_READ, LOKI_READ), desk=True)

    assert PROMETHEUS_READ in offered
    assert LOKI_READ not in offered, (
        "a capability needing an integration this team has not connected was offered. "
        "It reports itself unavailable by name, which costs the turn either way."
    )


async def test_a_team_with_nothing_connected_never_reaches_the_model(
    plane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Narrowing to nothing ends the run rather than offering an empty turn."""
    _connected(monkeypatch)
    llm = _SilentLLM()
    store = FakePersistence()
    runner = ReActInvestigationRunner(llm=llm, registry=_catalogue(PROMETHEUS_READ, LOKI_READ))  # type: ignore[arg-type]
    runner.attach_recording(gateway=store, guardrails=GuardrailEngine(), broker=RunEventBroker())
    state = GatewayState(gateway=store, tokens=TokenService(gateway=store), investigator=runner)
    assert await compose_remediation(state, org_id=ORG, proxy_url=PROXY) is not None

    await runner.investigate(_start())

    assert llm.requests == [], (
        "a turn was sent for a team that can run nothing. Every capability on it "
        "would report itself unavailable by name."
    )


def _ranks_first(registry: Registry, *, alert_source: str, objective: str) -> str:
    """Return which of ``registry``'s capabilities the ranker puts first."""
    from capabilities.registry.planning import CatalogueRanker
    from core.pipeline.ports import IncidentSignals

    ranked = CatalogueRanker().rank(
        tuple(found.metadata for found in registry.tools.values()),
        IncidentSignals(alert_source=alert_source, summary=objective),
    )
    return ranked[0].name


async def test_the_cut_at_the_ceiling_happens_after_both_filters(
    plane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cutting first spends slots on capabilities that were about to be removed.

    The ceiling is lowered to one so the ordering is visible, and the case is
    built so that cutting first would leave the turn holding nothing: the
    top-ranked capability for this alert is the one the team has *not*
    connected. The precondition is asserted rather than assumed, because a
    ranking change would otherwise make this test pass without measuring
    anything.
    """
    registry = _catalogue(PROMETHEUS_READ, LOKI_READ)
    objective = "prometheus is reporting checkout saturating its replicas"
    assert _ranks_first(registry, alert_source="prometheus", objective=objective) == (
        PROMETHEUS_READ
    ), (
        "this test needs the unconnected capability to rank first; the ranker no "
        "longer puts it there, so the case no longer distinguishes the two orders."
    )

    _connected(monkeypatch, "loki")
    monkeypatch.setattr(module, "MAX_AGENT_TOOL_SCHEMAS", 1)

    llm = _SilentLLM()
    store = FakePersistence()
    runner = ReActInvestigationRunner(llm=llm, registry=registry)  # type: ignore[arg-type]
    runner.attach_recording(gateway=store, guardrails=GuardrailEngine(), broker=RunEventBroker())
    state = GatewayState(gateway=store, tokens=TokenService(gateway=store), investigator=runner)
    assert await compose_remediation(state, org_id=ORG, proxy_url=PROXY) is not None
    await runner.investigate(
        InvestigationStart(
            run_id="run-3",
            objective=objective,
            team_node_id=TEAM,
            principal_id="ana",
            org_id=ORG,
            alert_source="prometheus",
        )
    )

    offered = tuple(schema.name for schema in llm.requests[0].tools)
    assert offered == (LOKI_READ,), (
        f"with room for one capability the turn was offered {offered}. Cutting at the "
        f"ceiling before narrowing spends the budget on what is about to be removed."
    )


async def test_a_team_with_no_integrations_is_told_what_to_connect(
    plane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The answer that is written, tested, and had never once run.

    Not "no integrations configured" — which is true and leaves the reader where
    they started — but which one to connect, how many capabilities it would
    unlock, and which of those would have served the alert that just fired.
    """
    _connected(monkeypatch)
    llm = _SilentLLM()
    store = FakePersistence()
    runner = ReActInvestigationRunner(llm=llm, registry=_catalogue(PROMETHEUS_READ, LOKI_READ))  # type: ignore[arg-type]
    runner.attach_recording(gateway=store, guardrails=GuardrailEngine(), broker=RunEventBroker())
    state = GatewayState(gateway=store, tokens=TokenService(gateway=store), investigator=runner)
    assert await compose_remediation(state, org_id=ORG, proxy_url=PROXY) is not None

    summary = await runner.investigate(_start())

    assert not llm.requests, (
        "the model was called for a team that can run nothing. The run's only cost "
        "would have been spent on its cheapest sentence."
    )
    assert "prometheus" in summary.lower() or "loki" in summary.lower(), (
        f"the outcome for a team with nothing connected was {summary!r}, which names "
        f"no integration to connect."
    )


async def test_the_alert_source_is_suggested_first(
    plane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The integration whose name matches the source that fired comes first."""
    _connected(monkeypatch)
    llm = _SilentLLM()
    store = FakePersistence()
    runner = ReActInvestigationRunner(llm=llm, registry=_catalogue(PROMETHEUS_READ, LOKI_READ))  # type: ignore[arg-type]
    runner.attach_recording(gateway=store, guardrails=GuardrailEngine(), broker=RunEventBroker())
    state = GatewayState(gateway=store, tokens=TokenService(gateway=store), investigator=runner)
    assert await compose_remediation(state, org_id=ORG, proxy_url=PROXY) is not None

    summary = await runner.investigate(
        InvestigationStart(
            run_id="run-2",
            objective="the log store is silent",
            team_node_id=TEAM,
            principal_id="ana",
            org_id=ORG,
            alert_source="loki",
        )
    )

    lowered = summary.lower()
    assert "loki" in lowered
    assert lowered.index("loki") < (
        lowered.index("prometheus") if "prometheus" in lowered else len(lowered)
    ), f"the outcome suggested an integration before the one matching the alert source: {summary!r}"
