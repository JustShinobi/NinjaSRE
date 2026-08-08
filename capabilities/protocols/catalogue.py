"""What a set of bridged servers contributes to a team's catalogue.

This is where a third-party declaration becomes an ordinary ``RegisteredTool``,
and "ordinary" is the whole design. Selection scores it, the approval gate reads
its side-effect level, the guardrail hooks scan its arguments and its output,
the tool cache dedupes it, and the trace records it — none of which knows it came
from somewhere else, because none of them is given a way to find out.

Three rules are applied here rather than in each protocol's adapter, so all
three protocols get them identically:

**The cap, with its excess named.** A server offering four hundred tools
contributes ``MAX_TOOLS_PER_PROTOCOL_SERVER`` of them and every one it did not
contribute is listed with a reason. A count is not a report: an operator needs
to know *which* tool is missing before they can decide the server is configured
wrong.

**The classification, or the refusal.** An unclassified tool is still built into
a registration and still appears in the catalogue — it is a thing the operator
has to decide about, and hiding it is how it never gets decided. Its body
refuses, before any argument reaches the server, so "cannot execute" is a
property of the call rather than of whoever remembered to check.

**An unreachable server degrades to nothing.** No exception leaves here for a
server being down (FR-007). The tools are absent, the server is listed as
unhealthy, and the investigation runs with what is left.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from capabilities.protocols.classification import (
    UNCLASSIFIED_LEVEL,
    Classification,
    ClassificationTable,
)
from capabilities.protocols.port import (
    BridgedResult,
    BridgedTool,
    BridgeHealth,
    Discovery,
    ExcludedTool,
    ExclusionReason,
    ProtocolAdapter,
    ProtocolKind,
)
from config.constants.autonomy import UNCLASSIFIED_RISK_CLASS
from config.constants.protocols import (
    MAX_BRIDGED_DESCRIPTION_CHARS,
    MAX_TOOLS_PER_PROTOCOL_SERVER,
)
from core.capability.metadata import EvidenceType, ToolMetadata
from core.capability.registered import RegisteredTool, build_registration, classify_exception
from core.capability.result import CapabilityErrorClass, CapabilityResult, Evidence
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The tag every bridged capability carries, so a team can switch the whole lot
#: off with one ``disabled_tags`` entry rather than by naming each tool.
BRIDGED_TAG = "bridged"

#: What a tool's entry says when its server declared no description. Blank is not
#: an option — the metadata type refuses it, and rightly: a tool the model cannot
#: tell apart from another is a tool it calls at random.
DEFAULT_DESCRIPTION = "A tool bridged from the {server} server. The server declared no description."

#: What a human is being asked to accept when they approve a bridged write.
BRIDGED_APPROVAL_REASON = (
    "{qualified} runs on {server}, a bridged server outside this deployment. "
    "An operator classified it as {level}."
)

#: A bridged tool has no rollback generator and cannot be given one — nothing
#: here knows what the server did. Saying so is the honest plan, and it is what
#: the approver reads before deciding.
BRIDGED_ROLLBACK_PLAN = (
    "The {server} server declares no rollback for {qualified}. Undoing this action "
    "means acting in {server} directly; there is no automated reversal."
)

#: What a bridged tool's answer counts as. Not ``analysis`` — the server observed
#: something in a system we do not model — and not a vendor evidence type we
#: would be inventing. A document is what an opaque external answer is.
BRIDGED_EVIDENCE_TYPE = EvidenceType.DOCUMENT


@dataclass(frozen=True, slots=True)
class BridgedCapability:
    """One external tool as the catalogue holds it.

    ``registered`` exists whether or not the tool may run. That is deliberate:
    the console lists it, selection can score it, and attempting it produces a
    refusal the model can read — which is what makes "unclassified cannot
    execute" a testable property rather than a policy nobody exercises.
    """

    server: str
    tool: str
    kind: ProtocolKind
    classification: Classification
    registered: RegisteredTool
    executable: bool

    @property
    def qualified_name(self) -> str:
        """Return the ``<server>.<tool>`` an operator classifies against."""
        return self.classification.qualified_name

    @property
    def catalogue_name(self) -> str:
        """Return the name the model calls."""
        return self.registered.name


@dataclass(frozen=True, slots=True)
class BridgedCatalogue:
    """Everything a team's registered servers contributed, and everything they did not."""

    capabilities: tuple[BridgedCapability, ...] = ()
    excluded: tuple[ExcludedTool, ...] = ()
    unavailable: tuple[BridgeHealth, ...] = ()
    discoveries: tuple[Discovery, ...] = ()
    classifications: ClassificationTable = field(default_factory=ClassificationTable)

    @property
    def unhealthy(self) -> tuple[str, ...]:
        """Return the names of the servers that could not be reached."""
        return tuple(report.server for report in self.unavailable)

    def capability(self, qualified_name: str) -> BridgedCapability | None:
        """Return the bridged capability called ``qualified_name``, or ``None``."""
        for found in self.capabilities:
            if found.qualified_name == qualified_name:
                return found
        return None

    def tools(self) -> dict[str, RegisteredTool]:
        """Return the registrations, keyed the way the loop's tool map is."""
        return {found.registered.name: found.registered for found in self.capabilities}

    def executable_tools(self) -> dict[str, RegisteredTool]:
        """Return only the registrations an operator has classified."""
        return {
            found.registered.name: found.registered
            for found in self.capabilities
            if found.executable
        }

    def awaiting_classification(self) -> tuple[str, ...]:
        """Return the qualified names still waiting on an operator's decision."""
        return tuple(found.qualified_name for found in self.capabilities if not found.executable)

    def report(self) -> str:
        """Return the sentence the console shows about the bridged catalogue."""
        parts = [discovery.report() for discovery in self.discoveries]
        for report in self.unavailable:
            parts.append(
                f"{report.server}: unavailable, its tools are excluded"
                + (f" ({report.detail})" if report.detail else "")
            )
        awaiting = self.awaiting_classification()
        if awaiting:
            parts.append(f"{len(awaiting)} tools awaiting classification")
        return "; ".join(parts)


