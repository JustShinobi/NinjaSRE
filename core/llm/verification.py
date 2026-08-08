"""Does this model satisfy the contract an investigation needs, and if not, what does.

``preflight`` next door *describes* a provider: five checks, each passed,
degraded, failed or skipped. This *decides* — and the two are deliberately
separate, because they answer different questions and one of them has to be
willing to say no.

The difference that matters is degraded tool calling. Preflight reports it and
carries on, which is right for a report. Here it is a refusal, because a model
that answers instead of calling the tool will not fail at setup; it will fail
forty seconds into the first investigation, having produced a paragraph of
plausible prose where an evidence-backed finding should be, and the operator will
conclude the platform is broken. Verifying it at setup turns a confusing failure
into a clear one.

Degraded *structured* output is the opposite call and for the same reason: a
model reaching structured output through a prompt-and-parse shim does work, it
works today in this codebase, and refusing it would rule out most self-hosted
models. So it is accepted and said out loud.

When the endpoint can enumerate what else it serves, a refusal names the models
that would work. "The model endpoint answered, but not with a model that supports
tool calling; here are the ones it offers that do" is a sentence somebody can act
on in one step, and it is the whole reason this module bothers to ask.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from core.llm.preflight import CheckResult, CheckStatus, PreflightReport, preflight

#: The preflight checks this contract is made of, in the order a failure in one
#: makes the next meaningless. Authentication before tool calling, because a
#: rejected key produces a tool-calling failure that has nothing to do with tools.
_CREDENTIALS = "credentials"
_AUTHENTICATION = "authentication"
_TOOL_CALLING = "tool calling"
_STRUCTURED = "structured output"


@dataclass(frozen=True, slots=True)
class ModelVerdict:
    """Whether the configured model can be used, and what to do if it cannot."""

    provider_id: str
    model_id: str
    satisfied: bool
    #: What the endpoint actually could not do, in a sentence. Empty when
    #: satisfied. Never "verification failed" — that is a restatement, not a
    #: limitation, and the self-check's ``Finding`` would refuse it anyway.
    limitation: str = ""
    #: What to do next. Empty when satisfied.
    remedy: str = ""
    #: The endpoint's other models that would satisfy the contract, where it can
    #: be asked. Empty when it cannot, which is honest rather than encouraging.
    alternatives: tuple[str, ...] = ()
    #: How the working configuration reads in a passing report.
    summary_line: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a check, a route and a bundle read."""
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "satisfied": self.satisfied,
            "limitation": self.limitation,
            "remedy": self.remedy,
            "alternatives": list(self.alternatives),
            "summary": self.summary_line,
        }


def _status(report: PreflightReport, name: str) -> CheckResult | None:
    """Return the named check's result, or ``None`` if it never ran."""
    return next((check for check in report.checks if check.name == name), None)


def contract_verdict(report: PreflightReport, *, alternatives: Sequence[str] = ()) -> ModelVerdict:
    """Turn a preflight report into a decision about whether this model is usable.

    Ordered by which failure makes the others meaningless. A credential that does
    not resolve produces an authentication failure, which produces a tool-calling
    failure; reporting the last of those would send an operator to change models
    when the problem is an unset environment variable.
    """
    offered = tuple(alternatives)

    for name, limitation, remedy in (
        (
            _CREDENTIALS,
            f"the credential for {report.provider_id} does not resolve, so nothing was called",
            (
                f"set the environment variable {report.provider_id} needs, or configure the "
                f"credential through the vault, then verify again"
            ),
        ),
        (
            _AUTHENTICATION,
            (
                f"the {report.provider_id} endpoint did not authenticate this deployment — it "
                f"is reachable, and it rejected the credential presented to it"
            ),
            (
                "check the key and the endpoint are the pair they are meant to be; this is a "
                "credential problem, not a model problem, and changing model will not fix it"
            ),
        ),
    ):
        result = _status(report, name)
        if result is not None and result.status is CheckStatus.FAILED:
            return ModelVerdict(
                provider_id=report.provider_id,
                model_id=report.model_id,
                satisfied=False,
                limitation=_with_detail(limitation, result),
                remedy=remedy,
                alternatives=offered,
            )

    tools = _status(report, _TOOL_CALLING)
    if tools is not None and tools.status is not CheckStatus.PASSED:
        return ModelVerdict(
            provider_id=report.provider_id,
            model_id=report.model_id,
            satisfied=False,
            limitation=_with_detail(
                (
                    f"the {report.provider_id} endpoint answered, but {report.model_id!r} did "
                    f"not call the tool it was given — every investigation this platform runs "
                    f"is a sequence of tool calls, so this model cannot run one"
                ),
                tools,
            ),
            remedy=_model_remedy(offered),
            alternatives=offered,
        )

    structured = _status(report, _STRUCTURED)
    if structured is not None and structured.status is CheckStatus.FAILED:
        return ModelVerdict(
            provider_id=report.provider_id,
            model_id=report.model_id,
            satisfied=False,
            limitation=_with_detail(
                (
                    f"{report.model_id!r} produced no structured output by any mechanism, "
                    f"native or otherwise — the pipeline's stages exchange typed documents "
                    f"and cannot read prose"
                ),
                structured,
            ),
            remedy=_model_remedy(offered),
            alternatives=offered,
        )

    degraded = structured is not None and structured.status is CheckStatus.DEGRADED
    return ModelVerdict(
        provider_id=report.provider_id,
        model_id=report.model_id,
        satisfied=True,
        summary_line=(
            f"{report.model_id} on {report.provider_id} calls tools and returns structure"
            + (
                " (structured output is degraded — reached through a fallback rather than "
                "natively, which works and is slower)"
                if degraded
                else ""
            )
        ),
    )


def _with_detail(sentence: str, result: CheckResult) -> str:
    """Append the check's own detail, where it has one worth reading."""
    return f"{sentence}: {result.detail}" if result.detail else sentence


def _model_remedy(alternatives: Sequence[str]) -> str:
    """Return what to do about a model that cannot meet the contract."""
    if alternatives:
        listed = ", ".join(alternatives)
        return (
            f"point NINJASRE_LLM_MODEL at one of the models this endpoint offers that do "
            f"satisfy the contract: {listed}"
        )
    return (
        "choose a model that supports tool calling. This endpoint could not be asked what "
        "else it serves, so the list has to come from its own documentation"
    )


async def verify_model(
    *,
    run_preflight: Callable[[], Awaitable[PreflightReport]] | None = None,
    list_models: Callable[[], Awaitable[Sequence[str]]] | None = None,
    **binding: Any,
) -> ModelVerdict:
    """Verify the configured provider against the contract, and return the verdict.

    ``run_preflight`` is injected so this is testable and so a caller that has
    already run preflight does not pay for a second set of real calls.
    ``list_models`` is asked only when the verdict is going to be a refusal —
    enumerating models on a working deployment is a round trip nobody needs.
    """
    probe = run_preflight or (lambda: preflight(**binding))
    report = await probe()

    verdict = contract_verdict(report)
    if verdict.satisfied or list_models is None:
        return verdict

    try:
        offered = await list_models()
    except Exception:  # noqa: BLE001 — an endpoint that will not list is still verifiable
        offered = ()

    return contract_verdict(
        report, alternatives=tuple(name for name in offered if name != report.model_id)
    )


__all__ = ["ModelVerdict", "contract_verdict", "verify_model"]
