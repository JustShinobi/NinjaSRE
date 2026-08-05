"""EXPERIMENTAL. A runtime backed by a vendor agent SDK, and what it cannot do.

This adapter exists for one reason: a team already running on a vendor's agent
SDK should be able to point NinjaSRE at their existing setup while they migrate,
rather than choosing between the two on day one. It is never the default, it is
selected only by an explicit environment variable, and the guard in
``core.agent.guard`` refuses to let it produce a published number.

**What it cannot enforce.** In this runtime the loop belongs to the vendor.
There is no seam to insert control flow into, so every guardrail that is a
property of the loop's control flow is simply absent:

``MAX_INVESTIGATION_LOOPS``
    The SDK decides when to stop. A run can exceed the iteration ceiling and
    nothing here will notice, let alone prevent it.

``MAX_STAGNANT_ITERATIONS``
    There is no point at which "this iteration produced no new evidence" can be
    evaluated and acted on, so a run can spin on the same call until the vendor's
    own limits end it.

The in-run duplicate cache
    Repeated calls are re-executed. The model is never told it already holds a
    result.

The context budget
    Eviction and truncation happen inside the vendor's session by whatever
    policy it uses. No eviction is recorded, so a missing observation cannot be
    explained afterwards.

``pre_tool_use`` denial and rewrite
    Approval gating and argument masking both depend on being able to refuse or
    change a call between the model asking and the tool running. This adapter
    has no such point, which means **Articles III and IV cannot be enforced
    here**. That is the most serious gap on this list and the reason the flag
    exists rather than a configuration file entry.

Trajectory comparability
    Turn records are reconstructed from what the SDK reports rather than
    observed as they happen, so a trace from this runtime is not replayable to
    the standard ``SC-008`` sets.

**The dependency is optional and not installed by default.** Provider
neutrality means a deployment where nothing leaves the operator's
infrastructure installs no vendor packages and is still fully functional
(Article VI); an adapter that forced one into the dependency tree would break
that for everybody in order to serve the few teams that want it. Without the
extra, this runtime reports its own unavailability as a failed result rather
than raising — a caller that selected it should learn that in the same shape
every other failure arrives in.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Final

from config.constants.investigation import NINJASRE_RUNTIME_ENV, RUNTIME_CLAUDE_SDK
from core.agent.runtime_port import RunRequest, RunResult, RunStatus
from core.agent.session import Session, SessionStatus
from core.llm.types import Message, Role
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The distribution this adapter needs. Deliberately not a dependency of the
#: package, and deliberately not in the vendor-SDK deny-list either: that list
#: guards model clients outside ``core/llm/``, and this is an agent framework
#: rather than a model client.
SDK_MODULE: Final[str] = "claude_agent_sdk"

#: What this runtime cannot enforce, as data rather than as prose, so a console
#: or a CLI can show an operator the list before they select it.
UNENFORCEABLE_GUARDRAILS: Final[tuple[str, ...]] = (
    "the iteration ceiling (MAX_INVESTIGATION_LOOPS)",
    "the stagnation breaker (MAX_STAGNANT_ITERATIONS)",
    "the in-run duplicate tool-call cache",
    "the context budget, its eviction policy, and its eviction record",
    "pre_tool_use denial — approval gating (Article III)",
    "pre_tool_use rewriting — argument masking (Article IV)",
    "per-iteration trace records sufficient for offline replay",
)

_UNAVAILABLE = (
    "The {module!r} package is not installed, so the experimental "
    "{runtime!r} runtime cannot start. It is an optional extra on purpose: a "
    "deployment with no permitted egress installs no vendor packages and stays "
    "fully functional. Unset {env} to use the canonical runtime."
)


class ExperimentalRuntimeError(RuntimeError):
    """The experimental runtime could not be started or driven."""


@dataclass(slots=True)
class ClaudeAgentSdkRuntime:
    """EXPERIMENTAL. Satisfies ``Runtime``; never produces a published number.

    ``is_canonical`` is ``False`` and is what the benchmark guard reads. Nothing
    else about this class is load-bearing, and that is the intent: the port was
    defined in Wave 0 precisely so this could exist without becoming something
    the rest of the system depends on.
    """

    model: str = ""
    _sessions: dict[str, Session] | None = None

    @property
    def name(self) -> str:
        """Return the identifier this runtime is recorded under."""
        return RUNTIME_CLAUDE_SDK

    @property
    def is_canonical(self) -> bool:
        """Return ``False``. This runtime's results are never published."""
        return False

    @property
    def unenforceable_guardrails(self) -> tuple[str, ...]:
        """Return the guardrails this runtime cannot apply."""
        return UNENFORCEABLE_GUARDRAILS

    # -- the port -------------------------------------------------------------

    async def run(self, request: RunRequest) -> RunResult:
        """Return the outcome of one investigation driven by the vendor SDK."""
        session = Session(
            id=request.session_id or "sdk-run",
            objective=request.objective,
            system_prompt=request.system_prompt,
            alert_source=request.alert_source,
            context=dict(request.context),
            max_iterations=request.max_iterations,
            wall_clock_seconds=request.wall_clock_seconds,
            context_budget_tokens=request.context_budget_tokens,
        )
        session.append(Message(role=Role.USER, text=request.objective))
        return await self.resume(session)

    async def resume(self, session: Session) -> RunResult:
        """Return the outcome of continuing ``session`` under the vendor SDK."""
        logger.warning(
            "agent.experimental_runtime",
            runtime=self.name,
            session_id=session.id,
            unenforceable=len(UNENFORCEABLE_GUARDRAILS),
        )

        sdk = _load_sdk()
        if sdk is None:
            session.status = SessionStatus.FAILED
            message = _UNAVAILABLE.format(
                module=SDK_MODULE, runtime=self.name, env=NINJASRE_RUNTIME_ENV
            )
            return RunResult(
                session=session, status=RunStatus.FAILED, answer=message, failure=message
            )

        answer = await self._drive(sdk, session)
        session.append(Message(role=Role.ASSISTANT, text=answer))
        session.status = SessionStatus.COMPLETED
        return RunResult(session=session, status=RunStatus.COMPLETED, answer=answer)

    async def cancel(self, session_id: str) -> None:
        """Ask the run to stop.

        Best-effort and not a guarantee: interruption is the SDK's to offer, and
        what it does with a request mid-tool-call is outside this adapter's
        control. That is one more reason a cancelled run here is not resumable
        to the standard the canonical loop meets.
        """
        logger.info("agent.experimental_cancel_requested", session_id=session_id)

    async def _drive(self, sdk: Any, session: Session) -> str:
        """Return the answer the SDK produced for ``session``.

        Kept to one call into the vendor's surface on purpose. Every line of
        translation written here is a line that has to keep working against a
        dependency this project does not control and does not test against.
        """
        query = getattr(sdk, "query", None)
        if query is None:
            raise ExperimentalRuntimeError(
                f"{SDK_MODULE} exposes no 'query' entry point; this adapter was "
                "written against a version that did"
            )

        collected: list[str] = []
        async for item in query(prompt=session.objective):
            text = getattr(item, "text", None)
            if isinstance(text, str) and text:
                collected.append(text)
        return "\n".join(collected)


def _load_sdk() -> Any | None:
    """Return the vendor SDK module, or ``None`` when the extra is not installed."""
    try:
        return importlib.import_module(SDK_MODULE)
    except ImportError:
        return None


__all__ = [
    "SDK_MODULE",
    "UNENFORCEABLE_GUARDRAILS",
    "ClaudeAgentSdkRuntime",
    "ExperimentalRuntimeError",
]
