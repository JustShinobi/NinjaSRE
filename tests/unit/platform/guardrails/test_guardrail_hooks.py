"""What the loop sees when a rule fires on a tool call, going in and coming back.

The shape of the denial is the interesting assertion. A refusal has to be
something the model can reason about rather than an exception, which here means a
``Deny`` value classified ``PERMISSION_DENIED`` — the classification whose
``retryable`` is false. Getting that wrong in either direction is expensive:
classified ``APPROVAL_REQUIRED``, the loop waits for a human who is never
coming; classified as retryable, it repeats the refused call until the budget
runs out.
"""

from __future__ import annotations

import pytest

from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import ALLOW, Deny, HookPoint, Rewrite, ToolContext
from core.capability.metadata import EvidenceType, SideEffectLevel, ToolMetadata
from core.capability.registered import RegisteredTool
from core.capability.result import CapabilityErrorClass, CapabilityResult, Evidence
from core.llm.types import ToolCall
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.hooks import GuardrailHooks, register
from platform.guardrails.rules import parse_ruleset

pytestmark = [pytest.mark.unit]

BLOCKING = """
rules:
  - name: no-private-keys
    action: block
    keywords: ["begin"]
    patterns:
      - '-----BEGIN [A-Z ]{0,20}PRIVATE KEY-----'
"""

REDACTING = """
rules:
  - name: strip-tokens
    action: redact
    keywords: ["tok_"]
    patterns:
      - '\\btok_[A-Za-z0-9]{16,64}\\b'
"""

SECRET = "tok_abcdefghijklmnop1234"
KEY = "-----BEGIN RSA PRIVATE KEY-----"


def hooks_over(document: str) -> GuardrailHooks:
    """Return hooks bound to an engine over one inline ruleset."""
    return GuardrailHooks(engine=GuardrailEngine(ruleset=parse_ruleset(document, source="test")))


