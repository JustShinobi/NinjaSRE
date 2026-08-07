"""Turning what a server offers into what a team may run.

SC-002 and SC-007 both live here, and they are the two halves of the same
argument: a bridged tool enters the catalogue on our terms, not the server's.
Unclassified means it cannot execute — asserted by attempting it, not by reading
a flag — and a server that offers more tools than the cap has its excess
reported rather than quietly dropped.
"""

from __future__ import annotations

import pytest

from capabilities.protocols.catalogue import bridged_catalogue
from capabilities.protocols.classification import ClassificationTable
from capabilities.protocols.port import ExclusionReason, ProtocolKind
from config.constants.protocols import MAX_TOOLS_PER_PROTOCOL_SERVER
from core.capability.metadata import SideEffectLevel
from core.capability.result import CapabilityErrorClass
from tests.unit.capabilities.protocols.conftest import ScriptedAdapter, offered

pytestmark = pytest.mark.unit


async def _catalogue(adapter: ScriptedAdapter, classifications: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    return await bridged_catalogue(
        adapter,
        servers=("deploys",),
        classifications=ClassificationTable.of(classifications or {}),
    )


# --- SC-002: an unclassified tool cannot execute -------------------------------


async def test_an_unclassified_tool_is_in_the_catalogue_and_refuses_to_run() -> None:
    adapter = ScriptedAdapter(tools=[offered("deploys", "rollout")])

    built = await _catalogue(adapter)

    capability = built.capability("deploys.rollout")
    assert capability is not None
    assert not capability.executable

    result = await capability.registered.invoke({"target": "web"})

    assert not result.succeeded
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.PERMISSION_DENIED
    assert "classif" in result.error.message.lower()
    # And the server was never contacted. A refusal that still made the call
    # would be an audit line rather than a control.
    assert adapter.invocations == []


async def test_a_tool_the_server_declares_read_still_cannot_execute() -> None:
    adapter = ScriptedAdapter(tools=[offered("deploys", "delete_everything", declared="read")])

    built = await _catalogue(adapter)

    capability = built.capability("deploys.delete_everything")
    assert capability is not None
    assert not capability.executable
    assert capability.classification.suggested_level is SideEffectLevel.READ
    assert capability.registered.metadata.side_effect_level is not SideEffectLevel.READ
    assert adapter.invocations == []


async def test_a_classified_tool_runs_and_reaches_the_server() -> None:
    adapter = ScriptedAdapter(tools=[offered("deploys", "status")])

    built = await _catalogue(adapter, {"deploys.status": "read"})

    capability = built.capability("deploys.status")
    assert capability is not None
    assert capability.executable
    assert capability.registered.metadata.side_effect_level is SideEffectLevel.READ

    result = await capability.registered.invoke({"target": "web"})

    assert result.succeeded
    assert adapter.invocations == [("deploys", "status", {"target": "web"})]


async def test_a_classified_write_carries_everything_the_approval_gate_needs() -> None:
    adapter = ScriptedAdapter(tools=[offered("deploys", "rollout")])

    built = await _catalogue(adapter, {"deploys.rollout": "write_reversible"})

    metadata = built.capability("deploys.rollout").registered.metadata
    assert metadata.side_effect_level.needs_approval
    assert metadata.requires_approval
    assert metadata.approval_reason.strip()
    assert metadata.rollback_plan.strip()


async def test_awaiting_classification_is_reported_for_the_console() -> None:
    adapter = ScriptedAdapter(
        tools=[offered("deploys", "status"), offered("deploys", "rollout")],
    )

    built = await _catalogue(adapter, {"deploys.status": "read"})

    assert built.awaiting_classification() == ("deploys.rollout",)


# --- SC-007: the cap reports its excess ----------------------------------------


async def test_a_server_over_the_cap_contributes_the_cap_and_reports_the_rest() -> None:
    total = MAX_TOOLS_PER_PROTOCOL_SERVER + 7
    adapter = ScriptedAdapter(tools=[offered("deploys", f"tool_{n}") for n in range(total)])

    built = await _catalogue(adapter)

    assert len(built.capabilities) == MAX_TOOLS_PER_PROTOCOL_SERVER
    capped = [item for item in built.excluded if item.reason is ExclusionReason.TOOL_CAP_REACHED]
    assert len(capped) == 7
    # Every dropped tool is named, not just counted: SC-007 is "reported rather
    # than silently dropped", and a number is not a report.
    assert {item.tool for item in capped} == {
        f"tool_{n}" for n in range(MAX_TOOLS_PER_PROTOCOL_SERVER, total)
    }
    assert str(total) in built.report()


async def test_the_tools_that_survive_the_cap_are_the_ones_the_server_listed_first() -> None:
    total = MAX_TOOLS_PER_PROTOCOL_SERVER + 3
    adapter = ScriptedAdapter(tools=[offered("deploys", f"tool_{n}") for n in range(total)])

    built = await _catalogue(adapter)

    assert [item.tool for item in built.capabilities][:3] == ["tool_0", "tool_1", "tool_2"]


# --- degradation and naming -----------------------------------------------------


async def test_an_unavailable_server_contributes_nothing_and_says_why() -> None:
    adapter = ScriptedAdapter(tools=[offered("deploys", "status")], reachable=False)

    built = await _catalogue(adapter, {"deploys.status": "read"})

    assert built.capabilities == ()
    assert built.unhealthy == ("deploys",)
    assert "deploys" in built.report()


async def test_two_servers_offering_the_same_tool_name_do_not_collide() -> None:
    adapter = ScriptedAdapter(
        tools=[offered("deploys", "status"), offered("payments", "status")],
    )

    built = await bridged_catalogue(
        adapter,
        servers=("deploys", "payments"),
        classifications=ClassificationTable.of(
            {"deploys.status": "read", "payments.status": "read"}
        ),
    )

    names = {item.registered.name for item in built.capabilities}
    assert names == {"deploys__status", "payments__status"}


async def test_a_bridged_tool_is_tagged_by_its_protocol_and_its_server() -> None:
    adapter = ScriptedAdapter(tools=[offered("deploys", "status")], kind=ProtocolKind.ACP)

    built = await _catalogue(adapter, {"deploys.status": "read"})

    tags = built.capability("deploys.status").registered.metadata.tags
    assert "bridged" in tags
    assert ProtocolKind.ACP.value in tags
    assert "deploys" in tags


async def test_a_bridged_tool_names_its_server_as_the_evidence_source() -> None:
    adapter = ScriptedAdapter(tools=[offered("deploys", "status")])

    built = await _catalogue(adapter, {"deploys.status": "read"})

    assert built.capability("deploys.status").registered.metadata.evidence_source == "deploys"


async def test_a_tool_that_declares_no_description_still_produces_a_usable_entry() -> None:
    adapter = ScriptedAdapter(tools=[offered("deploys", "status", description="  ")])

    built = await _catalogue(adapter, {"deploys.status": "read"})

    description = built.capability("deploys.status").registered.metadata.description
    assert description.strip()
    assert "deploys" in description


async def test_a_failing_server_call_becomes_a_classified_result_not_an_exception() -> None:
    adapter = ScriptedAdapter(tools=[offered("deploys", "status")], reachable=True)
    built = await _catalogue(adapter, {"deploys.status": "read"})
    capability = built.capability("deploys.status")

    class Exploding(ScriptedAdapter):
        async def invoke(self, server: str, tool: str, arguments):  # type: ignore[no-untyped-def]
            raise RuntimeError("the transport fell over")

    rebuilt = await bridged_catalogue(
        Exploding(tools=[offered("deploys", "status")]),
        servers=("deploys",),
        classifications=ClassificationTable.of({"deploys.status": "read"}),
    )
    result = await rebuilt.capability("deploys.status").registered.invoke({"target": "web"})

    assert capability.executable
    assert not result.succeeded
    assert result.error is not None
    assert result.error.classification is CapabilityErrorClass.INTERNAL
