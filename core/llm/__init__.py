"""The provider-agnostic LLM layer.

Every model call in NinjaSRE goes through here, and no vendor SDK is imported
anywhere else — ``make check-vendor-sdks`` fails the build on one. That is what
makes a deployment with no permitted egress a real deployment rather than a
degraded one: point the configuration at a local model and the same tool
calling, structured output, streaming, and accounting apply.

The public surface is small on purpose::

    from core.llm import get_llm

    client = get_llm(role="investigator")
    result = await client.invoke(request)

Everything else — dialects, adapters, transports, retry — is an implementation
detail of that call, and none of it reaches a caller's imports.
"""

from __future__ import annotations

from core.llm.factory import get_llm, resolve_binding
from core.llm.failures import RETRYABLE_CLASSES, FailureClass, ProviderFailure
from core.llm.registry import ModelDescriptor, ModelRegistry, default_registry
from core.llm.types import (
    Degradation,
    DegradationKind,
    FinishReason,
    InvokeRequest,
    InvokeResult,
    LLMClient,
    Message,
    ReasoningEffort,
    Role,
    StreamEvent,
    StreamEventKind,
    StructuredMechanism,
    TokenEstimate,
    ToolCall,
    ToolResult,
    ToolSchema,
)
from core.llm.usage import Pricing, TokenCounts, UsageLedger, UsageRecord

__all__ = [
    "RETRYABLE_CLASSES",
    "Degradation",
    "DegradationKind",
    "FailureClass",
    "FinishReason",
    "InvokeRequest",
    "InvokeResult",
    "LLMClient",
    "Message",
    "ModelDescriptor",
    "ModelRegistry",
    "Pricing",
    "ProviderFailure",
    "ReasoningEffort",
    "Role",
    "StreamEvent",
    "StreamEventKind",
    "StructuredMechanism",
    "TokenCounts",
    "TokenEstimate",
    "ToolCall",
    "ToolResult",
    "ToolSchema",
    "UsageLedger",
    "UsageRecord",
    "default_registry",
    "get_llm",
    "resolve_binding",
]