def tool_context() -> ToolContext:
    """Return a context naming a capability, which is all the hooks read from it."""
    metadata = ToolMetadata(
        name="datadog_search_logs",
        display_name="Datadog Search Logs",
        description="Search Datadog logs.",
        domain="observability",
        tags=("logs",),
        use_cases=("find why a pod restarted",),
        evidence_source="datadog",
        evidence_type=EvidenceType.LOG,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    registered = RegisteredTool(
        metadata=metadata,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        call=_unused,
        source_module="tests",
        source_qualname="unused",
    )
    return ToolContext(session=None, iteration=1, registered=registered)  # type: ignore[arg-type]


async def _unused(**_arguments: object) -> CapabilityResult:
    raise AssertionError("the hooks never call the capability")


def call(**arguments: object) -> ToolCall:
    """Return a tool call carrying ``arguments``."""
    return ToolCall(id="t1", name="datadog_search_logs", arguments=arguments)


# -- pre_tool_use --------------------------------------------------------------


async def test_a_clean_call_is_allowed_without_a_rewrite() -> None:
    """The overwhelmingly common path, and it must allocate nothing."""
    decision = await hooks_over(REDACTING).pre_tool_use(
        call(query="service:checkout status:error"), tool_context()
    )

    assert decision is ALLOW


async def test_a_blocking_rule_denies_with_a_structured_refusal() -> None:
    """A value the model can route around, not an exception."""
    decision = await hooks_over(BLOCKING).pre_tool_use(call(body=KEY), tool_context())

    assert isinstance(decision, Deny)
    assert decision.classification is CapabilityErrorClass.PERMISSION_DENIED
    assert not decision.classification.retryable
    assert "no-private-keys" in decision.reason


async def test_the_denial_never_quotes_what_it_matched() -> None:
    """The refusal goes into the transcript, which is where the key must not be."""
    decision = await hooks_over(BLOCKING).pre_tool_use(call(body=KEY), tool_context())

    assert isinstance(decision, Deny)
    assert KEY not in decision.reason


async def test_a_redacting_rule_rewrites_the_arguments_and_proceeds() -> None:
    """Redaction lets a legitimate call through with the secret taken out."""
    decision = await hooks_over(REDACTING).pre_tool_use(
        call(query=f"token {SECRET} failed"), tool_context()
    )

    assert isinstance(decision, Rewrite)
    assert SECRET not in decision.arguments["query"]
    assert "[REDACTED]" in decision.arguments["query"]
    assert "strip-tokens" in decision.reason


async def test_a_nested_argument_is_scanned_too() -> None:
    """An exfiltration would use the field nobody is looking at."""
    decision = await hooks_over(REDACTING).pre_tool_use(
        call(payload={"headers": [{"value": SECRET}]}), tool_context()
    )

    assert isinstance(decision, Rewrite)
    assert SECRET not in str(decision.arguments)


async def test_a_non_string_argument_survives_unchanged() -> None:
    """Rewriting must not coerce a limit into a string on its way past."""
    decision = await hooks_over(REDACTING).pre_tool_use(
        call(limit=50, since=None, tags=["a"], text=SECRET), tool_context()
    )

    assert isinstance(decision, Rewrite)
    assert decision.arguments["limit"] == 50
    assert decision.arguments["since"] is None
    assert decision.arguments["tags"] == ["a"]


# -- post_tool_use -------------------------------------------------------------


async def test_a_clean_result_is_returned_unchanged() -> None:
    """``None`` means "keep it", which is what the registry reads."""
    result = CapabilityResult.ok("datadog_search_logs", value={"logs": ["nothing here"]})

    assert await hooks_over(REDACTING).post_tool_use(call(), result, tool_context()) is None


async def test_a_secret_in_a_tool_result_is_redacted_before_it_becomes_evidence() -> None:
    """A secret that reaches evidence is a secret in every backup from then on."""
    result = CapabilityResult.ok(
        "datadog_search_logs",
        value={"logs": [f"auth failed with {SECRET}"]},
        evidence=(
            Evidence(
                source="datadog",
                evidence_type=EvidenceType.LOG,
                summary=f"one line containing {SECRET}",
                reference="datadog:query-1",
            ),
        ),
    )

    redacted = await hooks_over(REDACTING).post_tool_use(call(), result, tool_context())

    assert redacted is not None
    assert SECRET not in str(redacted.value)
    assert SECRET not in redacted.evidence[0].summary
    assert redacted.evidence[0].reference == "datadog:query-1"


async def test_a_secret_in_an_error_message_is_redacted_too() -> None:
    """A failure message is a string a capability wrote, with the same risks."""
    result = CapabilityResult.failed(
        "datadog_search_logs",
        CapabilityErrorClass.UPSTREAM_ERROR,
        f"rejected credentials {SECRET}",
        detail=f"header carried {SECRET}",
    )

    redacted = await hooks_over(REDACTING).post_tool_use(call(), result, tool_context())

    assert redacted is not None
    assert redacted.error is not None
    assert SECRET not in redacted.error.message
    assert SECRET not in redacted.error.detail


async def test_post_tool_use_never_blocks() -> None:
    """The call already happened; refusing its result only means the loop repeats it."""
    result = CapabilityResult.ok("datadog_search_logs", value={"body": KEY})

    redacted = await hooks_over(BLOCKING).post_tool_use(call(), result, tool_context())

    assert redacted is not None
    assert KEY not in str(redacted.value)


# -- registration --------------------------------------------------------------


def test_registration_attaches_both_points() -> None:
    """One call wires the whole feature into a loop."""
    registry = HookRegistry()

    register(registry, engine=GuardrailEngine(ruleset=parse_ruleset(BLOCKING, source="t")))

    assert [hook.name for hook in registry.hooks_at(HookPoint.PRE_TOOL_USE)] == [
        "guardrails.pre_tool_use"
    ]
    assert [hook.name for hook in registry.hooks_at(HookPoint.POST_TOOL_USE)] == [
        "guardrails.post_tool_use"
    ]


async def test_guardrails_run_before_a_later_hook_can_rewrite_past_them() -> None:
    """Order is negative so a refused call never costs a human an approval prompt."""
    registry = HookRegistry()

    async def approvals(_call: ToolCall, _context: ToolContext) -> None:
        raise AssertionError("a blocked call must not reach the approval gate")

    register(registry, engine=GuardrailEngine(ruleset=parse_ruleset(BLOCKING, source="t")))
    registry.register(HookPoint.PRE_TOOL_USE, approvals, name="approvals", order=10)

    decision, _arguments, failures = await registry.run_pre_tool_use(call(body=KEY), tool_context())

    assert isinstance(decision, Deny)
    assert failures == ()
