"""Verifying a configured provider end to end, before an incident does it.

Recorded fixtures prove that an adapter reads a provider's response correctly.
What they cannot prove is that the bytes reach the provider at all: that the
credentials resolve, the SDK extra is installed, the model identifier is one
this deployment can serve, and the schema this deployment's version accepts is
the one the dialect assumes.

So preflight makes four real calls, in the order they fail: authenticate, call a
tool, ask for structure, stream. Each is small. Together they exercise the
things that differ between "configured" and "working", and finding out here
costs a few hundred tokens rather than a stalled investigation.

It also reports which registry rows are still *inferred* — read from the
vendor's documentation rather than confirmed against this deployment — because
a context window that is wrong by a factor of eight is a failure nobody
attributes to a configuration file.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from core.llm.client import ProviderClient
from core.llm.credentials import (
    CredentialResolver,
    EnvironmentCredentialResolver,
    environment_variables_for,
)
from core.llm.factory import LlmFactory
from core.llm.redaction import internal_detail
from core.llm.registry import ModelRegistry, ProviderDescriptor
from core.llm.types import (
    InvokeRequest,
    Message,
    Role,
    StreamEventKind,
    ToolSchema,
)

#: The check tool. Trivial on purpose: a failure here is the provider rejecting
#: the *mechanism*, never the model finding the task hard.
_PROBE_TOOL = ToolSchema(
    name="ninjasre_preflight_echo",
    description="Echo the supplied token back. Call this exactly once.",
    parameters={
        "type": "object",
        "properties": {"token": {"type": "string", "description": "The token to echo."}},
        "required": ["token"],
    },
)

_PROBE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"status": {"type": "string"}, "checked": {"type": "boolean"}},
    "required": ["status", "checked"],
}

_PROBE_TOKEN = "ninjasre-preflight"
_MAX_PROBE_OUTPUT_TOKENS = 256


class CheckStatus(StrEnum):
    """How one preflight check came out."""

    PASSED = "passed"
    FAILED = "failed"
    #: The provider genuinely lacks the capability; the abstraction degrades and
    #: says so, which is the documented behaviour rather than a fault.
    DEGRADED = "degraded"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One check, and what it found."""

    name: str
    status: CheckStatus
    detail: str = ""
    #: How long this check took to answer, in milliseconds. ``0.0`` for a check
    #: that never made a call — a descriptor-declared skip, or a check that ran
    #: before timing was wired around it — which is a fact worth keeping
    #: distinct from "answered instantly".
    duration_ms: float = 0.0

    @property
    def is_blocking(self) -> bool:
        """Return whether this result should stop the deployment being used."""
        return self.status is CheckStatus.FAILED


