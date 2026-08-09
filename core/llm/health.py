"""Is the endpoint answering, and is it the endpoint's fault or the model's.

The distinction this module exists for is the one an operator's next action
depends on. "The investigation failed" sends somebody to look at everything. "The
endpoint at ``http://tower.lan:11434`` did not answer within fifteen seconds"
sends them to the machine; "the endpoint answered and the model would not call
the tool it was given" sends them to a different set of weights. Those are
different afternoons.

Every failure class the provider layer already knows describes the *endpoint* —
a rejected key, a rate limit, a context window, a model the server does not
hold. ``MODEL_BEHAVIOUR`` is the one that describes the weights, and this module
is where the two are told apart and said out loud.

The check itself is deliberately trivial and deliberately impatient: it asks for
one word, on a budget far below the call budget, because the question is whether
the endpoint answers at all and an endpoint that needs a minute to say "yes" has
already answered "no".
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from config.constants.llm import ENDPOINT_HEALTH_TIMEOUT_SECONDS
from core.llm.failures import FailureClass
from core.llm.types import InvokeRequest, LLMClient, Message, Role

#: What the health probe asks for. One word, so the reply costs nothing and a
#: model that produces a paragraph has still answered the question being asked.
_PROBE = "Reply with the single word: ready."

_MAX_PROBE_OUTPUT_TOKENS = 16


class EndpointStatus(StrEnum):
    """What a health check found, in the terms an operator acts on."""

    #: The endpoint answered. Whether the *model* is any good is a separate
    #: question, and the probe deliberately does not conflate them.
    REACHABLE = "reachable"
    #: Nothing came back, or the transport failed. Look at the machine.
    UNREACHABLE = "unreachable"
    #: It answered and rejected the credential. Look at the key, not the model.
    UNAUTHENTICATED = "unauthenticated"
    #: It answered and does not hold this model. Pull it, or name another.
    MODEL_MISSING = "model_missing"
    #: It answered within its budget and the model did not do its job.
    MODEL_MISBEHAVING = "model_misbehaving"


#: How a failure class reads as an endpoint verdict. Everything not named here
#: is the endpoint failing to serve, which is ``UNREACHABLE`` — including
#: ``UNKNOWN``, because an unrecognised failure is not evidence that the model
#: is at fault and blaming the weights for it would send somebody to change
#: something that was working.
_VERDICTS: dict[FailureClass, EndpointStatus] = {
    FailureClass.AUTH: EndpointStatus.UNAUTHENTICATED,
    FailureClass.MODEL_UNAVAILABLE: EndpointStatus.MODEL_MISSING,
    FailureClass.MODEL_BEHAVIOUR: EndpointStatus.MODEL_MISBEHAVING,
}


@dataclass(frozen=True, slots=True)
class EndpointHealth:
    """One health check, and how long it took to find out."""

    status: EndpointStatus
    endpoint: str
    model_id: str = ""
    detail: str = ""
    elapsed_seconds: float = 0.0

    @property
    def usable(self) -> bool:
        """Return whether an investigation could be started against this endpoint."""
        return self.status is EndpointStatus.REACHABLE

    @property
    def blames_the_endpoint(self) -> bool:
        """Return whether the fault is the endpoint's rather than the model's.

        The property the whole module is for. A caller showing an operator one
        sentence should show a different one depending on this.
        """
        return self.status in {
            EndpointStatus.UNREACHABLE,
            EndpointStatus.UNAUTHENTICATED,
            EndpointStatus.MODEL_MISSING,
        }

    def render(self) -> str:
        """Return the one line a surface prints."""
        suffix = f": {self.detail}" if self.detail else ""
        return f"{self.endpoint} [{self.status.value}] after {self.elapsed_seconds:.1f}s{suffix}"


async def check_endpoint(
    client: LLMClient,
    *,
    endpoint: str = "",
    timeout_seconds: float = ENDPOINT_HEALTH_TIMEOUT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> EndpointHealth:
    """Ask ``client``'s endpoint one trivial question and report what came back.

    ``endpoint`` is a label for the message and nothing reads it to decide
    anything — a check that behaved differently depending on which endpoint it
    was pointed at would be the provider-conditional branch this whole feature
    forbids.
    """
    name = endpoint or client.provider_id
    started = clock()
    try:
        result = await asyncio.wait_for(
            client.invoke(
                InvokeRequest(
                    messages=(Message(role=Role.USER, text=_PROBE),),
                    max_output_tokens=_MAX_PROBE_OUTPUT_TOKENS,
                )
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        return EndpointHealth(
            status=EndpointStatus.UNREACHABLE,
            endpoint=name,
            model_id=client.model_id,
            detail=f"no answer within {timeout_seconds:.0f}s",
            elapsed_seconds=clock() - started,
        )

    elapsed = clock() - started
    if result.succeeded:
        return EndpointHealth(
            status=EndpointStatus.REACHABLE,
            endpoint=name,
            model_id=client.model_id,
            elapsed_seconds=elapsed,
        )

    return EndpointHealth(
        status=_VERDICTS.get(result.failure or FailureClass.UNKNOWN, EndpointStatus.UNREACHABLE),
        endpoint=name,
        model_id=client.model_id,
        detail=result.failure_message,
        elapsed_seconds=elapsed,
    )


__all__ = ["EndpointHealth", "EndpointStatus", "check_endpoint"]