async def bridged_catalogue(
    adapter: ProtocolAdapter,
    *,
    servers: Sequence[str],
    classifications: ClassificationTable | None = None,
    tool_cap: int = MAX_TOOLS_PER_PROTOCOL_SERVER,
) -> BridgedCatalogue:
    """Return what ``servers`` contribute through ``adapter``, with the reasons for the rest.

    Never raises for anything a server did. A server that is down, answers
    nonsense, or offers four hundred tools each produces a recorded reason and a
    smaller catalogue, because the alternative is an investigation that does not
    start.
    """
    table = classifications if classifications is not None else ClassificationTable()

    built: list[BridgedCapability] = []
    excluded: list[ExcludedTool] = []
    unavailable: list[BridgeHealth] = []
    discoveries: list[Discovery] = []
    suggestions: list[Classification] = []

    for server in servers:
        discovery, health = await _discover(adapter, server)
        if discovery is None:
            unavailable.append(health or BridgeHealth.down(server, "the server did not answer"))
            continue

        discoveries.append(discovery)
        excluded.extend(discovery.excluded)

        kept, over_cap = discovery.tools[:tool_cap], discovery.tools[tool_cap:]
        for dropped in over_cap:
            excluded.append(
                ExcludedTool(
                    server=server,
                    tool=dropped.tool,
                    reason=ExclusionReason.TOOL_CAP_REACHED,
                    detail=(
                        f"{server} offered {len(discovery.tools)} tools and the per-server "
                        f"cap is {tool_cap}"
                    ),
                )
            )

        for offered in kept:
            suggestion = Classification.suggested(
                offered.qualified_name, declared=offered.declared_side_effect
            )
            suggestions.append(suggestion)
            entry = table.entry(offered.qualified_name)
            decided = entry if entry is not None and entry.classified else suggestion
            built.append(_capability(adapter, offered, decided))

    return BridgedCatalogue(
        capabilities=tuple(built),
        excluded=tuple(excluded),
        unavailable=tuple(unavailable),
        discoveries=tuple(discoveries),
        classifications=table.with_suggestions(suggestions),
    )