@dataclass(frozen=True, slots=True)
class PreflightReport:
    """Everything preflight learned about one provider."""

    provider_id: str
    model_id: str
    transport: str
    checks: tuple[CheckResult, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        """Return whether the deployment is usable."""
        return not any(check.is_blocking for check in self.checks)

    def render(self) -> str:
        """Return the report as text, for a CLI to print verbatim.

        Rendered here rather than in the surface so every surface says the same
        thing, and so nothing has to reach into the structure to reformat it.
        """
        lines = [
            f"provider: {self.provider_id}",
            f"model:    {self.model_id}",
            f"transport:{self.transport}",
            "",
        ]
        width = max((len(check.name) for check in self.checks), default=0)
        for check in self.checks:
            suffix = f"  {check.detail}" if check.detail else ""
            lines.append(f"  [{check.status.value:>8}] {check.name.ljust(width)}{suffix}")
        if self.warnings:
            lines.append("")
            lines.extend(f"  warning: {warning}" for warning in self.warnings)
        lines.append("")
        lines.append("preflight passed" if self.ok else "preflight FAILED")
        return "\n".join(lines)


def _elapsed_ms(started: float) -> float:
    """Return how long has passed since ``started`` (a ``time.monotonic()`` reading), in milliseconds."""
    return (time.monotonic() - started) * 1000


async def _timed(check: Awaitable[CheckResult]) -> CheckResult:
    """Return ``check``'s result with how long it actually took attached.

    Wraps the call site rather than each check function, so a check's own body
    stays about what it found and never about how long finding it took —
    the same split ``PreflightReport.render`` already keeps between a check's
    status and its detail.
    """
    started = time.monotonic()
    result = await check
    return replace(result, duration_ms=_elapsed_ms(started))


def _credential_check(
    provider_id: str,
    resolver: CredentialResolver,
    provider: ProviderDescriptor | None,
) -> CheckResult:
    """Check the credentials resolve before spending a call to find out."""
    resolved = resolver.resolve(provider_id)
    required = provider.required_credentials if provider else ()
    missing = [name for name in required if not resolved.has(name)]

    if missing:
        variables = ", ".join(environment_variables_for(provider_id)) or "the credential vault"
        return CheckResult(
            "credentials",
            CheckStatus.FAILED,
            f"missing: {', '.join(missing)} (configure through {variables})",
        )
    return CheckResult("credentials", CheckStatus.PASSED, f"present: {', '.join(resolved.names)}")


async def _authentication_check(client: ProviderClient) -> CheckResult:
    result = await client.invoke(
        InvokeRequest(
            messages=(Message(role=Role.USER, text="Reply with the single word: ready."),),
            max_output_tokens=_MAX_PROBE_OUTPUT_TOKENS,
        )
    )
    if result.succeeded:
        return CheckResult("authentication", CheckStatus.PASSED)
    return CheckResult(
        "authentication",
        CheckStatus.FAILED,
        f"{result.failure}: {result.failure_message}",
    )


async def _tool_call_check(client: ProviderClient) -> CheckResult:
    if not client.descriptor.supports_tools:
        return CheckResult("tool calling", CheckStatus.DEGRADED, "model declares no tool support")

    result = await client.invoke(
        InvokeRequest(
            messages=(
                Message(
                    role=Role.USER,
                    text=f"Call the echo tool with the token {_PROBE_TOKEN!r}.",
                ),
            ),
            tools=(_PROBE_TOOL,),
            max_output_tokens=_MAX_PROBE_OUTPUT_TOKENS,
            # The whole point of this probe: the call is mandatory, so a model
            # that answers in text anyway has demonstrated it cannot do this,
            # not merely that it chose not to this time.
            force_tool_call=True,
        )
    )
    if not result.succeeded:
        return CheckResult(
            "tool calling", CheckStatus.FAILED, f"{result.failure}: {result.failure_message}"
        )
    if not result.tool_calls:
        return CheckResult(
            "tool calling",
            CheckStatus.FAILED,
            "the model answered without calling the tool, even though the call was mandatory",
        )
    return CheckResult("tool calling", CheckStatus.PASSED, result.tool_calls[0].name)


async def _structured_check(client: ProviderClient) -> CheckResult:
    result = await client.invoke_structured(
        InvokeRequest(
            messages=(
                Message(
                    role=Role.USER,
                    text="Report status 'ok' and checked true.",
                ),
            ),
            max_output_tokens=_MAX_PROBE_OUTPUT_TOKENS,
        ),
        schema=_PROBE_SCHEMA,
    )
    if not result.succeeded:
        return CheckResult(
            "structured output", CheckStatus.FAILED, f"{result.failure}: {result.failure_message}"
        )
    if result.structured is None:
        return CheckResult(
            "structured output", CheckStatus.FAILED, "no structured result by any mechanism"
        )

    mechanism = result.structured_mechanism.value if result.structured_mechanism else "unknown"
    status = CheckStatus.PASSED if mechanism == "native" else CheckStatus.DEGRADED
    return CheckResult("structured output", status, f"via {mechanism}")


async def _stream_check(client: ProviderClient) -> CheckResult:
    if not client.descriptor.supports_streaming:
        return CheckResult("streaming", CheckStatus.DEGRADED, "model declares no streaming support")

    text = ""
    failure = ""
    async for event in client.stream(
        InvokeRequest(
            messages=(Message(role=Role.USER, text="Count from one to five."),),
            max_output_tokens=_MAX_PROBE_OUTPUT_TOKENS,
        )
    ):
        if event.kind is StreamEventKind.TEXT_DELTA:
            text += event.text
        elif event.kind is StreamEventKind.ERROR:
            failure = f"{event.failure}: {event.detail}"

    if failure:
        return CheckResult("streaming", CheckStatus.FAILED, failure)
    if not text:
        return CheckResult("streaming", CheckStatus.DEGRADED, "the stream carried no text")
    return CheckResult("streaming", CheckStatus.PASSED, f"{len(text)} characters")


def _registry_warnings(registry: ModelRegistry, provider_id: str, model_id: str) -> tuple[str, ...]:
    warnings: list[str] = []
    descriptor = registry.find(provider_id, model_id)
    if descriptor is None:
        return ()

    if descriptor.inferred:
        warnings.append(
            f"the registry row for {model_id!r} is inferred from vendor documentation, not "
            "confirmed against this deployment — check the context window and feature flags"
        )
    if descriptor.pricing is None:
        warnings.append(
            f"{model_id!r} has no pricing, so cost accounting will report it as unpriced; "
            "supply rates with ModelRegistry.set_pricing"
        )
    return tuple(warnings)


async def preflight(
    provider_id: str | None = None,
    *,
    model_id: str | None = None,
    transport: str | None = None,
    registry: ModelRegistry | None = None,
    credentials: CredentialResolver | None = None,
) -> PreflightReport:
    """Verify one configured provider end to end.

    Ordered so the cheapest and most likely failure comes first: credentials
    that do not resolve, then a call that does not authenticate, then the three
    capabilities. A blocking failure short-circuits the rest — running a tool
    check against a provider that just rejected the key only produces a second
    copy of the same error.
    """
    resolver = credentials or EnvironmentCredentialResolver()
    factory = LlmFactory(registry=registry, credentials=resolver)

    from core.llm.factory import resolve_binding

    binding = resolve_binding(
        provider_id=provider_id,
        model_id=model_id,
        transport=transport,
        registry=factory.registry,
    )

    started = time.monotonic()
    first = _credential_check(
        binding.provider_id, resolver, factory.registry.provider(binding.provider_id)
    )
    checks: list[CheckResult] = [replace(first, duration_ms=_elapsed_ms(started))]

    if checks[0].is_blocking:
        return PreflightReport(
            provider_id=binding.provider_id,
            model_id=binding.model_id,
            transport=binding.transport,
            checks=tuple(checks),
            warnings=_registry_warnings(factory.registry, binding.provider_id, binding.model_id),
        )

    try:
        client = factory.get(
            provider_id=binding.provider_id,
            model_id=binding.model_id,
            transport=binding.transport,
        )
    except Exception as error:  # noqa: BLE001 — a misconfiguration, reported not raised
        checks.append(CheckResult("client", CheckStatus.FAILED, internal_detail(error)))
        return PreflightReport(
            provider_id=binding.provider_id,
            model_id=binding.model_id,
            transport=binding.transport,
            checks=tuple(checks),
        )

    checks.append(await _timed(_authentication_check(client)))
    if not checks[-1].is_blocking:
        checks.append(await _timed(_tool_call_check(client)))
        checks.append(await _timed(_structured_check(client)))
        checks.append(await _timed(_stream_check(client)))

    return PreflightReport(
        provider_id=binding.provider_id,
        model_id=binding.model_id,
        transport=binding.transport,
        checks=tuple(checks),
        warnings=_registry_warnings(factory.registry, binding.provider_id, binding.model_id),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run preflight from the command line and print the report.

    A minimal entry point so an operator can verify a provider before the CLI
    exists to wrap it. The surfaces feature adds the wrapper; this stays the
    thing it calls.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "provider", nargs="?", help="provider to verify (default: the configured one)"
    )
    parser.add_argument(
        "--model", dest="model_id", help="model to verify (default: the provider's)"
    )
    parser.add_argument("--transport", help="transport to verify (default: the configured one)")
    arguments = parser.parse_args(argv)

    report = asyncio.run(
        preflight(
            arguments.provider,
            model_id=arguments.model_id,
            transport=arguments.transport,
        )
    )
    print(report.render())
    return 0 if report.ok else 1


__all__ = [
    "CheckResult",
    "CheckStatus",
    "PreflightReport",
    "main",
    "preflight",
]


if __name__ == "__main__":
    raise SystemExit(main())
