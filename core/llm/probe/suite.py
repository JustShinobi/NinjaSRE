"""Making the model do each thing, and writing down whether it did.

Every probe is a small prompt with a trivial task in it. That is deliberate: a
failure here has to mean "the mechanism does not work", never "the model found
the question hard", so nothing asks the model to think.

Two of the five are measurements rather than yes-or-no questions, and both cost
more than one call.

**Usable context** is bisected between nothing and the advertised window. A
quantised build routinely accepts far less than its card claims, and the figure
matters: it is what decides when the transcript is compacted, and compacting too
late is a rejected turn in the middle of an incident.

**The schema limit** is a doubling ladder. A model that emits a clean tool call
with two schemas in front of it and prose with sixteen has a limit, and the only
way to find it is to show it sixteen. The ladder stops at the first rung it
fails, so a model with no limit pays six calls and one with a low limit pays
fewer.

The whole suite is bounded at around twenty small calls, and its result is
cached against the model's identity, so an operator pays for it once per model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from config.constants.investigation import MAX_AGENT_TOOL_SCHEMAS
from config.constants.llm import (
    CHARACTERS_PER_TOKEN_ESTIMATE,
    MODEL_PROBE_CONTEXT_RESOLUTION_TOKENS,
    MODEL_PROBE_CONTEXT_STEPS,
    MODEL_PROBE_MAX_OUTPUT_TOKENS,
)
from core.llm.probe.behaviours import Behaviour, BehaviourStatus
from core.llm.probe.cache import ProbeCache
from core.llm.probe.report import (
    BehaviourResult,
    EndpointProbe,
    ModelIdentity,
    ModelProbe,
)
from core.llm.types import (
    InvokeRequest,
    LLMClient,
    Message,
    Role,
    StreamEventKind,
    StructuredMechanism,
    ToolSchema,
)

#: The probe tool. Trivial on purpose, and named so a call to it in somebody's
#: request log is obviously not an investigation.
_PROBE_TOOL_PREFIX = "ninjasre_probe_echo"

_PROBE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"status": {"type": "string"}, "checked": {"type": "boolean"}},
    "required": ["status", "checked"],
}

#: Filler for the context measurement. Prose rather than a repeated character
#: because a tokeniser collapses a run of one character and would let the probe
#: report a window several times the real one.
_FILLER = (
    "The checkout service returned a gateway error while the payments service stayed "
    "healthy, and the deployment before it changed only a configuration value. "
)


def _probe_tool(index: int) -> ToolSchema:
    """Return one probe tool, distinct from the others only in its name."""
    suffix = "" if index == 0 else f"_{index}"
    return ToolSchema(
        name=f"{_PROBE_TOOL_PREFIX}{suffix}",
        description="Echo the supplied token back. Call this exactly once.",
        parameters={
            "type": "object",
            "properties": {"token": {"type": "string", "description": "The token to echo."}},
            "required": ["token"],
        },
    )


def _ask(text: str, *, tools: tuple[ToolSchema, ...] = ()) -> InvokeRequest:
    return InvokeRequest(
        messages=(Message(role=Role.USER, text=text),),
        tools=tools,
        max_output_tokens=MODEL_PROBE_MAX_OUTPUT_TOKENS,
    )


async def _tool_calling(client: LLMClient) -> BehaviourResult:
    result = await client.invoke(
        _ask("Call the echo tool with the token 'probe'.", tools=(_probe_tool(0),))
    )
    if not result.succeeded:
        return BehaviourResult(
            Behaviour.TOOL_CALLING, BehaviourStatus.FAILED, result.failure_message
        )
    if not result.tool_calls:
        return BehaviourResult(
            Behaviour.TOOL_CALLING,
            BehaviourStatus.FAILED,
            "the model answered in prose instead of calling the tool it was given",
        )
    return BehaviourResult(
        Behaviour.TOOL_CALLING, BehaviourStatus.PASSED, result.tool_calls[0].name
    )


async def _schema_adherence(client: LLMClient) -> BehaviourResult:
    result = await client.invoke_structured(
        _ask("Report status 'ok' and checked true."), schema=_PROBE_SCHEMA
    )
    if not result.succeeded:
        return BehaviourResult(
            Behaviour.SCHEMA_ADHERENCE, BehaviourStatus.FAILED, result.failure_message
        )
    if result.structured is None:
        return BehaviourResult(
            Behaviour.SCHEMA_ADHERENCE,
            BehaviourStatus.FAILED,
            "no document came back by any mechanism, native or otherwise",
        )
    missing = [key for key in ("status", "checked") if key not in result.structured]
    if missing:
        return BehaviourResult(
            Behaviour.SCHEMA_ADHERENCE,
            BehaviourStatus.DEGRADED,
            f"the document omitted {', '.join(missing)}",
        )
    if result.structured_mechanism in {
        StructuredMechanism.TOOL_COERCION,
        StructuredMechanism.PROSE_PARSING,
    }:
        return BehaviourResult(
            Behaviour.SCHEMA_ADHERENCE,
            BehaviourStatus.DEGRADED,
            f"reached through {result.structured_mechanism.value} rather than natively",
        )
    return BehaviourResult(Behaviour.SCHEMA_ADHERENCE, BehaviourStatus.PASSED)


async def _multi_tool_turn(client: LLMClient) -> BehaviourResult:
    tools = (_probe_tool(0), _probe_tool(1))
    result = await client.invoke(
        _ask("Call both tools, once each, with the token 'probe'.", tools=tools)
    )
    if not result.succeeded:
        return BehaviourResult(
            Behaviour.MULTI_TOOL_TURN, BehaviourStatus.FAILED, result.failure_message
        )
    if len(result.tool_calls) >= 2:
        return BehaviourResult(Behaviour.MULTI_TOOL_TURN, BehaviourStatus.PASSED)
    if result.tool_calls:
        return BehaviourResult(
            Behaviour.MULTI_TOOL_TURN,
            BehaviourStatus.DEGRADED,
            "asked for two tools, offered one call; the loop will serialise them",
        )
    return BehaviourResult(
        Behaviour.MULTI_TOOL_TURN,
        BehaviourStatus.FAILED,
        "two tools on the turn produced no call at all",
    )


async def _streaming(client: LLMClient) -> BehaviourResult:
    text = ""
    failure = ""
    async for event in client.stream(_ask("Count from one to five.")):
        if event.kind is StreamEventKind.TEXT_DELTA:
            text += event.text
        elif event.kind is StreamEventKind.ERROR:
            failure = event.detail
    if failure:
        return BehaviourResult(Behaviour.STREAMING, BehaviourStatus.FAILED, failure)
    if not text:
        return BehaviourResult(
            Behaviour.STREAMING, BehaviourStatus.DEGRADED, "the stream carried no text"
        )
    return BehaviourResult(Behaviour.STREAMING, BehaviourStatus.PASSED, f"{len(text)} characters")


#: What every padded probe carries besides its filler. Measured and subtracted
#: rather than added on top, so a request built for the advertised window is the
#: advertised window — a probe that overshot by its own instruction would report
#: every model as overstating its context, including the ones that do not.
_PADDING_INSTRUCTION = "\nReply with the single word: ready."


def _padded(tokens: int) -> InvokeRequest:
    """Return a request whose prompt is about ``tokens`` tokens long."""
    characters = max(
        tokens * CHARACTERS_PER_TOKEN_ESTIMATE - len(_PADDING_INSTRUCTION),
        0,
    )
    filler = (_FILLER * (characters // len(_FILLER) + 1))[:characters]
    return _ask(f"{filler}{_PADDING_INSTRUCTION}")


async def _accepts(client: LLMClient, tokens: int) -> bool:
    """Return whether a prompt of about ``tokens`` tokens comes back at all."""
    return (await client.invoke(_padded(tokens))).succeeded


async def _usable_context(
    client: LLMClient,
    *,
    advertised: int,
    steps: int,
) -> tuple[BehaviourResult, int]:
    """Return how much context the model actually accepts, and how that reads.

    Bisected downward from the advertised figure. The lower bound starts at zero
    rather than at some assumed minimum: an endpoint serving a model it never
    loaded refuses everything, and reporting that as "usable context: 4096" would
    send the operator to the wrong problem.
    """
    if advertised <= 0:
        return (
            BehaviourResult(
                Behaviour.USABLE_CONTEXT,
                BehaviourStatus.SKIPPED,
                "the registry row advertises no context window to measure against",
            ),
            0,
        )

    if await _accepts(client, advertised):
        return (
            BehaviourResult(
                Behaviour.USABLE_CONTEXT,
                BehaviourStatus.PASSED,
                f"accepted a prompt of about {advertised} tokens, as advertised",
            ),
            advertised,
        )

    low, high = 0, advertised
    for _ in range(max(steps, 1)):
        if high - low <= MODEL_PROBE_CONTEXT_RESOLUTION_TOKENS:
            break
        middle = (low + high) // 2
        if await _accepts(client, middle):
            low = middle
        else:
            high = middle

    if low == 0:
        return (
            BehaviourResult(
                Behaviour.USABLE_CONTEXT,
                BehaviourStatus.FAILED,
                "the endpoint refused every prompt, including the smallest probed",
            ),
            0,
        )
    return (
        BehaviourResult(
            Behaviour.USABLE_CONTEXT,
            BehaviourStatus.DEGRADED,
            f"accepted about {low} tokens against an advertised {advertised}",
        ),
        low,
    )


def _ladder(ceiling: int) -> tuple[int, ...]:
    """Return the schema counts to try, smallest first, ending at ``ceiling``."""
    rungs: list[int] = []
    count = 2
    while count < ceiling:
        rungs.append(count)
        count *= 2
    rungs.append(ceiling)
    return tuple(rungs)


async def _schema_limit(client: LLMClient, *, ceiling: int) -> int:
    """Return the largest number of schemas the model still calls a tool with.

    Stops at the first rung it fails. A model with no limit pays the whole
    ladder — six calls at the shipped ceiling — and one with a low limit pays
    two, which is the right way round.
    """
    demonstrated = 1
    for count in _ladder(ceiling):
        tools = tuple(_probe_tool(index) for index in range(count))
        result = await client.invoke(
            _ask("Call the echo tool with the token 'probe'.", tools=tools)
        )
        if not result.succeeded or not result.tool_calls:
            return demonstrated
        demonstrated = count
    return demonstrated


async def probe_model(
    client: LLMClient,
    *,
    advertised_context_tokens: int,
    fingerprint: str = "",
    context_steps: int = MODEL_PROBE_CONTEXT_STEPS,
    schema_ceiling: int = MAX_AGENT_TOOL_SCHEMAS,
) -> ModelProbe:
    """Return what ``client``'s model can actually do.

    ``advertised_context_tokens`` is what the registry row claims, and it is an
    input rather than something read off the client so that a caller replaying a
    recorded model can probe against the figure that model's row carried.

    Behaviours that a prior failure makes meaningless are skipped rather than
    run: asking a model that will not call a tool how many schemas it can hold
    produces a second copy of the same answer at six times the cost.
    """
    tool_calling = await _tool_calling(client)
    schema = await _schema_adherence(client)

    if tool_calling.status is BehaviourStatus.PASSED:
        multi_tool = await _multi_tool_turn(client)
        demonstrated = await _schema_limit(client, ceiling=schema_ceiling)
    else:
        multi_tool = BehaviourResult(
            Behaviour.MULTI_TOOL_TURN,
            BehaviourStatus.SKIPPED,
            "the model does not call one tool, so two is not a question",
        )
        demonstrated = schema_ceiling

    streaming = await _streaming(client)
    context, usable = await _usable_context(
        client, advertised=advertised_context_tokens, steps=context_steps
    )

    return ModelProbe(
        identity=ModelIdentity(
            provider_id=client.provider_id,
            model_id=client.model_id,
            fingerprint=fingerprint,
        ),
        behaviours=(tool_calling, schema, multi_tool, streaming, context),
        usable_context_tokens=usable,
        advertised_context_tokens=advertised_context_tokens,
        max_tool_schemas=min(demonstrated, schema_ceiling),
    )


@dataclass(frozen=True, slots=True)
class ProbeTarget:
    """One model an endpoint serves, and what its row claims about it."""

    client: LLMClient
    advertised_context_tokens: int
    fingerprint: str = ""


async def probe_endpoint(
    targets: Sequence[ProbeTarget],
    *,
    provider_id: str = "",
    cache: ProbeCache | None = None,
) -> EndpointProbe:
    """Return what every model this endpoint serves can actually do.

    ``cache`` is consulted per model and written back, so an operator who adds a
    sixth model to their server pays for one probe rather than six. A cached
    entry whose fingerprint no longer matches is a miss, which is what makes a
    model pulled again underneath a running deployment get re-probed.
    """
    probes: list[ModelProbe] = []
    for target in targets:
        identity = ModelIdentity(
            provider_id=target.client.provider_id,
            model_id=target.client.model_id,
            fingerprint=target.fingerprint,
        )
        stored = cache.get(identity) if cache is not None else None
        if stored is not None:
            probes.append(stored)
            continue
        probe = await probe_model(
            target.client,
            advertised_context_tokens=target.advertised_context_tokens,
            fingerprint=target.fingerprint,
        )
        if cache is not None:
            cache.put(probe)
        probes.append(probe)

    return EndpointProbe(
        provider_id=provider_id or (targets[0].client.provider_id if targets else ""),
        models=tuple(probes),
    )


__all__ = ["ProbeTarget", "probe_endpoint", "probe_model"]
