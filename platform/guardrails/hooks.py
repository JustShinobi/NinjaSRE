"""Binding the engine to the two points in the loop where a tool call passes.

Arguments and results are genuinely different threat surfaces, which is why
there are two hooks rather than one with a flag.

**``pre_tool_use`` guards exfiltration.** The realistic attack is a
prompt-injected log line persuading the model to put a secret it read in one
tool's output into another tool's arguments — a search query, a webhook body, a
commit message. So a ``block`` here refuses the call, and a ``redact`` here
rewrites the arguments and lets it proceed.

**``post_tool_use`` guards poisoning and persistence.** A tool result becomes
evidence, and evidence is persisted, summarised, and eventually rendered. A
secret that gets into evidence is a secret in the database, so results are
redacted before they ever become one. Nothing is blocked here: the call already
happened, and refusing its result would only mean the loop repeats it.

A denial is a *value*, not an exception. ``Deny`` goes back to the model
classified ``PERMISSION_DENIED``, which is the classification that says "do not
retry this" — as opposed to ``APPROVAL_REQUIRED``, which says "a human is
looking at it". The model can route around one and should wait for the other,
and conflating them is how an agent ends up either spinning or giving up.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import ALLOW, Deny, HookPoint, HookResult, Rewrite, ToolContext
from core.capability.result import CapabilityErrorClass, CapabilityResult
from core.llm.types import ToolCall
from platform.guardrails.audit import GuardrailAuditor, log_fields
from platform.guardrails.engine import GuardrailEngine, ScanMatch, ScanResult
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The names the hooks register under, so an ablation can unregister exactly
#: these and a trace can say which hook rewrote an argument.
PRE_TOOL_USE_HOOK = "guardrails.pre_tool_use"
POST_TOOL_USE_HOOK = "guardrails.post_tool_use"

#: Where in the loop a scan happened, recorded on every audit line.
PRE_TOOL_USE_LOCATION = "pre_tool_use"
POST_TOOL_USE_LOCATION = "post_tool_use"

#: Guardrails run before approvals. A call that is going to be refused outright
#: should not first cost a human the interruption of being asked about it.
HOOK_ORDER = -100


class GuardrailHooks:
    """The engine, the auditor, and the tenant the two hooks record against.

    A class rather than two closures because both hooks need the same three
    things, and passing them separately is how one of them ends up wired to a
    different engine than the other.
    """

    __slots__ = ("_auditor", "_engine", "_org_id", "_tally", "_team_id")

    def __init__(
        self,
        *,
        engine: GuardrailEngine,
        auditor: GuardrailAuditor | None = None,
        org_id: str = "",
        team_id: str = "",
    ) -> None:
        self._engine = engine
        self._auditor = auditor
        self._org_id = org_id
        self._team_id = team_id
        self._tally: dict[str, int] = {}

    def trace_summary(self) -> dict[str, Any]:
        """Return what the run trace records about what these hooks did.

        Rule names and counts. A run whose trace says ``no-private-keys: 3`` is
        a run somebody should look at, and that sentence is safe to put in front
        of anyone who can read the trace — which is a wider audience than the
        one entitled to what the rule matched.
        """
        return {
            "rules_fired": dict(self._tally),
            "matches": sum(self._tally.values()),
            "audit_only": self._engine.audit_only,
        }

    async def pre_tool_use(self, call: ToolCall, context: ToolContext) -> HookResult:
        """Return whether ``call`` may run, with its arguments rewritten if needed."""
        scanned, result = _scan_arguments(self._engine, call.arguments)
        if result.clean:
            return ALLOW

        await self._record(result, location=PRE_TOOL_USE_LOCATION, capability=context.capability)

        if result.blocked:
            return Deny(
                reason=result.denial_reason(),
                classification=CapabilityErrorClass.PERMISSION_DENIED,
            )
        if scanned == dict(call.arguments):
            return ALLOW
        return Rewrite(
            arguments=scanned,
            reason=f"guardrail redaction: {', '.join(result.rules_fired)}",
        )

    async def post_tool_use(
        self, call: ToolCall, result: CapabilityResult, context: ToolContext
    ) -> CapabilityResult | None:
        """Return ``result`` with any matched content redacted, or ``None``.

        ``None`` means "unchanged", which is the common case and costs nothing.
        """
        del call
        rendered, scan = _scan_result(self._engine, result)
        if scan.clean:
            return None

        await self._record(scan, location=POST_TOOL_USE_LOCATION, capability=context.capability)
        return rendered

    def register(self, hooks: HookRegistry) -> HookRegistry:
        """Attach both hooks to ``hooks`` and return it."""
        hooks.register(
            HookPoint.PRE_TOOL_USE,
            self.pre_tool_use,
            name=PRE_TOOL_USE_HOOK,
            order=HOOK_ORDER,
        )
        hooks.register(
            HookPoint.POST_TOOL_USE,
            self.post_tool_use,
            name=POST_TOOL_USE_HOOK,
            order=HOOK_ORDER,
        )
        return hooks

    async def _record(self, result: ScanResult, *, location: str, capability: str) -> None:
        """Tally the scan, log it, and audit it when there is somewhere to audit to."""
        for match in result.matches:
            self._tally[match.rule] = self._tally.get(match.rule, 0) + 1
        logger.info(
            "guardrails.matched",
            capability=capability,
            **log_fields(result, location=location),
        )
        if self._auditor is None or not self._org_id:
            return
        await self._auditor.record_scan(
            result,
            org_id=self._org_id,
            team_id=self._team_id,
            location=f"{location}:{capability}",
        )


def register(
    hooks: HookRegistry,
    *,
    engine: GuardrailEngine,
    auditor: GuardrailAuditor | None = None,
    org_id: str = "",
    team_id: str = "",
) -> HookRegistry:
    """Attach the guardrail hooks to ``hooks`` and return it."""
    return GuardrailHooks(engine=engine, auditor=auditor, org_id=org_id, team_id=team_id).register(
        hooks
    )


def _scan_arguments(
    engine: GuardrailEngine, arguments: Mapping[str, Any]
) -> tuple[dict[str, Any], ScanResult]:
    """Return the arguments after redaction, and the combined scan.

    Every string is scanned wherever it is nested. A schema-aware walk would
    miss the field somebody adds next week, which is the field an exfiltration
    would use precisely because nobody is looking at it.
    """
    matches: list[ScanMatch] = []
    blocked = False
    blocking: list[str] = []
    truncated = False

    def walk(value: Any) -> Any:
        nonlocal blocked, truncated
        if isinstance(value, str):
            scan = engine.scan(value)
            matches.extend(scan.matches)
            blocked = blocked or scan.blocked
            blocking.extend(scan.blocking_rules)
            truncated = truncated or scan.truncated or scan.match_limit_reached
            return scan.text
        if isinstance(value, Mapping):
            return {key: walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, tuple):
            return tuple(walk(item) for item in value)
        return value

    rewritten = {key: walk(value) for key, value in arguments.items()}
    combined = ScanResult(
        text="",
        matches=tuple(matches),
        blocked=blocked,
        blocking_rules=tuple(dict.fromkeys(blocking)),
        truncated=truncated,
    )
    return rewritten, combined


def _scan_result(
    engine: GuardrailEngine, result: CapabilityResult
) -> tuple[CapabilityResult, ScanResult]:
    """Return ``result`` with everything readable in it redacted, and the scan.

    The value, the evidence summaries and references, and the error message all
    go through one walk, so a secret in any of them produces one scan and one
    audit line rather than three that have to be correlated afterwards.
    """
    parts: dict[str, Any] = {
        "value": result.value,
        "evidence": [
            {"summary": item.summary, "reference": item.reference} for item in result.evidence
        ],
        "error": (
            None
            if result.error is None
            else {"message": result.error.message, "detail": result.error.detail}
        ),
    }

    rewritten, scan = _scan_arguments(engine, parts)
    if scan.clean:
        return result, scan

    evidence = tuple(
        replace(item, summary=redacted["summary"], reference=redacted["reference"])
        for item, redacted in zip(result.evidence, rewritten["evidence"])
    )
    error = result.error
    if error is not None:
        error = replace(
            error,
            message=rewritten["error"]["message"],
            detail=rewritten["error"]["detail"],
        )

    return replace(result, value=rewritten["value"], evidence=evidence, error=error), scan


__all__ = [
    "HOOK_ORDER",
    "POST_TOOL_USE_HOOK",
    "POST_TOOL_USE_LOCATION",
    "PRE_TOOL_USE_HOOK",
    "PRE_TOOL_USE_LOCATION",
    "GuardrailHooks",
    "register",
]