async def _discover(
    adapter: ProtocolAdapter, server: str
) -> tuple[Discovery | None, BridgeHealth | None]:
    """Return what ``server`` offers, or ``None`` and why it could not be asked.

    An empty answer is confirmed against ``health`` before it is believed. A
    server that genuinely offers no tools and a server that is unreachable look
    identical from a tool list, and only one of them is something an operator
    can fix.

    An adapter is not supposed to raise here, and this catches anyway. The rule
    that a bridge never fails an investigation has to hold for an adapter
    somebody writes next month as well as for the three written today.
    """
    try:
        discovery = await adapter.discover(server)
    except Exception as error:  # noqa: BLE001 — FR-007 is exactly this catch
        logger.warning("protocols.discovery_failed", server=server, error=str(error))
        return None, BridgeHealth.down(server, str(error))

    if discovery.tools or discovery.excluded:
        return discovery, None

    health = await _health(adapter, server)
    if not health.reachable:
        return None, health
    return discovery, health


async def _health(adapter: ProtocolAdapter, server: str) -> BridgeHealth:
    """Return whether ``server`` answered a health check, never raising."""
    try:
        return await adapter.health(server)
    except Exception as error:  # noqa: BLE001 — a health check that raises is unhealthy
        logger.warning("protocols.health_failed", server=server, error=str(error))
        return BridgeHealth.down(server, str(error))


def _capability(
    adapter: ProtocolAdapter, offered: BridgedTool, classification: Classification
) -> BridgedCapability:
    """Return one external tool as the catalogue will hold it."""
    return BridgedCapability(
        server=offered.server,
        tool=offered.tool,
        kind=adapter.kind,
        classification=classification,
        registered=registered_tool_for(adapter, offered, classification),
        executable=classification.classified,
    )


def registered_tool_for(
    adapter: ProtocolAdapter, offered: BridgedTool, classification: Classification
) -> RegisteredTool:
    """Return the registration a bridged tool enters the catalogue as.

    The same type a decorated function produces, built through the same
    ``build_registration``, so nothing downstream has a way to treat it
    differently even if it wanted to.
    """
    metadata = _metadata(adapter.kind, offered, classification)
    body = (
        _refusing_body(offered, classification)
        if not classification.classified
        else _invoking_body(adapter, offered)
    )
    return build_registration(
        metadata=metadata,
        call=body,
        source_module=f"{adapter.kind.value}:{offered.server}",
        source_qualname=offered.tool,
        input_schema=dict(offered.input_schema) or {"type": "object", "properties": {}},
        output_schema={"type": "object"},
    )


