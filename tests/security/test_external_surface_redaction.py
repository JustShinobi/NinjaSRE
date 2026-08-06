"""Errors driven through every sink, and what each one is allowed to say.

An exception message is written for whoever can read the logs. It routinely
carries a query, a hostname, a connection string, an organisation identifier —
and, when a library is careless, a prefix of a key. None of that belongs in an
HTTP response body or a chat message, and CWE-209 is the name for finding out
the hard way.

The discipline this suite enforces has two halves, and the second is the one
that keeps the first from rotting.

**No exception detail reaches an external surface.** A type name at most. A type
name is a fact about NinjaSRE's own code; a message is a fact about the request.

**The local CLI is not an external surface.** Redaction happens at the sink,
once, rather than at each call site — so the engineer running the command sees
the whole failure, and the same shared code path is what publishes the redacted
version to chat. A design that redacted centrally would have made local
debugging worse for no gain in safety.
"""

from __future__ import annotations

import pytest

from core.llm.failures import FailureClass, ProviderFailure
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.rules import default_ruleset
from platform.guardrails.sinks import EXTERNAL_SINKS, LOCAL_SINKS, Sink, SinkGuard
from platform.masking.context import MaskingContext
from platform.masking.policy import MaskingLevel, MaskingPolicy

pytestmark = [pytest.mark.security]

#: The things an exception message is allowed to contain and a response is not.
#: Each is distinctive, so finding one in an external rendering is finding a
#: leak rather than a coincidence.
SECRET_QUERY = "SELECT * FROM credentials WHERE org_id = 'acme'"
SECRET_HOST = "vault-internal.acme.svc.cluster.local:8200"
SECRET_KEY_PREFIX = "sk-live-9f2a41c7e83b6d05"
SECRET_CONNECTION = "postgresql://ninjasre:hunter2@db-primary.internal:5432/ninjasre"

LEAKY_MESSAGE = (
    f"query {SECRET_QUERY} against {SECRET_HOST} failed; "
    f"retried with {SECRET_KEY_PREFIX} on {SECRET_CONNECTION}"
)

LEAKS: tuple[str, ...] = (SECRET_QUERY, SECRET_HOST, SECRET_KEY_PREFIX, SECRET_CONNECTION)


def failures() -> tuple[BaseException, ...]:
    """Return one failure of each shape a sink actually has to render."""
    return (
        RuntimeError(LEAKY_MESSAGE),
        ValueError(LEAKY_MESSAGE),
        ProviderFailure(
            classification=FailureClass.AUTH,
            provider_id="anthropic",
            message=LEAKY_MESSAGE,
            status_code=401,
        ),
        KeyError(SECRET_KEY_PREFIX),
        OSError(111, LEAKY_MESSAGE),
    )


def guard() -> SinkGuard:
    """Return a guard wired the way a deployment wires one."""
    return SinkGuard(
        engine=GuardrailEngine(ruleset=default_ruleset()),
        masking=MaskingContext(policy=MaskingPolicy(level=MaskingLevel.STANDARD)),
    )


@pytest.mark.parametrize("sink", sorted(EXTERNAL_SINKS), ids=lambda s: s.value)
@pytest.mark.parametrize("error", failures(), ids=lambda e: type(e).__name__)
def test_no_exception_detail_reaches_an_external_surface(sink: Sink, error: BaseException) -> None:
    """Five failure shapes, every external sink, nothing gets through."""
    rendered = guard().render_failure(error, sink=sink)

    for leak in LEAKS:
        assert leak not in rendered


@pytest.mark.parametrize("sink", sorted(EXTERNAL_SINKS), ids=lambda s: s.value)
def test_an_external_rendering_still_says_something_useful(sink: Sink) -> None:
    """A response of "an error occurred" wastes the operator's time as surely.

    The type name is the most that leaves, and it has to actually be there —
    otherwise nobody can tell two different failures apart from the outside.
    """
    rendered = guard().render_failure(RuntimeError(LEAKY_MESSAGE), sink=sink)

    assert rendered.strip()
    assert "RuntimeError" in rendered


