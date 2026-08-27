"""A served investigation re-decides its toolset before every turn.

The sibling of ``tests/unit/capabilities/registry/test_turn_ranking.py``, which
asks whether the ranker can do this. This file asks the question that decides
whether it is a delivery: does a run started through
``ReActInvestigationRunner.investigate`` — the entry point a webhook and the
REST route both reach — actually get a different payload on its second turn?

Measured on staging, from a real run's own selection rationale::

    ranked 76, offered 40, cut by the ceiling 20

``_select_tools`` ran once, before the first turn, and the loop then held that
answer for the whole investigation. The twenty were not cut from a turn; they
were cut from the run. Every assertion below is read off what the model was
actually sent, turn by turn, rather than off a selector called directly — a
mechanism with no path from a serving composition root is not a delivery.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from capabilities.registry.catalogue import Registry
from config.constants.runs import TURN_PAYLOAD_RATIONALE
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.registered import RegisteredTool, capability_marker
from core.llm.types import FinishReason, InvokeResult, ToolCall
from core.llm.usage import TokenCounts, UsageRecord
from gateway.http.services import InvestigationStart
from gateway.runtime import investigator as module
from gateway.runtime.investigator import ReActInvestigationRunner
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.runs.stream import RunEventBroker
from tests.unit.gateway.runtime.conftest import PROVIDER_ID, ScriptedLLM, text_turn

pytestmark = pytest.mark.unit

ORG = "acme"
TEAM = "platform"


def _tool(
    name: str,
    *,
    source: str,
    tags: tuple[str, ...] = (),
    use_cases: tuple[str, ...] = (),
) -> RegisteredTool:
    """Return a throwaway read declaring exactly what a test wants ranked.

    Requires no integration, so the availability narrowing passes it through
    and what these tests measure is the ranking rather than the filters —
    those have their own file in ``test_tool_selection.py``.
    """

    async def _body() -> dict[str, Any]:
        return {"read": name}

    _body.__name__ = f"body_{name}"
    decorated = tool(
        name=name,
        display_name=name.replace("_", " ").title(),
        description=f"Reads {source} and reports what it read.",
        domain="observability",
        evidence_source=source,
        evidence_type=EvidenceType.LOG,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
        tags=tags,
        use_cases=use_cases,
    )(_body)
    found = capability_marker(decorated)
    assert found is not None, f"{name!r} carries no capability marker"
    return found


#: What the system that delivered the alert can say about the alert itself.
#: Top of the opening ranking, because for a tool "the alert source it
#: declares" is the vendor its evidence comes from.
ALERTING = _tool(
    "alertmanager_incident_statistics",
    source="alertmanager",
    tags=("alertmanager", "alert"),
    use_cases=("count how many alerts fired in a window",),
)

#: The vendor that holds the thing that actually broke. Nothing in the opening
#: alert text names it, so it does not reach the opening payload.
BACKUPS = _tool(
    "proxmox_backup_failures",
    source="proxmox",
    tags=("proxmox", "backup"),
    use_cases=("list the backup jobs that failed on a node",),
)

#: Filler that scores nothing and sorts before ``proxmox_``, so it — and not
#: the capability under test — is what the opening turn's spare slot goes to.
FILLER = _tool("datadog_unrelated_read", source="datadog")


def _registry(*tools: RegisteredTool) -> Registry:
    return Registry(tools={found.name: found for found in tools})


def _start(run_id: str = "run-1") -> InvestigationStart:
    return InvestigationStart(
        run_id=run_id,
        objective="alertmanager fired: something is wrong on the estate",
        team_node_id=TEAM,
        principal_id="operator-1",
        org_id=ORG,
        alert_source="alertmanager",
    )


def _calls(name: str, *, said: str) -> InvokeResult:
    """Return a turn that calls ``name`` and says ``said`` while doing it."""
    return InvokeResult(
        provider_id=PROVIDER_ID,
        model_id="scripted-1",
        text=said,
        tool_calls=(ToolCall(id=f"call-{name}", name=name, arguments={}),),
        finish_reason=FinishReason.TOOL_CALLS,
        usage=UsageRecord(
            provider_id=PROVIDER_ID,
            model_id="scripted-1",
            tokens=TokenCounts(input_tokens=100, output_tokens=20),
        ),
    )


#: What the model says on its first turn. This is the "I need X" the design
#: never had a way to hear: ranked once against the alert, saying it changes
#: nothing; ranked again before the next turn, it is the whole signal.
ESTABLISHED = "the alert is not an alert storm — the failing job is a proxmox backup on node pve01"


def _offered_per_turn(llm: ScriptedLLM) -> tuple[tuple[str, ...], ...]:
    """Return the capability names each turn was actually sent, in turn order."""
    return tuple(tuple(schema.name for schema in request.tools) for request in llm.requests)


async def _run(
    llm: ScriptedLLM,
    registry: Registry,
    *,
    gateway: PersistenceGateway | None = None,
    run_id: str = "run-1",
) -> ReActInvestigationRunner:
    """Drive one whole investigation through the serving entry point."""
    runner = ReActInvestigationRunner(llm=llm, registry=registry)  # type: ignore[arg-type]
    if gateway is not None:
        runner.attach_recording(
            gateway=gateway, guardrails=GuardrailEngine(), broker=RunEventBroker()
        )
    await runner.investigate(_start(run_id))
    return runner


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, name="Acme")
    yield store
    await store.close()


async def test_the_second_turn_is_offered_a_capability_the_first_turn_was_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect, at the size it can be read at: two turns, two payloads.

    Room for two capabilities and three to choose between. The opening alert
    names Alertmanager, so the opening payload is the alerting tool and the
    filler that sorts next. The model then says, in its own words, that the
    incident is a Proxmox backup failure — and the turn after that has to be
    able to act on it.

    Before this, the second turn was sent the first turn's payload, because
    ``_select_tools`` had run once and the loop was holding its answer. The
    Proxmox capability was not cut from a turn; it was cut from the run.
    """
    monkeypatch.setattr(module, "MAX_AGENT_TOOL_SCHEMAS", 2)
    llm = ScriptedLLM([_calls(ALERTING.name, said=ESTABLISHED), text_turn("backups are failing")])

    await _run(llm, _registry(ALERTING, BACKUPS, FILLER))

    turns = _offered_per_turn(llm)
    assert len(turns) >= 2, f"the run did not reach a second turn: {turns}"
    first, second = turns[0], turns[1]

    assert BACKUPS.name not in first, (
        f"the opening turn already held {BACKUPS.name}, so this case cannot tell a "
        f"re-ranked payload from a fixed one: {first}"
    )
    assert BACKUPS.name in second, (
        f"the second turn was offered {second} after the model established the incident "
        f"is a Proxmox backup failure. Selection that runs once before the first turn "
        f"makes every capability it cut unreachable for the whole run, and leaves the "
        f"model no way to say it needs one."
    )