def _metadata(
    kind: ProtocolKind, offered: BridgedTool, classification: Classification
) -> ToolMetadata:
    """Return the declaration a bridged tool is scored, gated, and approved on."""
    level = classification.effective_level
    description = (offered.description or "").strip() or DEFAULT_DESCRIPTION.format(
        server=offered.server
    )
    needs_approval = level.needs_approval
    return ToolMetadata(
        name=offered.catalogue_name,
        display_name=(offered.title.strip() or offered.qualified_name),
        description=description[:MAX_BRIDGED_DESCRIPTION_CHARS],
        tags=(BRIDGED_TAG, kind.value, offered.server),
        evidence_source=offered.server,
        evidence_type=BRIDGED_EVIDENCE_TYPE,
        side_effect_level=level,
        # Never. Nothing here knows whether the server serialises its own calls,
        # and the cost of guessing wrong is concurrent writes against a system
        # we do not model.
        parallel_safe=False,
        requires_approval=needs_approval,
        approval_reason=(
            BRIDGED_APPROVAL_REASON.format(
                qualified=offered.qualified_name, server=offered.server, level=level.value
            )
            if needs_approval
            else ""
        ),
        rollback_plan=(
            BRIDGED_ROLLBACK_PLAN.format(server=offered.server, qualified=offered.qualified_name)
            if needs_approval
            else ""
        ),
        # The top of the scale, stated rather than left blank. A first-party
        # author is required to declare this and the build fails when they do
        # not; a server nobody here controls declares nothing we would act on,
        # so the honest classification is the one that never runs unattended.
        risk_class=UNCLASSIFIED_RISK_CLASS if needs_approval else "",
    )


def _refusing_body(offered: BridgedTool, classification: Classification) -> Any:
    """Return a body that refuses before anything reaches the server.

    The refusal happens here rather than at a gate above, so there is no path —
    a direct ``invoke``, a sub-agent with its own tool map, a future runtime —
    on which an unclassified tool runs because somebody forgot the check.
    """
    del classification

    async def refuse(**arguments: Any) -> CapabilityResult:
        del arguments
        from capabilities.protocols.classification import UNCLASSIFIED_REFUSAL

        return CapabilityResult.failed(
            offered.catalogue_name,
            CapabilityErrorClass.PERMISSION_DENIED,
            UNCLASSIFIED_REFUSAL.format(name=offered.qualified_name),
            detail=(
                f"the {offered.server} server declared "
                f"{offered.declared_side_effect or 'nothing'}, which is a suggestion; "
                f"until an operator classifies it the tool is treated as "
                f"{UNCLASSIFIED_LEVEL.value}"
            ),
        )

    return refuse


def _invoking_body(adapter: ProtocolAdapter, offered: BridgedTool) -> Any:
    """Return a body that calls the server and classifies whatever comes back."""

    async def call(**arguments: Any) -> CapabilityResult:
        started = time.perf_counter()
        try:
            produced = await adapter.invoke(offered.server, offered.tool, arguments)
        except Exception as error:  # noqa: BLE001 — a bridge failure is one call's failure
            return CapabilityResult.failed(
                offered.catalogue_name,
                classify_exception(error),
                f"{offered.qualified_name} failed: {type(error).__name__}",
                detail=str(error),
                duration_seconds=time.perf_counter() - started,
            )
        return _as_capability_result(offered, produced, time.perf_counter() - started)

    return call


def _as_capability_result(
    offered: BridgedTool, produced: BridgedResult, duration: float
) -> CapabilityResult:
    """Return the capability-layer result one bridged answer becomes."""
    elapsed = produced.duration_seconds or duration
    if produced.failed:
        return CapabilityResult.failed(
            offered.catalogue_name,
            produced.error_class or CapabilityErrorClass.UPSTREAM_ERROR,
            produced.message or f"{offered.qualified_name} failed",
            detail=produced.detail,
            duration_seconds=elapsed,
        )
    return CapabilityResult.ok(
        offered.catalogue_name,
        value=produced.value,
        evidence=(
            Evidence(
                source=offered.server,
                evidence_type=BRIDGED_EVIDENCE_TYPE,
                summary=f"{offered.qualified_name} answered",
                reference=offered.qualified_name,
            ),
        ),
        duration_seconds=elapsed,
        truncated=produced.truncated,
    )


__all__ = [
    "BRIDGED_APPROVAL_REASON",
    "BRIDGED_EVIDENCE_TYPE",
    "BRIDGED_ROLLBACK_PLAN",
    "BRIDGED_TAG",
    "BridgedCapability",
    "BridgedCatalogue",
    "bridged_catalogue",
    "registered_tool_for",
]