@pytest.mark.parametrize("sink", sorted(LOCAL_SINKS), ids=lambda s: s.value)
def test_a_local_sink_keeps_the_whole_failure(sink: Sink) -> None:
    """The human running the command is already authorised."""
    rendered = guard().render_failure(RuntimeError(LEAKY_MESSAGE), sink=sink)

    assert SECRET_QUERY in rendered


def test_a_provider_failure_reaches_the_outside_as_its_classification() -> None:
    """Enough for the reader to know whether to retry or to call an operator."""
    error = ProviderFailure(
        classification=FailureClass.RATE_LIMITED,
        provider_id="anthropic",
        message=LEAKY_MESSAGE,
        status_code=429,
    )

    rendered = guard().render_failure(error, sink=Sink.CHAT)

    assert "rate limiting" in rendered.lower()
    assert "anthropic" not in rendered.lower()


# -- the text sinks, as opposed to the failure sinks ---------------------------


def test_a_secret_in_text_is_redacted_before_transmission() -> None:
    """Guardrails apply to text at the sink, not only to exceptions."""
    body = f"the worker connected with {SECRET_CONNECTION} and then stalled"

    rendered = guard().render(body, sink=Sink.REST_API)

    assert SECRET_CONNECTION not in rendered
    assert "[REDACTED]" in rendered


def test_the_same_text_is_untouched_on_the_local_cli() -> None:
    """The engineer at the terminal is debugging, and needs the whole line."""
    body = f"the worker connected with {SECRET_CONNECTION} and then stalled"

    rendered = guard().render(body, sink=Sink.CLI)

    assert rendered == body


def test_a_local_sink_can_still_be_audited() -> None:
    """Not filtering is not the same as not looking.

    The engine is never removed from the boundary; at a local sink it is only
    the acting on the result that is skipped, and ``inspect`` is how a
    deployment records what would have matched.
    """
    body = f"the worker connected with {SECRET_CONNECTION} and then stalled"

    result = guard().inspect(body)

    assert "database-connection-string" in result.rules_fired


def test_persistence_is_filtered_even_though_it_never_leaves_the_host() -> None:
    """Persistence is a filtered destination, and deliberately so.

    A secret written to the database is a secret in every backup, every replica,
    and every export from then on. "It stays on our infrastructure" is a claim
    about the network, not about the blast radius.
    """
    body = f"connection string {SECRET_CONNECTION}"

    rendered = guard().render(body, sink=Sink.PERSISTENCE)

    assert SECRET_CONNECTION not in rendered


def test_identifiers_are_restored_for_an_authorised_reader() -> None:
    """The report names the real pod for the person on call."""
    guarded = guard()
    masked = guarded.masking.mask("pod checkout-7d9f8b6c5d-x2n4p restarted")

    rendered = guarded.render(masked, sink=Sink.REPORT, authorised=True)

    assert "checkout-7d9f8b6c5d-x2n4p" in rendered


def test_identifiers_stay_masked_for_an_unauthorised_reader() -> None:
    """The mixed-authorisation channel from the spec's edge cases.

    A token is meaningless without the mapping, which is exactly what makes it
    the right thing to leave in place when the reader is not entitled to the
    identifier.
    """
    guarded = guard()
    masked = guarded.masking.mask("pod checkout-7d9f8b6c5d-x2n4p restarted")

    rendered = guarded.render(masked, sink=Sink.CHAT, authorised=False)

    assert "checkout-7d9f8b6c5d-x2n4p" not in rendered
    assert "NSRE_MASK_POD_1" in rendered


def test_every_sink_is_classified() -> None:
    """A sink nobody classified would default to whichever branch was written first.

    Enumerating both sets and asserting they partition ``Sink`` is what makes
    adding a surface a compile-time-ish decision rather than a silent one.
    """
    assert set(Sink) == EXTERNAL_SINKS | LOCAL_SINKS
    assert not EXTERNAL_SINKS & LOCAL_SINKS