async def test_a_capability_called_on_one_turn_is_still_there_on_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-ranking must not pull a tool out from under the model mid-thought.

    The failure this guards against would read as a model defect rather than a
    selection one: the model calls a capability, the next turn's ranking drops
    it, and its follow-up call comes back "unknown capability" for something it
    was holding one turn ago.

    Same script as the test above, so the two are one case read two ways: the
    payload moves, and what is in flight moves with it rather than under it.
    """
    monkeypatch.setattr(module, "MAX_AGENT_TOOL_SCHEMAS", 2)
    llm = ScriptedLLM([_calls(ALERTING.name, said=ESTABLISHED), text_turn("backups are failing")])

    await _run(llm, _registry(ALERTING, BACKUPS, FILLER))

    turns = _offered_per_turn(llm)
    assert ALERTING.name in turns[1], (
        f"{ALERTING.name} was called on the first turn and the second turn was offered "
        f"{turns[1]}. A toolset that reshuffles underneath a call in progress is a "
        f"different failure from the one per-turn ranking exists to fix."
    )


async def test_every_turn_stays_inside_the_schema_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Article II clause 3, asserted where the clause actually applies.

    The cap is on the payload of a turn. Re-deciding that payload every turn is
    only permissible because the cap is re-applied every turn — so the two are
    asserted as one property, against a catalogue far larger than the ceiling.
    """
    monkeypatch.setattr(module, "MAX_AGENT_TOOL_SCHEMAS", 3)
    crowd = tuple(_tool(f"vendor_read_{index:02d}", source=f"vendor{index}") for index in range(20))
    llm = ScriptedLLM([_calls(ALERTING.name, said=ESTABLISHED), text_turn("nothing further")])

    await _run(llm, _registry(ALERTING, BACKUPS, FILLER, *crowd))

    turns = _offered_per_turn(llm)
    assert turns, "the loop never called the model"
    for index, offered in enumerate(turns):
        assert len(offered) <= 3, (
            f"turn {index + 1} carried {len(offered)} tool schemas against a ceiling of 3. "
            f"The cap is on every turn's payload, not on the first one: {offered}"
        )


async def test_each_turn_records_what_it_was_offered_and_what_it_cut(
    monkeypatch: pytest.MonkeyPatch, gateway: PersistenceGateway
) -> None:
    """The record has to follow the decision, or it stops being evidence.

    Once the offered set changes between turns, an operator asking why a
    capability was missing is asking about a turn. A rationale written once for
    the run would be answering about a payload that no longer exists — and the
    two turns here genuinely had different ones, so a record that repeated
    itself would be describing the first turn twice.
    """
    monkeypatch.setattr(module, "MAX_AGENT_TOOL_SCHEMAS", 2)
    llm = ScriptedLLM([_calls(ALERTING.name, said=ESTABLISHED), text_turn("backups are failing")])

    async with gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
        from platform.runs.recorder import RunRecorder

        await RunRecorder(store=uow.run_traces).start_run(
            trigger="alert", principal_id="operator-1", team_node_id=TEAM, run_id="run-1"
        )

    await _run(llm, _registry(ALERTING, BACKUPS, FILLER), gateway=gateway)

    async with gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
        recorded = await uow.run_traces.turns_for_run("run-1")

    rationales: Sequence[str] = [
        str(turn.payload.get(TURN_PAYLOAD_RATIONALE, "")) for turn in recorded
    ]
    assert len(rationales) >= 2, f"fewer than two turns were recorded: {rationales}"
    for index, rationale in enumerate(rationales[:2]):
        assert "offered" in rationale and "cut by the ceiling" in rationale, (
            f"turn {index + 1} recorded no account of what it offered and what the "
            f"ceiling took: {rationale!r}"
        )
    assert rationales[0] != rationales[1], (
        "both turns recorded the same selection rationale, although they were offered "
        "different capabilities. A record written once for the run describes a payload "
        "that no longer exists by the time anybody opens it."
    )
